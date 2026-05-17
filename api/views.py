from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from .models import Merchant, Payout, Ledger, OutboxEvent
import redis
import json
import logging

logger = logging.getLogger(__name__)


redis_client = redis.from_url(settings.CELERY_BROKER_URL)

LUA_IDEMPOTENCY_SCRIPT = """
local val = redis.call('GET', KEYS[1])
if not val then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
    return 'NEW'
end
return val
"""
lua_idempotency_check = redis_client.register_script(LUA_IDEMPOTENCY_SCRIPT)
IDEMPOTENCY_TTL = 300 # 5 MINUTES

class PayoutSerializer(serializers.Serializer):
    amount_rupees = serializers.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0.01)
    bank_account_id = serializers.CharField(required=True)

@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint to verify backend server status.
    """
    return Response({"status": "ok", "message": "Backend server is healthy."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payout(request):
    """
    Main endpoint for simulating the payment
    """
    # 1. Validate Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return Response(
            {"error": "Missing Idempotency-Key header"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2. Validate request body using seralizer
    serializer = PayoutSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    amount_rupees = serializer.validated_data['amount_rupees']
    bank_account_id = serializer.validated_data['bank_account_id']

    if amount_rupees is None or not bank_account_id:
        return Response(
            {"error": "Missing required fields: 'amount_rupees' and 'bank_account_id' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    amount_paise = int(amount_rupees * 100)

    try:
        merchant = Merchant.objects.get(email=request.user.email)
        merchant_id = merchant.id
    except Merchant.DoesNotExist:
        return Response({"error": "Merchant not found for current user."}, status=status.HTTP_403_FORBIDDEN)

     # 3 Redis Lua Idempotency Check
    redis_key = f"idempotency:{idempotency_key}"
    try:
        result = lua_idempotency_check(keys=[redis_key], args=['PENDING', IDEMPOTENCY_TTL])
        redis_result = result.decode('utf-8') if isinstance(result, bytes) else result

        if redis_result == 'PENDING':
            return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
        elif redis_result != 'NEW':
            # Has a stored response payload — return it
            return Response(json.loads(redis_result), status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("Redis idempotency check failed: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Step 4 - Single atomic DB transaction
    try:
        with transaction.atomic():
            # Acquire row-level lock on the merchant
            merchant = Merchant.objects.select_for_update().get(id=merchant_id)
            
            # Compute available balance
            balance = Ledger.objects.filter(merchant=merchant).aggregate(
                total=Sum('amount_paise')
            )['total'] or 0

            if balance < amount_paise:
                redis_client.delete(redis_key)
                return Response({"error": "Insufficient Funds"}, status=status.HTTP_400_BAD_REQUEST)
            
            from django.db import IntegrityError
            from .models import IdempotencyKey

            # Write Payout
            payout = Payout.objects.create(
                merchant=merchant,
                bank_account_id=bank_account_id,
                amount_paise=amount_paise,
                status='PENDING'
            )
            
            # Enforce DB Idempotency
            try:
                IdempotencyKey.objects.create(
                    key=idempotency_key,
                    payout=payout,
                    status='PENDING'
                )
            except IntegrityError:
                redis_client.delete(redis_key)
                return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
            
            # Write Ledger HOLD
            Ledger.objects.create(
                merchant=merchant,
                entry_type='HOLD',
                amount_paise= -1 * amount_paise,
                payout=payout
            )            
            
            # Write OutboxEvent
            OutboxEvent.objects.create(
                event_type='PAYOUT_REQUESTED',
                payload={
                    'payout_id': str(payout.id),
                    "amount_paise": amount_paise,
                    "bank_account_id": bank_account_id,
                    "Idempotency-Key": idempotency_key
                },
                status='PENDING'
            )

        # Step 5 - Return Response (Redis key stays as PENDING until the Celery worker completes)
        return Response(
            {
                "payout_id": str(payout.id),
                "status": payout.status,
                "amount_paise": payout.amount_paise
            },
            status=status.HTTP_202_ACCEPTED
        )
    except Merchant.DoesNotExist:
        redis_client.delete(redis_key)
        return Response({"error": "Merchant not found"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_ledger_entries(request, merchant_id):
    """
    Lists all ledger entries associated with a given merchant ID.
    Ordered by created_at.
    """
    try:
        merchant = Merchant.objects.get(id=merchant_id)
        if merchant.email != request.user.email:
             return Response({"error": "Unauthorized to access this ledger."}, status=status.HTTP_403_FORBIDDEN)
    except Merchant.DoesNotExist:
        return Response({"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

    ledger_entries = Ledger.objects.filter(merchant=merchant).order_by('created_at')
    
    # Very basic manual serialization since we aren't heavily using ModelSerializers yet
    data = [
        {
            "id": str(entry.id),
            "entry_type": entry.entry_type,
            "amount_paise": entry.amount_paise,
            "payout_id": str(entry.payout.id) if entry.payout else None,
            "created_at": entry.created_at.isoformat()
        }
        for entry in ledger_entries
    ]

    return Response(data, status=status.HTTP_200_OK)
