import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'
const MERCHANT_ID = import.meta.env.VITE_MERCHANT_ID || ''

function App() {
  const [tab, setTab] = useState('payout')
  const [ledger, setLedger] = useState([])
  const [bankAccountId, setBankAccountId] = useState('')
  const [amountPaise, setAmountPaise] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [statusMsg, setStatusMsg] = useState(null)
  const [polling, setPolling] = useState(false)
  const intervalRef = useRef(null)

  const fetchLedger = useCallback(async () => {
    if (!MERCHANT_ID) return
    try {
      const res = await fetch(`${API_BASE}/api/v1/merchants/${MERCHANT_ID}/ledger`)
      if (res.ok) {
        const data = await res.json()
        setLedger(data)
        return data
      }
    } catch (err) {
      console.error('Failed to fetch ledger:', err)
    }
    return null
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchLedger()
  }, [fetchLedger])

  // Polling logic
  useEffect(() => {
    if (!polling) return

    intervalRef.current = setInterval(async () => {
      const data = await fetchLedger()
      if (data) {
        const hasPending = data.some(
          (entry) => entry.entry_type === 'HOLD'
        )
        if (!hasPending) {
          setPolling(false)
        }
      }
    }, 5000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [polling, fetchLedger])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setStatusMsg(null)

    const idempotencyKey = crypto.randomUUID()

    try {
      const res = await fetch(`${API_BASE}/api/v1/payouts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({
          amount_paise: parseInt(amountPaise, 10),
          bank_account_id: bankAccountId,
        }),
      })

      const data = await res.json()

      if (res.ok) {
        setStatusMsg({
          type: 'success',
          text: `Payout accepted — ID: ${data.payout_id}`,
        })
        setBankAccountId('')
        setAmountPaise('')
        setTab('ledger')
        setPolling(true)
        fetchLedger()
      } else {
        setStatusMsg({
          type: 'error',
          text: data.error || 'Request failed',
        })
      }
    } catch (err) {
      setStatusMsg({ type: 'error', text: 'Network error — is the backend running?' })
    } finally {
      setSubmitting(false)
    }
  }

  const formatAmount = (paise) => {
    const rupees = Math.abs(paise) / 100
    const prefix = paise >= 0 ? '+' : '-'
    return `${prefix} ₹${rupees.toFixed(2)}`
  }

  const formatDate = (iso) => {
    const d = new Date(iso)
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  return (
    <div className="dashboard">
      <header className="header">
        <h1>Playto Payout Engine</h1>
        <p>Dashboard for managing payouts and viewing ledger entries</p>
      </header>

      <div className="tabs">
        <button
          className={`tab ${tab === 'payout' ? 'active' : ''}`}
          onClick={() => setTab('payout')}
        >
          Request Payout
        </button>
        <button
          className={`tab ${tab === 'ledger' ? 'active' : ''}`}
          onClick={() => { setTab('ledger'); fetchLedger(); }}
        >
          Ledger
        </button>
      </div>

      {tab === 'payout' && (
        <form className="payout-form" onSubmit={handleSubmit}>
          <h2>New Payout Request</h2>
          <div className="form-group">
            <label htmlFor="bankAccountId">Bank Account ID</label>
            <input
              id="bankAccountId"
              type="text"
              placeholder="e.g. bank_acc_12345"
              value={bankAccountId}
              onChange={(e) => setBankAccountId(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="amountPaise">Amount (Paise)</label>
            <input
              id="amountPaise"
              type="number"
              min="1"
              placeholder="e.g. 5000 (= ₹50.00)"
              value={amountPaise}
              onChange={(e) => setAmountPaise(e.target.value)}
              required
            />
          </div>
          <button className="submit-btn" type="submit" disabled={submitting}>
            {submitting ? 'Submitting...' : 'Submit Payout'}
          </button>

          {statusMsg && (
            <div className={`status-message ${statusMsg.type}`}>
              {statusMsg.text}
            </div>
          )}
        </form>
      )}

      {tab === 'ledger' && (
        <div className="ledger-section">
          <h2>
            Ledger Entries
            {polling && <span className="polling-badge">POLLING</span>}
          </h2>

          {ledger.length === 0 ? (
            <div className="empty-state">
              <p>No ledger entries yet.{!MERCHANT_ID && ' Set VITE_MERCHANT_ID in your .env file.'}</p>
            </div>
          ) : (
            <table className="ledger-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Payout ID</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      <span className={`badge ${entry.entry_type.toLowerCase()}`}>
                        {entry.entry_type}
                      </span>
                    </td>
                    <td className={entry.amount_paise >= 0 ? 'amount-positive' : 'amount-negative'}>
                      {formatAmount(entry.amount_paise)}
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '13px', fontFamily: 'monospace' }}>
                      {entry.payout_id ? entry.payout_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                      {formatDate(entry.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

export default App
