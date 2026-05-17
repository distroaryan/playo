from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Merchant, Ledger
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    token = request.data.get('token')
    if not token:
        return Response({"error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Verify the token with Google
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), settings.GOOGLE_CLIENT_ID
        )

        email = idinfo.get('email')
        name = idinfo.get('name', '')

        if not email:
            return Response({"error": "Google token missing email"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user, created = User.objects.get_or_create(username=email, defaults={'email': email})
            if created:
                # Set unusable password since they use Google
                user.set_unusable_password()
                user.save()
                
            merchant, m_created = Merchant.objects.get_or_create(email=email, defaults={'name': name})
            if m_created:
                # Give 10,000 rupees for testing
                Ledger.objects.create(
                    merchant=merchant,
                    entry_type='CREDIT',
                    amount_paise=1000000 
                )

            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'merchant_id': str(merchant.id),
                'name': merchant.name
            }, status=status.HTTP_200_OK)

    except ValueError as e:
        logger.error(f"Invalid Google token: {e}")
        return Response({"error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        logger.error(f"Google login failed: {e}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    email = request.data.get('email')
    password = request.data.get('password')
    name = request.data.get('name', '')

    if not email or not password:
        return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)
    
    if User.objects.filter(username=email).exists():
        return Response({"error": "User already exists."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)
            merchant = Merchant.objects.create(name=name, email=email)
            # Create an initial ledger entry so they have some test balance
            Ledger.objects.create(
                merchant=merchant,
                entry_type='CREDIT',
                amount_paise=1000000 # Give 10,000 rupees for testing
            )
            refresh = RefreshToken.for_user(user)
            # Also embed merchant ID in the token or just return it
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'merchant_id': str(merchant.id),
                'name': name
            }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get('email')
    password = request.data.get('password')
    
    user = authenticate(username=email, password=password)
    
    if user is not None:
        try:
            merchant = Merchant.objects.get(email=email)
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'merchant_id': str(merchant.id),
                'name': merchant.name
            })
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant profile not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
