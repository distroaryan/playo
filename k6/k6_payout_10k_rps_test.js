import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import exec from 'k6/execution';

export const options = {
  scenarios: {
    constant_request_rate: {
      executor: 'constant-arrival-rate',
      rate: 10000, // 10,000 requests per second (RPS)
      timeUnit: '1s',
      duration: '3m',      // Keep hitting 10k RPS for 3 mins
      preAllocatedVUs: 2000,
      maxVUs: 10000,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1500'], // More lenient for extreme throughput testing
    http_req_failed: ['rate<0.01'], 
  },
};

const BASE_URL = 'http://localhost:8000/api/v1';

export function setup() {
  const res = http.get(`http://localhost:8000/health`);
  if (res.status !== 200) {
    exec.test.abort('Backend is not healthy or unreachable.');
  }
}

export default function () {
  const idempotencyKey = uuidv4();
  const payload = JSON.stringify({
    amount_paise: Math.floor(Math.random() * 5000) + 100,
    bank_account_id: 'K6_10K_BENCHMARK',
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
  };

  const res = http.post(`${BASE_URL}/payouts`, payload, params);

  check(res, {
    'is status 202': (r) => r.status === 202,
  });
}
