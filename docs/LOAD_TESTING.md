# Performance & Load Testing

To ensure the Playto Payout Engine can handle institutional-grade traffic, we use [K6](https://k6.io/) to simulate extreme concurrency scenarios.

## Test Scenarios

The testing suite consists of specialized scripts designed to benchmark different segments of the architecture up to **10,000+ Requests Per Second (RPS)**.

### 1. Payout Endpoint Benchmark (`k6_payout_10k_rps_test.js`)
Aggressive throughput test targeting the main Payout creation API.
- **Goal**: Validate Redis idempotency gate performance and PostgreSQL row-level lock efficiency under extreme concurrent writes.
- **Execution**: 
  ```bash
  k6 run k6_payout_10k_rps_test.js
  ```

### 2. Reconciliation API Stress Test (`k6_reconcile_load_test.js`)
Simulates concurrent CSV reconciliation uploads.
- **Goal**: Measure the impact of sustained bulk operations with row-level locks on database latency and connection pool saturation.
- **Execution**:
  ```bash
  k6 run k6_reconcile_load_test.js
  ```

### 3. Mixed Workload Simulation (`k6_mixed_load_test.js`)
A realistic production simulation blending constant Payout creation, Ledger balance polling, and periodic Reconciliation events.
- **Goal**: Identify deadlocks or resource contention (e.g., Redis CPU maxing out) when reading and writing simultaneously.
- **Execution**:
  ```bash
  k6 run k6_mixed_load_test.js
  ```

## Running the Tests

**Warning**: These scripts are configured with `constant-arrival-rate` executors aimed at generating massive throughput. Running these locally against Docker Desktop may crash your local environment. They are intended for dedicated load-testing environments.

1. Ensure the backend is running.
2. Update the `VITE_MERCHANT_ID` or merchant UUID within the scripts if the seed data has changed.
3. Monitor the database locks and Celery Flower (`localhost:5555`) during the runs.
