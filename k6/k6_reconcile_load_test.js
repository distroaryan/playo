import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import exec from 'k6/execution';

export const options = {
  stages: [
    { duration: '30s', target: 2000 }, // Ramp up
    { duration: '1m', target: 2000 },  // Sustained high load
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'], // 95% of requests under 1000ms
    http_req_failed: ['rate<0.05'],    // Max 5% failure rate during stress testing
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
  // We need to simulate uploading a CSV file to the reconciliation endpoint
  // We mock a CSV containing standard columns
  const csvContent = `payout_id,status\n${uuidv4()},SUCCESS\n${uuidv4()},FAILED\n`;
  
  // Using http.file to mock the multipart file upload natively in k6
  const data = {
    file: http.file(csvContent, 'reconcile.csv', 'text/csv'),
  };

  const res = http.post(`${BASE_URL}/reconcile`, data);

  check(res, {
    'is status 200 or 403': (r) => r.status === 200 || r.status === 403,
    'has reconciled field': (r) => {
      try {
        if(r.status === 200) {
           return r.json('reconciled') !== undefined;
        }
        return true;
      } catch (e) {
        return false;
      }
    },
  });

  sleep(0.1);
}
