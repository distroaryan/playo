# Playto Payout Engine — Build Planner

> **Stack:** Django + DRF · React + Tailwind · PostgreSQL · Celery + Redis  
> **Rule:** Every checkpoint = one focused git commit. No mixed concerns in a single commit.  
> **Amounts:** Always integers in paise. Never floats. Never Python arithmetic on balances.

We are building a payment engine where the merchant can request payouts and we simulate the full
lifecycle with production-grade practices. Single merchant only — no authentication, no login,
no multi-tenant scoping. Redis is used exclusively as a Celery message broker.

---

## Checkpoint 1 — Project Scaffold & Environment

**Git commit:** `chore: project scaffold, docker-compose, env config`

- [ ] Initialise Django project (`playto/`) and DRF app structure
- [ ] Create `docker-compose.yml` with four services: `postgres`, `redis`, `django`, `celery`
- [ ] `.env` file with `DATABASE_URL`, `REDIS_URL`, `DEFAULT_MERCHANT_ID`
- [ ] `requirements.txt` — django, djangorestframework, psycopg2-binary, celery, redis, django-celery-results
- [ ] Confirm all four containers start and connect cleanly
- [ ] `README.md` with setup instructions and how to run locally

---

## Checkpoint 2 — Core Models & Migrations

**Git commit:** `feat: merchant, ledger, payout, idempotency key models`

- [ ] **`Merchant` model**
  - `id` (UUID), `name`, `email`, `created_at`
  - No stored `balance` field — balance is always derived from ledger

- [ ] **`Ledger` model** 
  - `id` (UUID), `merchant` (FK)
  - `entry_type` (choices: `CREDIT`, `HOLD`, `DEBIT`)
  - `amount_paise` (`BigIntegerField` — positive for CREDIT, negative for HOLD/DEBIT)
  - `payout` (FK to `Payout`, nullable — set on HOLD and DEBIT rows)
  - `created_at`, `updated_at`

- [ ] **`Payout` model** (state machine)
  - `id` (UUID), `merchant` (FK), `bank_account_id`
  - `amount_paise` (`BigIntegerField`)
  - `status` (choices: `PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`)
  - `retry_count` (`IntegerField`, default 0)
  - `created_at`, `updated_at`

- [ ] **`IdempotencyKey` model**
  - `key` (primary key, string)
  - `payout` (OneToOneField to `Payout`)
  - `status` (choices: `PENDING`, `COMPLETED`)
  - `created_at`
  - On duplicate request: look up key → get linked payout → serialize and return it. No stored response body.

- [ ] **`OutboxEvent` model** (transactional outbox — written atomically with every payout)
  - `id` (UUID), `event_type` (e.g. `PAYOUT_REQUESTED`)
  - `payload` (JSONField — contains `payout_id` and anything the relay worker needs)
  - `status` (choices: `PENDING`, `PROCESSED`, `FAILED`)
  - `created_at`, `processed_at` (nullable)
  - Composite index on `(status, created_at)` — the relay worker queries this on every poll cycle

- [ ] Run and verify all migrations
- [ ] Register all models in Django admin

---

## Checkpoint 3 — Seed Data

**Git commit:** `feat: seed script — single merchant with credit history`

- [ ] Management command `python manage.py seed`
- [ ] Creates exactly 1 merchant — id stored in `.env` as `DEFAULT_MERCHANT_ID`
- [ ] Creates 10-15 `CREDIT` and `DEBIT` ledger entries totalling ₹1,20,000 (simulating prior customer payments)
- [ ] Seed is idempotent — safe to run multiple times, skips if merchant already exists
- [ ] Verify balance derivation query returns correct total after seeding

---

## Checkpoint 4 — Payout Request API

**Git commit:** `feat: POST /api/v1/payouts — idempotency check, row lock, atomic hold, enqueue`

This is the most critical checkpoint. Order of operations is strict.

### Request flow:

- [ ] **Step 1 — Validate request**
  - Reject `400` if `Idempotency-Key` header is missing
  - Reject `400` if `amount_paise` or `bank_account_id` is missing or malformed

