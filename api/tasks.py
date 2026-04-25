import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import OutboxEvent

logger = logging.getLogger(__name__)

@shared_task
def process_payout(payout_id):
    """
    Placeholder process_payout task.
    In a full Checkpoint 6 implementation, this would handle simulation logic,
    retries, and updating the Payout, Ledger, and IdempotencyKey models.
    """
    logger.info(f"Processing payout: {payout_id}")
    return True

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
