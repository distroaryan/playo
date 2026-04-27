import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import exec from 'k6/execution';

export const options = {
  // Define stages for the load test
  stages: [
    { duration: '10s', target: 50 },  // Ramp-up to 50 virtual users (VUs) over 10 seconds
    { duration: '30s', target: 50 },  // Stay at 50 VUs for 30 seconds
    { duration: '10s', target: 100 }, // Ramp-up to 100 VUs over 10 seconds
    { duration: '30s', target: 100 }, // Stay at 100 VUs for 30 seconds
    { duration: '10s', target: 0 },   // Ramp-down to 0 VUs
  ],
  thresholds: {
    // We want 95% of requests to complete within 500ms
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    // We want the error rate to be less than 1%
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = 'http://localhost:8000/api/v1';

export function setup() {
  // Check if the backend is up and running before starting the full load test
  const res = http.get(`http://localhost:8000/health`);
  if (res.status !== 200) {
    exec.test.abort('Backend is not healthy or unreachable. Connection refused. Aborting load test early.');
  }
}

export default function () {
  // Setup the request payload
  const idempotencyKey = uuidv4();
  const payload = JSON.stringify({
    amount_paise: 1000,
    bank_account_id: 'K6_BENCHMARK_ACC',
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
  };

  // Send the POST request
  const res = http.post(`${BASE_URL}/payouts`, payload, params);

  // Assertions (Checks)
  check(res, {
    'is status 202': (r) => r.status === 202,
    'has payout_id': (r) => {
      try {
        return r.json('payout_id') !== undefined;
      } catch (e) {
        return false;
      }
    },
    'is status PENDING': (r) => {
      try {
        return r.json('status') === 'PENDING';
      } catch (e) {
        return false;
      }
    },
  });

  // Small sleep to simulate realistic user behavior between requests
  // Set to 0.1s for high throughput testing
  sleep(0.1);
}