- [ ] **Step 2 — Postgres idempotency check**
  - Query `IdempotencyKey` table for this key
  - If found with `status=COMPLETED` → fetch the linked `Payout` via `idempotency_key.payout`, serialize and return with `200`
  - If found with `status=PENDING` → return `409 Conflict` — request is already in flight
  - If not found → proceed to step 3

- [ ] **Step 3 — Single atomic DB transaction** (`with transaction.atomic():`)
  - `SELECT FOR UPDATE` on `Merchant` row — acquires row-level lock
  - Compute available balance via DB-level `SUM` on `Ledger`:
    ```python
    balance = Ledger.objects.filter(merchant=merchant).aggregate(
        total=Sum('amount_paise')
    )['total'] or 0
    ```
  - If `balance < amount_paise` → raise `InsufficientFundsError` → `400`, nothing written to DB
  - Write `Payout(status=PENDING, ...)`
  - Write `Ledger(entry_type=HOLD, amount_paise=-amount_paise, payout=payout)`
  - Write `IdempotencyKey(key=key, payout=payout, status=PENDING)`
  - Write `OutboxEvent(event_type='PAYOUT_REQUESTED', payload={'payout_id': ...}, status='PENDING')`
  - All four writes are inside one `atomic()` block — no Celery call from the view

- [ ] **Step 4 — Return response**
  - Return `202 Accepted`:
    ```json
    { "payout_id": "...", "status": "pending", "amount_paise": 50000 }
    ```

- [ ] Write unit tests for: missing header, duplicate key (pending), duplicate key (completed), insufficient balance, successful creation, outbox entry created alongside payout

---

## Checkpoint 5 — Transactional Outbox Relay Worker

**Git commit:** `feat: outbox relay worker — polls DB and enqueues Celery tasks`

### Why this matters:

Without the outbox pattern:
```
transaction.commit()       ← payout + hold written to DB
process_payout.delay()     ← Redis call happens after — if this fails, payout is PENDING forever
```

With the outbox pattern:
```
transaction.commit()       ← payout + hold + OutboxEvent all written atomically
relay worker polls DB      ← picks up OutboxEvent, calls process_payout.delay()
marks OutboxEvent PROCESSED ← only after Celery confirms the enqueue succeeded
```

### Relay worker task:

- [ ] **`relay_outbox` Celery Beat task** — runs every 5 seconds
  - Query with `select_for_update(skip_locked=True)`:
    ```python
    events = OutboxEvent.objects.select_for_update(skip_locked=True).filter(
        status='PENDING'
    ).order_by('created_at')[:10]
    ```
  - For each event, inside its own `atomic()` block:
    - Call `process_payout.delay(payload['payout_id'])`
    - Mark `outbox_event.status = PROCESSED`, `processed_at = now()`
    - If Celery enqueue raises → leave as `PENDING` for next poll cycle

- [ ] **Stale outbox sweep** — separate Beat task, runs every 10 minutes
  - Query: `OutboxEvent.objects.filter(status='PENDING', created_at__lt=now - 15min)`
  - Mark as `FAILED`, log with payout ID

- [ ] Add both tasks to `CELERY_BEAT_SCHEDULE` in `settings.py`

---

## Checkpoint 6 — Celery Worker & Simulation Logic

**Git commit:** `feat: payout processor worker with simulation, hang retry, failure refund`

### Task structure:

- [ ] **`process_payout` Celery task**
  - `bind=True`, `soft_time_limit=30`, `max_retries=3`
  - On pickup: update `payout.status = PROCESSING`

- [ ] **Simulation logic**
  ```
  random() < 0.70  →  SUCCESS path
  random() < 0.90  →  FAILURE path   (20% of total)
  else             →  HANG path      (10% of total)
  ```

- [ ] **SUCCESS path**
  - `payout.status = SUCCESS`
  - Write `Ledger(entry_type=DEBIT, amount_paise=-amount_paise, payout=payout)` — finalises the debit
  - Delete the `HOLD` ledger row linked to this payout
  - Update `IdempotencyKey.status = COMPLETED`

- [ ] **FAILURE path — no retry, immediate rollback**
  - Call `rollback_payout(payout_id, reason='bank declined')` immediately

