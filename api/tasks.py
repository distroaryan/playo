import logging
from celery import shared_task
from django.db import transaction
from django.conf import settings
from django.utils import timezone
import random
import logging
import json
import redis
from celery.exceptions import SoftTimeLimitExceeded
from .models import OutboxEvent, Payout, Ledger

logger = logging.getLogger(__name__)

redis_client = redis.from_url(settings.CELERY_BROKER_URL)
IDEMPOTENCY_RESPONSE_TTL = 86400  # 24 hours

def _update_redis_idempotency(payout):
    """
    Writes the final payout response JSON into Redis, replacing the 'PENDING' lock.
    The idempotency key is retrieved from the OutboxEvent payload.
    """
    try:
        event = OutboxEvent.objects.filter(
            payload__payout_id=str(payout.id)
        ).first()
        if event:
            idem_key = event.payload.get('Idempotency-Key')
            if idem_key:
                redis_key = f"idempotency:{idem_key}"
                response_data = json.dumps({
                    "payout_id": str(payout.id),
                    "status": payout.status,
                    "amount_paise": payout.amount_paise
                })
                redis_client.set(redis_key, response_data, ex=IDEMPOTENCY_RESPONSE_TTL)
                logger.info(f"Updated Redis idempotency key '{redis_key}' with terminal state: {payout.status}")
    except Exception as e:
        logger.error(f"Failed to update Redis idempotency key for payout {payout.id}: {e}")

def rollback_payout(payout_id, reason):
    """
    Rolls back a failed or timed-out payout.
    Releases funds back to the available balance by deleting the HOLD ledger.
    Updates Redis idempotency key with the final response.
    """
    logger.info(f"Rolling back payout {payout_id}. Reason: {reason}")
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        payout.status = 'FAILED'
        payout.save(update_fields=['status', 'updated_at'])

        # Delete the HOLD row — funds are released back to available balance
        Ledger.objects.filter(payout=payout, entry_type='HOLD').delete()

    # Update Redis idempotency key with the final response
    _update_redis_idempotency(payout)


@shared_task(bind=True, soft_time_limit=30, max_retries=3)
def process_payout(self, payout_id):
    """
    Simulation logic
    70% SUCCESS, 20% FAILURE, 10% HANG.
    """
    logger.info(f"Processing payout: {payout_id}")

    try:
        # 1. Update status to PROCESSING and block invalid transitions
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)
            
            # State Machine: Block transitions if already in a terminal state
            if payout.status in ['SUCCESS', 'FAILED']:
                logger.info(f"Payout {payout_id} is already in terminal state: {payout.status}. Aborting.")
                return "ALREADY_PROCESSED"

            if payout.status == 'PENDING':
                payout.status = 'PROCESSING'
                payout.save(update_fields=['status', 'updated_at'])

        # 2. Simulation Logic
        rand_val = random.random()
        
        if rand_val < 0.70:
            # SUCCESS path
            logger.info(f"Payout {payout_id} simulating SUCCESS")
            with transaction.atomic():
                payout = Payout.objects.select_for_update().get(id=payout_id)
                payout.status = 'SUCCESS'
                payout.save(update_fields=['status', 'updated_at'])

                # Write DEBIT to finalize
                Ledger.objects.create(
                    merchant=payout.merchant,
                    entry_type='DEBIT',
                    amount_paise=-payout.amount_paise,
                    payout=payout
                )
                # Delete HOLD row
                Ledger.objects.filter(payout=payout, entry_type='HOLD').delete()

            # Update Redis idempotency key with the final response
            _update_redis_idempotency(payout)
            return "SUCCESS"

        elif rand_val < 0.90:
            # FAILURE path
            logger.info(f"Payout {payout_id} simulating FAILURE (bank declined)")
            rollback_payout(payout_id, reason='bank declined')
            return "FAILED"

        else:
            # HANG path
            logger.info(f"Payout {payout_id} simulating HANG")
            # Manually raise SoftTimeLimitExceeded to trigger the celery retry logic
            raise SoftTimeLimitExceeded("Simulated timeout/hang")

    except SoftTimeLimitExceeded:
        logger.warning(f"SoftTimeLimitExceeded caught for payout {payout_id}")
        # Lock payout to safely increment retry_count
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)
            payout.retry_count += 1
            payout.save(update_fields=['retry_count', 'updated_at'])
            current_retries = payout.retry_count

        if current_retries <= 3:
            # Exponential backoff: 1->30s, 2->60s, 3->120s
            # self.request.retries is handled by celery, but we track our own just to be safe
            # Actually celery's retry countdown could use `self.request.retries`
            # The planner said `30 * (2 ** self.request.retries)` but wait, self.request.retries starts at 0.
            # 0->30s, 1->60s, 2->120s. 
            countdown_time = 30 * (2 ** self.request.retries)
            logger.info(f"Re-enqueuing payout {payout_id} in {countdown_time}s (retry {current_retries}/3)")
            raise self.retry(countdown=countdown_time)
        else:
            logger.error(f"Max retries exceeded for payout {payout_id}")
            rollback_payout(payout_id, reason='max hang retries exceeded')
            return "FAILED_MAX_RETRIES"

@shared_task
def relay_outbox():
    """
    Polls the OutboxEvent table for PENDING events.
    Uses select_for_update(skip_locked=True) to ensure exactly-once
    processing across multiple workers.
    """
    events = OutboxEvent.objects.select_for_update(skip_locked=True).filter(
        status='PENDING'
    ).order_by('created_at')[:10]

    with transaction.atomic():
        # Evaluate queryset inside the atomic block
        for event in events:
            try:
                # payload contains payout_id
                payout_id = event.payload.get('payout_id')
                if payout_id:
                    process_payout.delay(payout_id)
                
                event.status = 'PROCESSED'
                event.processed_at = timezone.now()
                event.save(update_fields=['status', 'processed_at'])
                logger.info(f"Relayed outbox event: {event.id}")
            except Exception as e:
                # If Celery enqueue raises an exception, we catch it here.
                # The event stays PENDING and will be retried on next poll.
                logger.error(f"Failed to relay outbox event {event.id}: {e}")
