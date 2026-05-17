import uuid
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.conf import settings
import concurrent.futures
import redis
import json
from unittest.mock import patch
from .models import Merchant, Payout, Ledger, OutboxEvent, IdempotencyKey
from django.db import connection, connections
from django.contrib.auth.models import User

redis_client = redis.from_url(settings.CELERY_BROKER_URL)

class PayoutAPITests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('create_payout')
        
        # Create a test user and merchant
        self.user = User.objects.create_user(username="test@example.com", email="test@example.com", password="password123")
        self.merchant = Merchant.objects.create(
            name="Test Merchant",
            email="test@example.com"
        )
        
        self.client.force_authenticate(user=self.user)
        
        # Override default merchant ID for testing
        self.settings_override = override_settings(DEFAULT_MERCHANT_ID=self.merchant.id)
        self.settings_override.enable()

        # Seed initial balance via Ledger
        Ledger.objects.create(
            merchant=self.merchant,
            entry_type='CREDIT',
            amount_paise=100,
        )

        Ledger.objects.create(
            merchant=self.merchant,
            entry_type='DEBIT',
            amount_paise=-10, 
        )

        # Clean up any leftover Redis idempotency keys from previous tests
        for key in redis_client.scan_iter('idempotency:*'):
            redis_client.delete(key)

    def test_missing_header(self):
        payload = {
            "amount_rupees": 0.50,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_duplicate_key_pending(self):
        key = "test-key-pending"
        # Seed Redis with PENDING state
        redis_client.set(f"idempotency:{key}", 'PENDING', ex=300)
        
        payload = {
            "amount_rupees": 0.50,
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
            amount_paise=50,
            status='SUCCESS'
        )
        # Seed Redis with the completed response JSON
        response_data = json.dumps({
            "payout_id": str(payout.id),
            "status": payout.status,
            "amount_paise": payout.amount_paise
        })
        redis_client.set(f"idempotency:{key}", response_data, ex=86400)
        
        payload = {
            "amount_rupees": 0.50,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payout_id"], str(payout.id))

    def test_insufficient_balance(self):
        key = "test-key-insufficient"
        payload = {
            "amount_rupees": 2.00,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient Funds", response.data["error"])
        
        # Verify db untouched
        self.assertEqual(Payout.objects.count(), 0)

    def test_successful_creation(self):
        key = "test-key-success"
        payload = {
            "amount_rupees": 0.50,
            "bank_account_id": "bank_123"
        }
        response = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=key, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        
        payout_id = response.data["payout_id"]
        
        # Verify Payout created
        payout = Payout.objects.get(id=payout_id)
        self.assertEqual(payout.status, 'PENDING')
        self.assertEqual(payout.amount_paise, 50)
        
        # Verify HOLD ledger created
        hold_ledger = Ledger.objects.get(payout=payout, entry_type='HOLD')
        self.assertEqual(hold_ledger.amount_paise, -50)
        
        # Verify DB Idempotency Key created
        db_key = IdempotencyKey.objects.get(key=key)
        self.assertEqual(db_key.payout, payout)
        self.assertEqual(db_key.status, 'PENDING')
        
        # Verify Redis idempotency key is set to PENDING
        redis_val = redis_client.get(f"idempotency:{key}")
        self.assertEqual(redis_val.decode('utf-8'), 'PENDING')
        
        # Verify OutboxEvent created
        outbox_event = OutboxEvent.objects.get(payload__payout_id=payout_id)
        self.assertEqual(outbox_event.event_type, 'PAYOUT_REQUESTED')
        self.assertEqual(outbox_event.status, 'PENDING')

    def test_concurrent_payout_requests(self):
        key = "test-key-concurrent"
        payload = {
            "amount_rupees": 0.50,
            "bank_account_id": "bank_123"
        }
        
        # Function to make the request, needs its own client instance in threads
        def make_request():
            from django.db import connection
            client = APIClient()
            # The user needs to be authenticated since this is a new client instance
            user = User.objects.get(username="test@example.com")
            client.force_authenticate(user=user)
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
        self.assertEqual(Payout.objects.filter(amount_paise=50).count(), 1)
        self.assertEqual(Ledger.objects.filter(entry_type='HOLD').count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='PAYOUT_REQUESTED').count(), 1)

        # Close connections opened by threads so the test db can be dropped
        from django.db import connections
        connections.close_all()

    def test_overdrawing_balance(self):
        key = "test-key-overdrawal"
        payload = {
            "amount_rupees": 0.50,
            "bank_account_id": "bank_123"
        }
        # Total Available balancer = 90

        def make_request(index: int):
            client = APIClient()
            # The user needs to be authenticated since this is a new client instance
            user = User.objects.get(username="test@example.com")
            client.force_authenticate(user=user)
            try:
                idempotency_key = f"key-{index}"
                return client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=idempotency_key, format='json')
            finally:
                connection.close()

        # Run 3 requests concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        status_codes = [r.status_code for r in responses]
        
        # Exactly one should be 202 ACCEPTED, and 2 should be 400 BAD REQUEST due to insufficient balancer
        self.assertEqual(status_codes.count(status.HTTP_202_ACCEPTED), 1)
        self.assertEqual(status_codes.count(status.HTTP_400_BAD_REQUEST), 2)
        
        # Verify db invariants: only 1 payout, 1 hold ledger, 1 outbox event
        self.assertEqual(Payout.objects.filter(amount_paise=50).count(), 1)
        self.assertEqual(Ledger.objects.filter(entry_type='HOLD').count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='PAYOUT_REQUESTED').count(), 1)

        # Close connections opened by threads so the test db can be dropped
        connections.close_all()

from .tasks import rollback_payout, process_payout

class TasksTests(TransactionTestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test Merchant", email="test2@example.com")
        self.payout = Payout.objects.create(merchant=self.merchant, bank_account_id="bank_123", amount_paise=50, status='PENDING')
        Ledger.objects.create(merchant=self.merchant, entry_type='HOLD', amount_paise=-50, payout=self.payout)
        OutboxEvent.objects.create(
            event_type='PAYOUT_REQUESTED',
            payload={"payout_id": str(self.payout.id), "Idempotency-Key": "task-test-key"}, 
            status='PENDING'
        )

    def test_rollback_payout_appends_ledger(self):
        rollback_payout(self.payout.id, reason="test failure")
        
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, 'FAILED')
        
        # Verify old HOLD still exists
        holds = Ledger.objects.filter(payout=self.payout, entry_type='HOLD')
        self.assertEqual(holds.count(), 2)
        
        # We should have one -50 and one 50
        amounts = set([h.amount_paise for h in holds])
        self.assertEqual(amounts, {-50, 50})

    @patch('api.tasks.random.random')
    def test_process_payout_success_appends_ledger(self, mock_random):
        mock_random.return_value = 0.5 # forces success
        
        process_payout(self.payout.id)
        
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, 'SUCCESS')
        
        # Verify holds
        holds = Ledger.objects.filter(payout=self.payout, entry_type='HOLD')
        self.assertEqual(holds.count(), 2)
        amounts = set([h.amount_paise for h in holds])
        self.assertEqual(amounts, {-50, 50})
        
        # Verify debit
        debits = Ledger.objects.filter(payout=self.payout, entry_type='DEBIT')
        self.assertEqual(debits.count(), 1)
        self.assertEqual(debits.first().amount_paise, -50)