- [ ] **HANG path — retry with exponential backoff, then rollback**
  - Catch `SoftTimeLimitExceeded`
  - Increment `payout.retry_count`
  - If `retry_count <= 3` → re-enqueue with backoff, status stays `PROCESSING`:
    ```
    retry_count = 1 → wait 30s
    retry_count = 2 → wait 60s
    retry_count = 3 → wait 120s
    ```
    ```python
    raise self.retry(countdown=30 * (2 ** self.request.retries))
    ```
  - If `retry_count > 3` → call `rollback_payout(payout_id, reason='max hang retries exceeded')`

- [ ] **`rollback_payout(payout_id, reason)` — shared function**
  ```python
  def rollback_payout(payout_id, reason):
      with transaction.atomic():
          payout = Payout.objects.select_for_update().get(id=payout_id)
          payout.status = 'FAILED'
          payout.save(update_fields=['status', 'updated_at'])

          # Delete the HOLD row — funds are released back to available balance
          Ledger.objects.filter(payout=payout, entry_type='HOLD').delete()

          IdempotencyKey.objects.filter(payout=payout).update(status='COMPLETED')
  ```
  - Rollback does NOT write a new ledger entry — it deletes the HOLD row, restoring the balance cleanly

---

## Checkpoint 7 — Beat Watchdog

**Git commit:** `feat: celery beat watchdog for orphaned PENDING and stale PROCESSING payouts`

- [ ] Celery Beat periodic task runs every 2 minutes
- [ ] **Orphaned PENDING sweep**
  - Query: `Payout.objects.filter(status='PENDING', created_at__lt=now - 10min)`
  - Re-enqueue `process_payout.delay(payout_id)`
- [ ] **Stale PROCESSING sweep**
  - Query: `Payout.objects.filter(status='PROCESSING', updated_at__lt=now - 5min)`
  - Increment `retry_count`
  - If `retry_count <= 3` → re-enqueue with backoff
  - If `retry_count > 3` → call `rollback_payout(payout_id, reason='watchdog: stale processing')`
- [ ] Log every watchdog action with payout ID and action taken
- [ ] Configure Beat schedule in `settings.py`

---

## Checkpoint 8 — Balance & Transaction APIs

**Git commit:** `feat: balance, transaction history, and payout status endpoints`

- [ ] **`GET /api/v1/merchant/balance`**
  - `available_balance` = `SUM(amount_paise)` across all `Ledger` entries for the merchant
  - `held_balance` = `SUM` of HOLD rows linked to non-terminal payouts
  - Returns `{ merchant_name, available_balance_paise, held_balance_paise }`

- [ ] **`GET /api/v1/merchant/transactions`**
  - Paginated list of `Ledger` rows for the merchant, newest first
  - Response fields: `entry_type`, `amount_paise`, `payout` (id), `created_at`

- [ ] **`GET /api/v1/payouts`**
  - Paginated list of all payouts, newest first
  - Response fields: `id`, `amount_paise`, `status`, `bank_account_id`, `retry_count`, `created_at`, `updated_at`

- [ ] **`GET /api/v1/payouts/{id}`**
  - Single payout — used by frontend polling
  - Same fields as list response

- [ ] Serializers for all responses
- [ ] All endpoints resolve merchant from `settings.DEFAULT_MERCHANT_ID`

---

## Checkpoint 9 — React Frontend

**Git commit:** `feat: merchant dashboard — balance card, payout form, live payout table`

- [ ] Bootstrap React app with Vite + Tailwind
- [ ] `VITE_API_BASE_URL` in frontend `.env`

- [ ] **`BalanceCard` component**
  - Displays `available_balance` and `held_balance` converted from paise to ₹
  - Polls `GET /api/v1/merchant/balance` every 10 seconds

- [ ] **`PayoutForm` component**
  - Fields: `amount` in ₹ (converted to paise on submit), `bank_account_id`
  - On submit: generate `crypto.randomUUID()` → attach as `Idempotency-Key` header → `POST /api/v1/payouts`
  - Client-side retry on network errors only (never on `4xx`):
    ```
    Attempt 1 → immediate
    Attempt 2 → wait 1s
    Attempt 3 → wait 2s
    Attempt 4 → wait 4s
    ```
  - Distinct UI states: submitting / accepted / duplicate / insufficient funds / error

