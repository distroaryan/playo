import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000'

/* ── Inline SVG Icons ─────────────────────── */
const Icons = {
  logo: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  send: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <path d="M22 2L11 13" />
      <path d="M22 2l-7 20-4-9-9-4 20-7z" />
    </svg>
  ),
  list: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  refresh: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <path d="M23 4v6h-6" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ),
  alert: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  ),
  inbox: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z" />
    </svg>
  ),
  arrowUp: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  ),
  logout: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" width="16" height="16">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

import AuthScreen from './components/AuthScreen'

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [merchantId, setMerchantId] = useState(localStorage.getItem('merchant_id'))
  const isAuthenticated = !!token

  const [tab, setTab] = useState('payout')
  const [ledger, setLedger] = useState([])
  const [bankAccountId, setBankAccountId] = useState('')
  const [amountRupees, setAmountRupees] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [statusMsg, setStatusMsg] = useState(null)
  const [polling, setPolling] = useState(false)
  const intervalRef = useRef(null)

  const handleLogin = (authData) => {
    localStorage.setItem('token', authData.access)
    localStorage.setItem('merchant_id', authData.merchant_id)
    setToken(authData.access)
    setMerchantId(authData.merchant_id)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('merchant_id')
    setToken(null)
    setMerchantId(null)
  }

  const fetchLedger = useCallback(async () => {
    if (!merchantId || !token) return
    try {
      const res = await fetch(`${API_BASE}/api/v1/merchants/${merchantId}/ledger`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      if (res.ok) {
        const data = await res.json()
        setLedger(data)
        return data
      }
    } catch (err) {
      console.error('Failed to fetch ledger:', err)
    }
    return null
  }, [merchantId, token])

  // Initial fetch
  useEffect(() => {
    if (isAuthenticated) {
      fetchLedger()
    }
  }, [fetchLedger, isAuthenticated])

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
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          amount_rupees: parseFloat(amountRupees),
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
        setAmountRupees('')
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

  /* ── Computed Stats ─────────────────────── */
  const totalEntries = ledger.length
  const holdCount = ledger.filter((e) => e.entry_type === 'HOLD').length
  const netBalance = ledger.reduce((sum, e) => sum + e.amount_paise, 0)

  if (!isAuthenticated) {
    return <AuthScreen onLogin={() => setIsAuthenticated(true)} />
  }

  return (
    <div className="dashboard">
      {/* ── Header ─────────────────────────── */}
      <header className="header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="header-brand">
          <div className="header-icon">{Icons.logo}</div>
          <div>
            <h1>Playto Payout Engine</h1>
            <p>Real-time dashboard for managing payouts and tracking ledger entries</p>
          </div>
        </div>
        <button 
          onClick={handleLogout} 
          className="submit-btn" 
          style={{ width: 'auto', padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-card)', color: 'var(--text-heading)', border: '1px solid var(--border-color)' }}
        >
          {Icons.logout} Logout
        </button>
      </header>

      {/* ── Stats Bar ──────────────────────── */}
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-label">Ledger Entries</div>
          <div className="stat-value accent">{totalEntries}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Pending Holds</div>
          <div className="stat-value" style={{ color: holdCount > 0 ? 'var(--hold-color)' : 'var(--text-heading)' }}>
            {holdCount}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Net Balance</div>
          <div className={`stat-value ${netBalance >= 0 ? 'positive' : 'negative'}`}>
            ₹{(Math.abs(netBalance) / 100).toFixed(2)}
          </div>
        </div>
      </div>

      {/* ── Tabs ───────────────────────────── */}
      <div className="tabs">
        <button
          className={`tab ${tab === 'payout' ? 'active' : ''}`}
          onClick={() => setTab('payout')}
          id="tab-payout"
        >
          <span className="tab-icon">{Icons.send}</span>
          Request Payout
        </button>
        <button
          className={`tab ${tab === 'ledger' ? 'active' : ''}`}
          onClick={() => { setTab('ledger'); fetchLedger(); }}
          id="tab-ledger"
        >
          <span className="tab-icon">{Icons.list}</span>
          Ledger
        </button>
      </div>

      {/* ── Payout Form ────────────────────── */}
      {tab === 'payout' && (
        <form className="payout-form" onSubmit={handleSubmit} id="payout-form">
          <h2>
            {Icons.arrowUp}
            New Payout Request
          </h2>
          <p className="form-subtitle">
            Enter the bank account and amount to initiate a payout transfer.
          </p>

          <div className="form-fields">
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
              <label htmlFor="amountRupees">Amount (Rupees)</label>
              <input
                id="amountRupees"
                type="number"
                min="0.01"
                step="0.01"
                placeholder="e.g. 50.00"
                value={amountRupees}
                onChange={(e) => setAmountRupees(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-actions">
            <button className="submit-btn" type="submit" disabled={submitting} id="submit-payout">
              {submitting ? (
                <>
                  <span className="spinner" />
                  Processing…
                </>
              ) : (
                <>
                  {Icons.send}
                  Submit Payout
                </>
              )}
            </button>

            {statusMsg && (
              <div className={`status-message ${statusMsg.type}`} id="status-message">
                <span className="status-icon">
                  {statusMsg.type === 'success' ? Icons.check : Icons.alert}
                </span>
                {statusMsg.text}
              </div>
            )}
          </div>
        </form>
      )}

      {/* ── Ledger View ────────────────────── */}
      {tab === 'ledger' && (
        <div className="ledger-section">
          <div className="ledger-header">
            <h2>
              Ledger Entries
              {polling && (
                <span className="polling-badge">
                  <span className="polling-dot" />
                  LIVE
                </span>
              )}
            </h2>
            <button className="refresh-btn" onClick={fetchLedger} type="button" id="refresh-ledger">
              {Icons.refresh}
              Refresh
            </button>
          </div>

          {ledger.length === 0 ? (
            <div className="empty-state" id="empty-state">
              <div className="empty-state-icon">{Icons.inbox}</div>
              <p>No ledger entries yet</p>
              <p className="hint">
                {!MERCHANT_ID
                  ? 'Set VITE_MERCHANT_ID in your .env file to get started.'
                  : 'Submit a payout to see entries appear here.'}
              </p>
            </div>
          ) : (
            <div className="ledger-table-wrapper">
              <table className="ledger-table" id="ledger-table">
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
                          <span className="badge-dot" />
                          {entry.entry_type}
                        </span>
                      </td>
                      <td className={entry.amount_paise >= 0 ? 'amount-positive' : 'amount-negative'}>
                        {formatAmount(entry.amount_paise)}
                      </td>
                      <td className="payout-id-cell">
                        {entry.payout_id ? entry.payout_id.slice(0, 8) + '…' : '—'}
                      </td>
                      <td className="date-cell">
                        {formatDate(entry.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default App
