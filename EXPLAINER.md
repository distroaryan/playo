# Playto Payout Engine - Architecture Explainer

## 1. The Ledger

**Question:** How is the balance calculated?
```python
balance = Ledger.objects.filter(merchant=merchant).aggregate(
    total=Sum('amount_paise')
)['total'] or 0
```

**Question:** Why model credits and debits this way?

**Answer:**
We avoid storing a mutable `balance` integer directly on the `Merchant` table because an update in a single value introduces race conditions and makes it complex to handle safely across concurrent requests.

To solve the race condition, we model the balance as a `Ledger` of `CREDIT`, `HOLD`, and `DEBIT` entries. The current balance is mathematically derived from the sum of all entries.

- When a payout is requested, a negative `HOLD` entry immediately reduces the calculated balance. 
- If the payout fails, the `HOLD` is simply deleted (or compensated), seamlessly returning the funds to the available balance without complex math.
- If the payout succeeds, the `HOLD` entry is updated to a new `DEBIT` entry. We avoid creating a new entry because using this approach, we can use row level locks to deal with the race conditions

Using this method, we avoid race conditions and use database aggregation to compute the balance instead of relying on application-level arithmetic operations.

## 2. The Lock

**Question:** How do we safely lock the merchant balance during a transaction?
```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    
    # Compute available balance
    balance = Ledger.objects.filter(merchant=merchant).aggregate(
        total=Sum('amount_paise')
    )['total'] or 0

    if balance < amount_paise:
        return Response({"error": "Insufficient Funds"}, status=status.HTTP_400_BAD_REQUEST)
```

