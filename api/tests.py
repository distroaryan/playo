import uuid
from django.test import TransactionTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.conf import settings

from .models import Merchant, Payout, Ledger, IdempotencyKey, OutboxEvent

class PayoutAPITests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('create_payout')
        
        # Create a test merchant
        self.merchant = Merchant.objects.create(
            name="Test Merchant",
            email="test@example.com"
        )
        
        # Override default merchant ID for testing
        settings.DEFAULT_MERCHANT_ID = self.merchant.id

        # Seed initial balance via Ledger
        Ledger.objects.create(
            merchant=self.merchant,
            entry_type='CREDIT',
            amount_paise=100000, # 1000 INR
        )

    def test_missing_header(self):
        payload = {
            "amount_paise": 5000,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_duplicate_key_pending(self):
        key = "test-key-pending"
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account_id="bank_123",
            amount_paise=5000,
            status='PENDING'
        )
        IdempotencyKey.objects.create(
            key=key,
            payout=payout,
            status='PENDING'
        )
        
        payload = {
            "amount_paise": 5000,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("error", response.data)

    def test_duplicate_key_completed(self):
        key = "test-key-completed"
        payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account_id="bank_123",
            amount_paise=5000,
            status='SUCCESS'
        )
        IdempotencyKey.objects.create(
            key=key,
            payout=payout,
            status='COMPLETED'
        )
        
        payload = {
            "amount_paise": 5000,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payout_id"], str(payout.id))

    def test_insufficient_balance(self):
        key = "test-key-insufficient"
        payload = {
            "amount_paise": 200000, # 2000 INR > 1000 INR available
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient Funds", response.data["error"])
        
        # Verify db untouched
        self.assertEqual(Payout.objects.count(), 0)
        self.assertFalse(IdempotencyKey.objects.filter(key=key).exists())

    def test_successful_creation(self):
        key = "test-key-success"
        payload = {
            "amount_paise": 5000,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        
        payout_id = response.data["payout_id"]
        
        # Verify Payout created
        payout = Payout.objects.get(id=payout_id)
        self.assertEqual(payout.status, 'PENDING')
        self.assertEqual(payout.amount_paise, 5000)
        
        # Verify HOLD ledger created
        hold_ledger = Ledger.objects.get(payout=payout, entry_type='HOLD')
        self.assertEqual(hold_ledger.amount_paise, -5000)
        
        # Verify IdempotencyKey created
        idem_key = IdempotencyKey.objects.get(key=key)
        self.assertEqual(idem_key.status, 'PENDING')
        self.assertEqual(idem_key.payout, payout)
        
        # Verify OutboxEvent created
        outbox_event = OutboxEvent.objects.get(payload__payout_id=payout_id)
        self.assertEqual(outbox_event.event_type, 'PAYOUT_REQUESTED')
        self.assertEqual(outbox_event.status, 'PENDING')

    def test_concurrent_payout_requests(self):
        import concurrent.futures
        
        key = "test-key-concurrent"
        payload = {
            "amount_paise": 5000,
            "bank_account_id": "bank_123"
        }
        
        # Function to make the request, needs its own client instance in threads
        def make_request():
            from django.db import connection
            client = APIClient()
            try:
                return client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
            finally:
                connection.close()

        # Run 3 requests concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(3)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        status_codes = [r.status_code for r in responses]
        
        # Exactly one should be 202 ACCEPTED, and two should be 409 CONFLICT
        self.assertEqual(status_codes.count(status.HTTP_202_ACCEPTED), 1)
        self.assertEqual(status_codes.count(status.HTTP_409_CONFLICT), 2)
        
        # Verify db invariants: only 1 payout, 1 hold ledger, 1 outbox event
        self.assertEqual(Payout.objects.filter(amount_paise=5000).count(), 1)
        self.assertEqual(Ledger.objects.filter(entry_type='HOLD').count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='PAYOUT_REQUESTED').count(), 1)

        # Close connections opened by threads so the test db can be dropped
        from django.db import connections
        connections.close_all()

from unittest.mock import patch
from .tasks import relay_outbox

class RelayOutboxWorkerTests(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Test Merchant",
            email="test@example.com"
        )
        self.payout = Payout.objects.create(
            merchant=self.merchant,
            bank_account_id="bank_123",
            amount_paise=5000,
            status='PENDING'
        )
        self.outbox_event = OutboxEvent.objects.create(
            event_type='PAYOUT_REQUESTED',
            payload={'payout_id': str(self.payout.id)},
            status='PENDING'
        )

    @patch('api.tasks.process_payout.delay')
    def test_relay_outbox_worker(self, mock_process_payout_delay):
        # Run the relay task
        relay_outbox()
        
        # Refresh from db
        self.outbox_event.refresh_from_db()
        
        # Assert process_payout.delay was called with the payout_id
        mock_process_payout_delay.assert_called_once_with(str(self.payout.id))
        
        # Assert outbox event was marked PROCESSED
        self.assertEqual(self.outbox_event.status, 'PROCESSED')
        self.assertIsNotNone(self.outbox_event.processed_at)