- [ ] **`PayoutTable` component**
  - Lists all payouts from `GET /api/v1/payouts`, newest first
  - Columns: ID (first 8 chars), amount in ₹, status badge, created, last updated
  - Status badges: `PENDING` (amber), `PROCESSING` (blue), `SUCCESS` (green), `FAILED` (red)

- [ ] **`usePayoutStatus` hook**
  - Accepts `payout_id` and `initial_status`
  - Polls `GET /api/v1/payouts/{id}` every 3 seconds while status is non-terminal
  - Clears interval on `SUCCESS` / `FAILED` or component unmount

---

## Checkpoint 10 — End-to-End Testing

**Git commit:** `test: payout lifecycle, concurrency, idempotency, failure, hang, watchdog`

- [ ] **Idempotency test** — same key in-flight → `409`; same key after completion → linked payout returned
- [ ] **Concurrency test** — 5 simultaneous POSTs, verify row lock holds, final balance is correct
- [ ] **Failure test** — mock simulation to always return FAILURE, verify immediate rollback, HOLD row deleted, balance restored
- [ ] **Hang retry test** — mock simulation to always hang, verify retries at 30s / 60s / 120s, verify HOLD deleted after 3rd hang
- [ ] **Watchdog test** — manually insert stale `PROCESSING` payout, verify Beat increments retry or rolls back
- [ ] **Insufficient balance test** — verify `400`, nothing written to DB
- [ ] Grep codebase — zero `float`, zero bare Python `+=/-=` on any balance or paise field

---

## Checkpoint 11 — Polish & Documentation

**Git commit:** `docs: README, ARCHITECTURE.md, API reference, env example`

- [ ] `README.md` — setup, seed, run, test instructions
- [ ] `ARCHITECTURE.md` — component diagram, data flow, key decisions
- [ ] API reference — all endpoints, headers, request/response shapes, example curls
- [ ] `.env.example` with all keys and descriptions
- [ ] Verify `docker-compose up --build` brings the full system up cleanly from scratch

---

## Checkpoint 12 — Webhook Delivery with Retries *(bonus)*

**Git commit:** `feat: webhook delivery worker with exponential backoff`

### Models:

- [ ] **`WebhookEndpoint` model**
  - `id` (UUID), `merchant` (FK), `url`, `secret` (for HMAC signing), `is_active`, `created_at`

- [ ] **`WebhookDelivery` model**
  - `id` (UUID), `webhook_endpoint` (FK), `payout` (FK)
  - `event_type` (e.g. `payout.success`, `payout.failed`)
  - `payload` (JSONField)
  - `status` (choices: `PENDING`, `DELIVERED`, `FAILED`)
  - `attempt_count` (`IntegerField`, default 0)
  - `last_attempted_at` (nullable), `next_retry_at` (nullable)
  - `response_status` (nullable int)
  - `created_at`

### Delivery task:

- [ ] **`deliver_webhook` Celery task** — triggered at end of `rollback_payout()` and SUCCESS path
  - `bind=True`, `max_retries=5`
  - Sign payload with HMAC-SHA256 → `X-Playto-Signature` header
  - POST to endpoint URL with 10s timeout
  - On 2xx → mark `DELIVERED`
  - On failure → retry with backoff: 10s / 30s / 60s / 300s / 600s → then mark `FAILED`
  - Webhook failure never affects payout state

- [ ] Seed a mock webhook endpoint pointing to `https://webhook.site`
- [ ] Expose `GET /api/v1/webhooks/deliveries`

---

## Checkpoint 13 — Event Sourcing / Audit Log *(bonus)*

**Git commit:** `feat: immutable payout event log for full state transition history`

