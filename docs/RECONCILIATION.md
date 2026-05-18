# Reconciliation API

The Reconciliation API allows the client to upload a CSV file containing payout updates (e.g., status changes from a bank gateway) and processes them synchronously to ensure accurate financial state updates.

## Architectural Flow

[View the Reconciliation Sync Flow Diagram on Excalidraw](https://excalidraw.com/#json=NlRB_EtnXycc-NPVr3WS-,9pFm3CEhk5h5TkzPf9OLCQ)

### Request Lifecycle

1. **Client Upload**: The React Dashboard submits a `multipart/form-data` request with a CSV file to `POST /api/v1/reconcile`.
2. **Parsing & Validation**: The Django API parses the CSV in memory, ensuring it has the required columns (`payout_id`, `status`).
3. **Atomic Processing (Per Row)**:
   - For each valid row, the system begins a **PostgreSQL Database Transaction**.
   - It performs a **Pessimistic Row-Level Lock** (`SELECT FOR UPDATE`) on the target Payout to prevent concurrent modifications during reconciliation.
   - Depending on the provided status:
     - **SUCCESS**: Updates the Payout status to `SUCCESS`, creates a `DEBIT` Ledger entry, and deletes the initial `HOLD` Ledger entry.
     - **FAILED**: Updates the Payout status to `FAILED` and deletes the initial `HOLD` Ledger entry (releasing funds back to the merchant).
4. **Idempotency Finalization**: Updates the Redis Idempotency Key mapping for the payout to a finalized state.
5. **Synchronous Response**: The API aggregates the results and returns a JSON summary containing counts of `reconciled`, `skipped`, and `errors`.

## Concurrency & Financial Safety

By employing pessimistic locking during the reconciliation process, we guarantee that no other in-flight requests (e.g., async Celery workers) can mutate the same payout concurrently. This strict isolation ensures that the Ledger remains an accurate, append-only source of truth and prevents double-spending or duplicate debit entries.