**Database Primitive:**
This relies on the PostgreSQL `SELECT ... FOR UPDATE` primitive (exposed via Django's `select_for_update()`).

When a request enters this atomic block, PostgreSQL places a row-level lock on the specific `Merchant` record. 
- If 10 concurrent requests for the same merchant arrive simultaneously, **1** acquires the lock and the other **9** must wait. 
- The first request calculates the balance, writes the `HOLD` ledger, and commits, releasing the lock.
- The second request then acquires the lock, recalculates the newly reduced balance in real-time, and correctly fails if funds are now insufficient. 

This guarantees a balance can never be overdrawn due to a race condition.

To prove this works in code and not just in theory, a test is added in `test.py` which attempts overdrawing an account with concurrent requests:

```python
def test_overdrawing_balance(self):
    key = "test-key-overdrawal"
    payload = {
        "amount_paise": 50,
        "bank_account_id": "bank_123"
    }
    # Total Available balance = 90

    def make_request(index: int):
        client = APIClient()
        try:
            idempotency_key = f"key-{index}"
            return client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=idempotency_key, format='json')
        finally:
            connection.close()

    # Run 3 requests concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(make_request(i)) for i in range(3)]
        responses = [f.result() for f in concurrent.futures.as_completed(futures)]

    status_codes = [r.status_code for r in responses]
    
    # Only 1 should succeed, the other 2 should fail with insufficient funds
    self.assertEqual(status_codes.count(status.HTTP_202_ACCEPTED), 1)
    self.assertEqual(status_codes.count(status.HTTP_400_BAD_REQUEST), 2)
    
    # Verify db invariants: only 1 payout, 1 hold ledger, 1 outbox event
    self.assertEqual(Payout.objects.filter(amount_paise=50).count(), 1)
    self.assertEqual(Ledger.objects.filter(entry_type='HOLD').count(), 1)
    self.assertEqual(OutboxEvent.objects.filter(event_type='PAYOUT_REQUESTED').count(), 1)

    # Close connections opened by threads so the test db can be dropped
    connections.close_all()
```

## 3. The Idempotency

**Question:** How does the system know it has seen a key before?

**Answer:** 
Clients are required to send an `Idempotency-Key` HTTP header. Idempotency is enforced through **Redis** using an atomic **Lua Script** to handle deduplication

A Redis key has three possible states:

| Redis Value | Meaning | HTTP Response |
|---|---|---|
| `null` (does not exist) | First time seeing this key | Proceed with the payout |
| `PENDING` | A request with this key is currently in flight | `409 Conflict` |
| `{json response}` | The payout has completed, the response is cached | `200 OK` (replayed response) |

**The Lua Script:**
```lua
local val = redis.call('GET', KEYS[1])
if not val then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
    return 'NEW'
end
return val
```
The Lua script is atomic — Redis guarantees no other commands can execute between the `GET` and `SET`. This means if two requests arrive at the exact same microsecond, only **one** will see `null` and set the key to `PENDING`. The other will see `PENDING` and be immediately rejected.

**The Check in `api/views.py`:**
```python
    # Redis Lua Idempotency Check
    redis_key = f"idempotency:{idempotency_key}"
    try:
        result = lua_idempotency_check(keys=[redis_key], args=['PENDING', IDEMPOTENCY_TTL])
        redis_result = result.decode('utf-8') if isinstance(result, bytes) else result

        if redis_result == 'PENDING':
            return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
        elif redis_result != 'NEW':
            # Has a stored response payload — replay it
            return Response(json.loads(redis_result), status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("Redis idempotency check failed: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

Since Redis is the sole idempotency gate, if it is unreachable, the system **cannot guarantee** that a duplicate payout won't be created. Rather than silently proceeding and risking double-processing, the API returns a `500 Internal Server Error` and the client must retry.

**The State Transition (Celery Worker):**
When the Celery worker finishes processing a payout (either `SUCCESS` or `FAILED`), it updates the Redis key from `PENDING` to the final JSON response payload:
```python
def _update_redis_idempotency(payout):
    event = OutboxEvent.objects.filter(payload__payout_id=str(payout.id)).first()
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
```

**Question:** What happens if the first request is in flight when the second arrives?
**Answer:**
1. **Request A** arrives and executes the **Redis Lua Script**. The script atomically checks if the key exists. Since it doesn't, it sets it to `PENDING` with a 5-minute expiry (to prevent permanent locks if the server crashes) and returns `NEW`.
2. **Request B** arrives with the exact same key. It executes the exact same Lua script.
3. Because Lua scripts execute atomically in Redis, **Request B** immediately sees the `PENDING` value set by Request A. It instantly returns a `409 Conflict` without touching the database at all.
4. If **Request A** has already completed and the Celery worker has written the final JSON response, **Request B** will see the cached JSON and return an exact `200 OK` replayed response.

**Concurrency Test:**
```python
def test_concurrent_payout_requests(self):
    key = "test-key-concurrent"
    payload = {
        "amount_paise": 50,
        "bank_account_id": "bank_123"
    }
    
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
    self.assertEqual(Payout.objects.filter(amount_paise=50).count(), 1)
    self.assertEqual(Ledger.objects.filter(entry_type='HOLD').count(), 1)
    self.assertEqual(OutboxEvent.objects.filter(event_type='PAYOUT_REQUESTED').count(), 1)

    connections.close_all()
```

## 4. The State Machine

**Question:** Where in the code is the transition from FAILED to COMPLETED blocked?
**Answer:**
The check is located inside `process_payout` in `api/tasks.py`, immediately upon the worker picking up the task.

**Code Reference:**
```python
@shared_task(bind=True, soft_time_limit=30, max_retries=3)
def process_payout(self, payout_id):
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
```
By placing this explicit check within a `select_for_update()` block *before* the simulation logic runs, we ensure that if a payout was already rolled back (marked as `FAILED`) due to a timeout or other error, a delayed worker retry cannot blindly override the state and turn a `FAILED` payout into a `SUCCESS` payout.

## 5. The AI Audit

### The Bad Code — PostgreSQL-Based Idempotency

The AI initially generated idempotency logic that relied entirely on a PostgreSQL `IdempotencyKey` table. The check was performed **outside** the transaction, and the key was inserted at the **very end** of the transaction:

```python
    # Idempotency check before starting a transaction
    try:
        key_record = IdempotencyKey.objects.get(key=idempotency_key)
        if key_record.status == 'COMPLETED':
            payout = key_record.payout
            return Response({...}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Request already in flight"}, status=status.HTTP_409_CONFLICT)
    except IdempotencyKey.DoesNotExist:
        pass

    # ... then inside the transaction, the IdempotencyKey was created at the very END
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        # ... create payout, ledger, outbox ...
        IdempotencyKey.objects.create(key=idempotency_key, payout=payout, status='PENDING')
```

**Why this is wrong:**
- If two concurrent requests arrive simultaneously, both execute `IdempotencyKey.objects.get()` **outside** the transaction, both see `DoesNotExist`, and both proceed.
- The second request only fails at the **very end** when it tries to `create()` the `IdempotencyKey`, throwing an `IntegrityError` and rolling back all the work — the Payout, Ledger, and OutboxEvent writes are all wasted.
- Under load, this **does not scale**. With 100 concurrent duplicate requests, 99 of them do the full transaction before failing. Every single one opens a DB connection, acquires a row lock, writes to 3 tables, and then rolls everything back.

### The Correct Code — Redis Lua Script

The current implementation uses **Redis as the sole atomic gate** for idempotency. The PostgreSQL `IdempotencyKey` model has been completely dropped.

```lua
local val = redis.call('GET', KEYS[1])
if not val then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
    return 'NEW'
end
return val
```

**Why this is correct:**
- **Speed**: Redis operates entirely in memory. A duplicate check takes microseconds, not milliseconds.
- **Atomicity**: The Lua script guarantees `GET` + `SET` execute as a single atomic operation — no race conditions possible, even under extreme concurrency.
- **Zero DB load for duplicates**: Duplicate requests are rejected at the Redis layer before they ever open a database connection. Under 100 concurrent duplicate requests, only **1** touches PostgreSQL.
- **Self-healing**: The `PENDING` key has a TTL (5 minutes). If the server crashes mid-request, the lock automatically expires and the client can safely retry.
- **Simpler schema**: No `IdempotencyKey` table, no migrations, no joins, no `select_for_update()` contention on a shared index.
- **Hard fail on Redis outage**: If Redis is unreachable, the API returns `500 Internal Server Error` instead of silently proceeding — because proceeding without the idempotency gate would risk creating duplicate payouts.

**Why a Lua script instead of `redis.get()` + `redis.set()` in Python?**
If we used separate `GET` and `SET` commands from the Python client, two concurrent requests could both execute `GET` simultaneously, both see that the key is missing, and both proceed to the database — defeating the purpose entirely. The Lua script eliminates this by making the check-and-set a single uninterruptible operation inside Redis.
