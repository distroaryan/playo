from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from api.models import Merchant, Ledger

class AuthAPITests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('register')
        self.login_url = reverse('login')

    def test_user_can_register(self):
        payload = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "name": "New User"
        }
        response = self.client.post(self.register_url, payload, format='json')
        
        # Should return 201 Created
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Response should contain tokens and merchant_id
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('merchant_id', response.data)
        
        # Verify db records
        self.assertTrue(User.objects.filter(username="newuser@example.com").exists())
        self.assertTrue(Merchant.objects.filter(email="newuser@example.com").exists())
        
        # Verify initial ledger credit
        merchant = Merchant.objects.get(email="newuser@example.com")
        self.assertTrue(Ledger.objects.filter(merchant=merchant, entry_type='CREDIT', amount_paise=1000000).exists())

    def test_duplicate_registration_fails(self):
        # Create user first
        User.objects.create_user(username="existing@example.com", email="existing@example.com", password="password123")
        
        payload = {
            "email": "existing@example.com",
            "password": "newpassword123",
            "name": "Existing User"
        }
        response = self.client.post(self.register_url, payload, format='json')
        
        # Should fail with 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_user_can_login(self):
        # Seed user and merchant
        User.objects.create_user(username="login@example.com", email="login@example.com", password="password123")
        Merchant.objects.create(name="Login User", email="login@example.com")
        
        payload = {
            "email": "login@example.com",
            "password": "password123"
        }
        response = self.client.post(self.login_url, payload, format='json')
        
        # Should succeed
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return tokens and merchant_id
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('merchant_id', response.data)

    def test_invalid_login_fails(self):
        payload = {
            "email": "nonexistent@example.com",
            "password": "password123"
        }
        response = self.client.post(self.login_url, payload, format='json')
        
        # Should fail with 401 Unauthorized
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)
