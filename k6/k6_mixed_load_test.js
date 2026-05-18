import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import exec from 'k6/execution';

export const options = {
  stages: [
    { duration: '1m', target: 3000 }, 
    { duration: '2m', target: 3000 }, 
    { duration: '1m', target: 0 }, 
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'], 
    http_req_failed: ['rate<0.05'], 
  },
};

const BASE_URL = 'http://localhost:8000/api/v1';
const MERCHANT_ID = '00000000-0000-0000-0000-000000000000'; // Dummy ID to trigger DB lookup

export function setup() {
  const res = http.get(`http://localhost:8000/health`);
  if (res.status !== 200) {
    exec.test.abort('Backend is not healthy or unreachable.');
  }
}

export default function () {
  const r = Math.random();

  if (r < 0.70) {
    // 70% of traffic: Create Payouts
    const payload = JSON.stringify({
      amount_paise: 500,
      bank_account_id: 'MIXED_ACC',
    });
    const params = { headers: { 'Content-Type': 'application/json', 'Idempotency-Key': uuidv4() } };
    const res = http.post(`${BASE_URL}/payouts`, payload, params);
    check(res, { 'payout status 202': (r) => r.status === 202 });
  } else if (r < 0.95) {
    // 25% of traffic: View Ledger 
    const params = { headers: { 'Authorization': 'Bearer DUMMY_TOKEN' } };
    const res = http.get(`${BASE_URL}/merchants/${MERCHANT_ID}/ledger`, params);
    check(res, { 'ledger check ok': (r) => r.status === 200 || r.status === 403 || r.status === 404 });
  } else {
    // 5% of traffic: Recon
    const csvContent = `payout_id,status\n${uuidv4()},SUCCESS\n${uuidv4()},FAILED\n`;
    const data = { file: http.file(csvContent, 'reconcile.csv', 'text/csv') };
    const res = http.post(`${BASE_URL}/reconcile`, data);
    check(res, { 'reconcile check ok': (r) => r.status === 200 || r.status === 403 });
  }

  sleep(0.05); // Short wait time
}