- [ ] **`PayoutEvent` model** (append-only)
  - `id` (UUID), `payout` (FK), `merchant` (FK)
  - `event_type` (choices: `CREATED`, `PROCESSING_STARTED`, `SUCCEEDED`, `FAILED`, `HANG_RETRY`, `WATCHDOG_RETRY`, `WATCHDOG_FAILED`, `REFUNDED`)
  - `from_status` (nullable), `to_status`
  - `metadata` (JSONField)
  - `created_at`

- [ ] Every state transition writes a `PayoutEvent` inside the same `atomic()` block

- [ ] **Illegal transition guard:**
  ```python
  LEGAL_TRANSITIONS = {
      'PENDING':    ['PROCESSING'],
      'PROCESSING': ['SUCCESS', 'FAILED'],
      'SUCCESS':    [],
      'FAILED':     [],
  }
  ```
  All paths call `transition()` — nothing updates `payout.status` directly

- [ ] Expose `GET /api/v1/payouts/{id}/events`

---

## Checkpoint 14 — Multi-Tenant with Auth *(bonus)*

**Git commit:** `feat: merchant API keys, scoped endpoints, multi-tenant data isolation`

- [ ] **`MerchantAPIKey` model** — `hashed_key` (SHA-256, never plaintext), `is_active`
- [ ] Custom DRF auth class — hashes incoming bearer token, looks up merchant
- [ ] All views switch from `DEFAULT_MERCHANT_ID` to `request.user`
- [ ] Every queryset filtered by `merchant=request.user`
- [ ] Idempotency keys scoped per merchant
- [ ] Seed 2–3 merchants, print keys once to stdout
- [ ] Test: merchant A cannot access merchant B's payouts (`404` not `403`)
- [ ] Frontend: API key input stored in `localStorage`, sent as `Authorization: Bearer <key>`

---

## Simulation Outcomes — Quick Reference

```
PAYOUT CREATED
  └─ status: PENDING
  └─ Ledger: HOLD  (-amount_paise)
  └─ IdempotencyKey: PENDING → payout (OneToOne)
  └─ retry_count: 0

WORKER PICKS UP TASK
  └─ status: PROCESSING

  ┌─ 70% SUCCESS
  │    └─ status: SUCCESS
  │    └─ Ledger: HOLD row deleted
  │    └─ Ledger: DEBIT  (-amount_paise)
  │    └─ IdempotencyKey: COMPLETED
  │
  ├─ 20% FAILURE  ← no retry, straight to refund
  │    └─ status: FAILED
  │    └─ Ledger: HOLD row deleted  (balance restored)
  │    └─ IdempotencyKey: COMPLETED
  │
  └─ 10% HANG  ← retry with backoff, then refund
       └─ SoftTimeLimitExceeded caught
       └─ retry_count += 1
       ├─ retry_count 1 → re-enqueue, wait 30s
       ├─ retry_count 2 → re-enqueue, wait 60s
       ├─ retry_count 3 → re-enqueue, wait 120s
       └─ retry_count > 3 → FAILED
            └─ Ledger: HOLD row deleted  (balance restored)
            └─ IdempotencyKey: COMPLETED

WATCHDOG (every 2 min)
  ├─ PENDING > 10min   → re-enqueue (fresh attempt)
  └─ PROCESSING > 5min → treat as hang, increment retry_count
                          re-enqueue if retries remain, else rollback
```

---

## Key Engineering Rules (Do Not Break)

| Rule | Why |
|---|---|
| `BigIntegerField` for all paise amounts | No float precision loss ever |
| DB-level `SUM` for balance, never Python loops | Single query, no stale reads |
| `SELECT FOR UPDATE` wrapping the balance check | Row lock prevents concurrent overspend |
| `transaction.atomic()` for hold + payout + idempotency key | All-or-nothing, no partial state |
| Ledger `HOLD` row is deleted on rollback, not offset | Clean balance, no phantom entries |
| Ledger is otherwise append-only (`CREDIT`, `DEBIT`) | Full audit trail |
| `IdempotencyKey` links to `Payout` directly | No stored JSON, return live payout data |
| `FAILURE` → immediate rollback, no retry | Bank said no — retrying won't change the answer |
| `HANG` → retry with backoff, rollback after 3rd | Timeout may be transient; give it fair chances |
| Redis is message broker only | One responsibility, no dual state management |