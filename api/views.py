from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint to verify backend server status.
    """
    return Response({"status": "ok", "message": "Backend server is healthy."}, status=status.HTTP_200_OK)


@api_view(['POST'])
def create_payout(request):
    """
    Initial implementation of Checkpoint 4: Payout Request API.
    Validates headers and basic payload.
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

    # If everything is correct, return success (mocking for now before full CP4 implementation)
    return Response(
        {
            "status": "success",
            "message": "Payload and headers validated successfully.",
            "data": {
                "amount_paise": amount_paise,
                "bank_account_id": bank_account_id,
                "idempotency_key": idempotency_key
            }
        },
        status=status.HTTP_200_OK
    )
