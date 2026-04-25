from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Sum

from .models import Merchant, Payout, Ledger, IdempotencyKey, OutboxEvent

@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint to verify backend server status.
    """
    return Response({"status": "ok", "message": "Backend server is healthy."}, status=status.HTTP_200_OK)


@api_view(['POST'])
def create_payout(request):
    """
    Implementation of Checkpoint 4: Payout Request API.
    Idempotency check, row lock, atomic hold, enqueue.
    """
    # 1. Validate Idempotency-Key header
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return Response(
            {"error": "Missing Idempotency-Key header"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2. Validate payload fields
    amount_paise = request.data.get('amount_paise')
    bank_account_id = request.data.get('bank_account_id')

    if amount_paise is None or not bank_account_id:
        return Response(
            {"error": "Missing required fields: 'amount_paise' and 'bank_account_id' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate type of amount_paise (must be an integer)
    try:
        amount_paise = int(amount_paise)
    except (ValueError, TypeError):
        return Response(
            {"error": "Malformed field: 'amount_paise' must be an integer."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Idempotency check before transaction
    try:
        key_record = IdempotencyKey.objects.get(key=idempotency_key)
        if key_record.status == 'COMPLETED':
            payout = key_record.payout
            return Response({
                "payout_id": str(payout.id),
                "status": payout.status,
                "amount_paise": payout.amount_paise
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
    except IdempotencyKey.DoesNotExist:
        pass

    merchant_id = getattr(settings, 'DEFAULT_MERCHANT_ID', None)
    if not merchant_id:
        return Response({"error": "Server configuration error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Step 3 - Single atomic DB transaction
    try:
        with transaction.atomic():
            # Acquire row-level lock on the merchant
            merchant = Merchant.objects.select_for_update().get(id=merchant_id)
            
            # Compute available balance
            balance = Ledger.objects.filter(merchant=merchant).aggregate(
                total=Sum('amount_paise')
            )['total'] or 0

            if balance < amount_paise:
                return Response({"error": "Insufficient Funds"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Write Payout
            payout = Payout.objects.create(
                merchant=merchant,
                bank_account_id=bank_account_id,
                amount_paise=amount_paise,
                status='PENDING'
            )
            
            # Write Ledger HOLD
            Ledger.objects.create(
                merchant=merchant,
                entry_type='HOLD',
                amount_paise=-amount_paise,
                payout=payout
            )
            
            # Write IdempotencyKey
            IdempotencyKey.objects.create(
                key=idempotency_key,
                payout=payout,
                status='PENDING'
            )
            
            # Write OutboxEvent
            OutboxEvent.objects.create(
                event_type='PAYOUT_REQUESTED',
                payload={'payout_id': str(payout.id)},
                status='PENDING'
            )

        # Step 4 - Return Response
        return Response(
            {
                "payout_id": str(payout.id),
                "status": payout.status,
                "amount_paise": payout.amount_paise
            },
            status=status.HTTP_202_ACCEPTED
        )
    except IntegrityError:
        # If another concurrent request inserted the same idempotency key
        return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
    except Merchant.DoesNotExist:
        return Response({"error": "Merchant not found"}, status=status.HTTP_400_BAD_REQUEST)
