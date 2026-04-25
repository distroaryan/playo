import uuid
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.conf import settings

from .models import Merchant, Payout, Ledger, IdempotencyKey, OutboxEvent

class PayoutAPITests(TestCase):
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
