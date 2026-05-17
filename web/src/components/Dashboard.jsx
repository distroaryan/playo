import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Layers, LogOut, ArrowUpRight, List, RefreshCw,
  Inbox, CheckCircle, AlertCircle, TrendingUp, Clock,
  Wallet, SendHorizonal, CreditCard, ChevronRight,
} from 'lucide-react'

const API_BASE = 'http://localhost:8000'

// ── colour helpers ──────────────────────────────────────────────────
const BADGE = {
  CREDIT: { bg: '#ECFDF5', color: '#065F46', border: '#A7F3D0', dot: '#10B981' },
  DEBIT:  { bg: '#FEF2F2', color: '#991B1B', border: '#FECACA', dot: '#EF4444' },
  HOLD:   { bg: '#FFFBEB', color: '#92400E', border: '#FDE68A', dot: '#F59E0B' },
  DEFAULT:{ bg: '#F8FAFC', color: '#475569', border: '#E2E8F0', dot: '#94A3B8' },
}

const badge = (type) => BADGE[type] || BADGE.DEFAULT

export default function Dashboard({ token, merchantId, onLogout }) {
  const [tab, setTab]               = useState('payout')
  const [ledger, setLedger]         = useState([])
  const [payouts, setPayouts]       = useState([])
  const [bankAccountId, setBankAccountId] = useState('')
  const [amountRupees, setAmountRupees]   = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [statusMsg, setStatusMsg]   = useState(null)   // { type: 'success'|'error', text }
  const [polling, setPolling]       = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const intervalRef = useRef(null)

  const fetchData = useCallback(async () => {
    if (!merchantId || !token) return null
    try {
      const [ledgerRes, payoutRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/merchants/${merchantId}/ledger`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_BASE}/api/v1/merchants/${merchantId}/payout`, {
          headers: { Authorization: `Bearer ${token}` },
        })
      ])
      if (ledgerRes.ok && payoutRes.ok) {
        const lData = await ledgerRes.json()
        const pData = await payoutRes.json()
        lData.sort((a,b) => new Date(b.created_at) - new Date(a.created_at))
        pData.sort((a,b) => new Date(b.created_at) - new Date(a.created_at))
        setLedger(lData)
        setPayouts(pData)
        return { lData, pData }
      }
    } catch (e) { console.error('Fetch failed', e) }
    return null
  }, [merchantId, token])

  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    if (!polling) return
    intervalRef.current = setInterval(async () => {
      const d = await fetchData()
      if (d && !d.pData.some(p => p.status === 'PENDING' || p.status === 'PROCESSING')) setPolling(false)
    }, 5000)
    return () => clearInterval(intervalRef.current)
  }, [polling, fetchData])

  const handleRefresh = async () => {
    setRefreshing(true)
    await fetchData()
    setRefreshing(false)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true); setStatusMsg(null)
    const key = crypto.randomUUID()
    try {
      const res = await fetch(`${API_BASE}/api/v1/payouts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': key,
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ amount_rupees: parseFloat(amountRupees), bank_account_id: bankAccountId }),
      })
      const data = await res.json()
      if (res.ok) {
        setStatusMsg({ type: 'success', text: `Payout accepted — ID: ${data.payout_id}` })
        setBankAccountId(''); setAmountRupees('')
        setTab('payouts'); setPolling(true); fetchData()
      } else {
        setStatusMsg({ type: 'error', text: data.error || 'Request failed' })
      }
    } catch {
      setStatusMsg({ type: 'error', text: 'Network error — is the backend running?' })
    } finally { setSubmitting(false) }
  }

  const fmt = (paise) =>
    `${paise >= 0 ? '+' : '−'} ₹${(Math.abs(paise) / 100).toFixed(2)}`

  const fmtDate = (iso) =>
    new Date(iso).toLocaleString('en-IN', {
      day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit',
    })

  const totalEntries = ledger.length
  const holdCount    = payouts.filter(p => p.status === 'PENDING' || p.status === 'PROCESSING').length
  const credits      = ledger.filter(e => e.entry_type === 'CREDIT').reduce((s, e) => s + e.amount_paise, 0)
  const successfulPayouts = payouts.filter(p => p.status === 'SUCCESS').reduce((s, p) => s + p.amount_paise, 0)
  const netBalance   = credits - successfulPayouts
  const initials     = merchantId ? merchantId.slice(0, 2).toUpperCase() : 'ME'

  // ── render ──────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: '#F8F7FF', fontFamily: 'Inter, system-ui, sans-serif' }}>

      {/* NAV */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: 'white',
        borderBottom: '1px solid #E2E8F0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}>
        <div style={{
          maxWidth: '1100px', margin: '0 auto',
          padding: '0 32px', height: '64px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          {/* Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '9px',
              background: 'linear-gradient(135deg, #4F46E5, #6D28D9)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(79,70,229,0.3)',
            }}>
              <Layers size={16} color="white" />
            </div>
            <span style={{ fontWeight: 700, fontSize: '17px', color: '#0F172A' }}>Playto</span>
            <span style={{ color: '#CBD5E1', fontSize: '13px', marginLeft: '2px' }}>|</span>
            <span style={{ color: '#94A3B8', fontSize: '13px' }}>Payout Engine</span>
          </div>

          {/* Right */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '34px', height: '34px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #818CF8, #4F46E5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 6px rgba(79,70,229,0.25)',
            }}>
              <span style={{ color: 'white', fontSize: '11px', fontWeight: 700 }}>{initials}</span>
            </div>
            <button
              onClick={onLogout}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '7px 14px', border: '1px solid #E2E8F0',
                borderRadius: '8px', background: 'white',
                fontSize: '13px', fontWeight: 500, color: '#475569',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = '#C7D2FE'; e.currentTarget.style.color = '#4F46E5' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = '#E2E8F0'; e.currentTarget.style.color = '#475569' }}
            >
              <LogOut size={13} />
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* MAIN */}
      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 32px' }}>

        {/* Page heading */}
        <div style={{ marginBottom: '28px' }}>
          <h1 style={{ fontSize: '26px', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.4px', margin: 0 }}>
            Payout Dashboard
          </h1>
          <p style={{ color: '#64748B', fontSize: '14px', marginTop: '6px' }}>
            Manage payouts and track ledger activity in real time.
          </p>
        </div>

        {/* STAT CARDS */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
          <StatCard
            label="Ledger Entries"
            value={totalEntries}
            icon={<TrendingUp size={16} color="#4F46E5" />}
            iconBg="#EEF2FF"
            valueColor="#4F46E5"
          />
          <StatCard
            label="Pending Holds"
            value={holdCount}
            icon={<Clock size={16} color={holdCount > 0 ? '#D97706' : '#94A3B8'} />}
            iconBg={holdCount > 0 ? '#FFFBEB' : '#F8FAFC'}
            valueColor={holdCount > 0 ? '#D97706' : '#0F172A'}
          />
          <StatCard
            label="Net Balance"
            value={`₹${(Math.abs(netBalance) / 100).toFixed(2)}`}
            icon={<Wallet size={16} color={netBalance >= 0 ? '#059669' : '#DC2626'} />}
            iconBg={netBalance >= 0 ? '#ECFDF5' : '#FEF2F2'}
            valueColor={netBalance >= 0 ? '#059669' : '#DC2626'}
          />
        </div>

        {/* MAIN TABBED CARD */}
        <div style={{
          background: 'white',
          borderRadius: '16px',
          border: '1px solid #E2E8F0',
          boxShadow: '0 4px 24px rgba(79,70,229,0.06), 0 1px 4px rgba(0,0,0,0.04)',
          overflow: 'hidden',
        }}>

          {/* Tab bar */}
          <div style={{ display: 'flex', borderBottom: '1px solid #F1F5F9', padding: '0 8px' }}>
            <TabButton
              active={tab === 'payout'}
              icon={<SendHorizonal size={15} />}
              label="Request Payout"
              onClick={() => setTab('payout')}
            />
            <TabButton
              active={tab === 'payouts'}
              icon={<List size={15} />}
              label="Payouts"
              onClick={() => { setTab('payouts'); fetchData() }}
              badge={polling ? 'LIVE' : null}
            />
            <TabButton
              active={tab === 'ledger'}
              icon={<Layers size={15} />}
              label="Ledger"
              onClick={() => { setTab('ledger'); fetchData() }}
              badge={polling ? 'LIVE' : null}
            />
          </div>

          {/* ── Payout form ── */}
          {tab === 'payout' && (
            <div style={{ padding: '32px' }}>
              <div style={{ marginBottom: '24px' }}>
                <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0F172A', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '28px', height: '28px', borderRadius: '8px', background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <ArrowUpRight size={15} color="#4F46E5" />
                  </div>
                  New Payout Request
                </h2>
                <p style={{ color: '#64748B', fontSize: '13px', marginTop: '8px' }}>
                  Enter the destination bank account and amount to initiate a payout.
                </p>
              </div>

              <form id="payout-form" onSubmit={handleSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                  {/* Bank account */}
                  <div>
                    <label style={labelStyle}>
                      <CreditCard size={12} style={{ opacity: 0.5 }} /> Bank Account ID
                    </label>
                    <input
                      id="bankAccountId"
                      list="bankList"
                      placeholder="bank_acc_12345"
                      value={bankAccountId}
                      onChange={e => setBankAccountId(e.target.value)}
                      required
                      style={fieldStyle}
                      onFocus={e => applyFocus(e.target)}
                      onBlur={e => applyBlur(e.target)}
                    />
                    <datalist id="bankList">
                      {[...new Set(ledger.filter(e => e.bank_account_id).map(e => e.bank_account_id))].map(id => (
                        <option key={id} value={id} />
                      ))}
                    </datalist>
                  </div>

                  {/* Amount */}
                  <div>
                    <label style={labelStyle}>
                      <span style={{ fontWeight: 700, opacity: 0.5, fontSize: '11px' }}>₹</span> Amount (Rupees)
                    </label>
                    <input
                      id="amountRupees"
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="50.00"
                      value={amountRupees}
                      onChange={e => setAmountRupees(e.target.value)}
                      required
                      style={fieldStyle}
                      onFocus={e => applyFocus(e.target)}
                      onBlur={e => applyBlur(e.target)}
                    />
                  </div>
                </div>

                {/* Submit */}
                <button
                  id="submit-payout"
                  type="submit"
                  disabled={submitting}
                  style={{
                    width: '100%', padding: '14px 24px',
                    background: submitting ? '#A5B4FC' : 'linear-gradient(135deg, #4F46E5 0%, #6D28D9 100%)',
                    color: 'white', border: 'none', borderRadius: '10px',
                    fontSize: '15px', fontWeight: 600, cursor: submitting ? 'not-allowed' : 'pointer',
                    boxShadow: submitting ? 'none' : '0 4px 16px rgba(79,70,229,0.35)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {submitting ? (
                    <><Spinner /> Processing…</>
                  ) : (
                    <><SendHorizonal size={16} /> Submit Payout <ChevronRight size={16} style={{ marginLeft: '2px' }} /></>
                  )}
                </button>

                {/* Status banner */}
                {statusMsg && (
                  <div
                    id="status-message"
                    style={{
                      marginTop: '16px',
                      display: 'flex', alignItems: 'flex-start', gap: '10px',
                      padding: '12px 16px', borderRadius: '10px',
                      background: statusMsg.type === 'success' ? '#ECFDF5' : '#FEF2F2',
                      border: `1px solid ${statusMsg.type === 'success' ? '#A7F3D0' : '#FECACA'}`,
                    }}
                  >
                    {statusMsg.type === 'success'
                      ? <CheckCircle size={16} color="#059669" style={{ flexShrink: 0, marginTop: '1px' }} />
                      : <AlertCircle size={16} color="#DC2626" style={{ flexShrink: 0, marginTop: '1px' }} />}
                    <p style={{
                      fontSize: '14px',
                      color: statusMsg.type === 'success' ? '#065F46' : '#991B1B',
                      margin: 0, wordBreak: 'break-all',
                    }}>
                      {statusMsg.text}
                    </p>
                  </div>
                )}
              </form>
            </div>
          )}

          {/* ── Payouts tab ── */}
          {tab === 'payouts' && (
            <div style={{ padding: '32px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0F172A', margin: 0 }}>Payouts</h2>
                <button
                  id="refresh-payouts"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '7px 14px', border: '1px solid #E2E8F0', borderRadius: '8px',
                    background: 'white', fontSize: '13px', fontWeight: 500, color: '#475569',
                    cursor: refreshing ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
                  }}
                >
                  <RefreshCw size={13} style={{ animation: refreshing ? 'spin 0.7s linear infinite' : 'none' }} />
                  Refresh
                </button>
              </div>

              {payouts.length === 0 ? (
                <div
                  id="empty-state-payouts"
                  style={{
                    textAlign: 'center', padding: '56px 32px',
                    border: '2px dashed #E2E8F0', borderRadius: '12px',
                    background: '#FAFBFC',
                  }}
                >
                  <p style={{ color: '#94A3B8', fontSize: '13px', margin: 0 }}>
                    No payouts yet. Submit a payout to see entries appear here.
                  </p>
                </div>
              ) : (
                <div id="payout-table" style={{ borderRadius: '10px', border: '1px solid #F1F5F9', overflow: 'hidden' }}>
                  <div style={{
                    display: 'grid', gridTemplateColumns: '120px 140px 1fr 160px',
                    padding: '10px 16px', background: '#F8FAFC',
                    borderBottom: '1px solid #F1F5F9',
                  }}>
                    {['Status', 'Amount', 'Payout ID', 'Date'].map(h => (
                      <span key={h} style={{ fontSize: '11px', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {h}
                      </span>
                    ))}
                  </div>

                  {payouts.map((entry, i) => {
                    const b = badge(entry.status === 'SUCCESS' ? 'CREDIT' : entry.status === 'FAILED' ? 'DEBIT' : 'HOLD')
                    return (
                      <div
                        key={entry.payout_id}
                        style={{
                          display: 'grid', gridTemplateColumns: '120px 140px 1fr 160px',
                          padding: '13px 16px',
                          borderBottom: i < payouts.length - 1 ? '1px solid #F8FAFC' : 'none',
                          alignItems: 'center',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = '#FAFBFE'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: '5px',
                          padding: '3px 10px', borderRadius: '100px',
                          background: b.bg, color: b.color, border: `1px solid ${b.border}`,
                          fontSize: '12px', fontWeight: 600,
                        }}>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: b.dot, flexShrink: 0 }} />
                          {entry.status}
                        </span>
                        <span style={{
                          fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                          color: '#0F172A', fontSize: '14px',
                        }}>
                          {fmt(-entry.amount_paise)}
                        </span>
                        <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#94A3B8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {entry.payout_id ? entry.payout_id : '—'}
                        </span>
                        <span style={{ fontSize: '13px', color: '#64748B' }}>
                          {fmtDate(entry.created_at)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Ledger tab ── */}
          {tab === 'ledger' && (
            <div style={{ padding: '32px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0F172A', margin: 0 }}>Ledger Entries</h2>
                <button
                  id="refresh-ledger"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '7px 14px', border: '1px solid #E2E8F0', borderRadius: '8px',
                    background: 'white', fontSize: '13px', fontWeight: 500, color: '#475569',
                    cursor: refreshing ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
                  }}
                >
                  <RefreshCw size={13} style={{ animation: refreshing ? 'spin 0.7s linear infinite' : 'none' }} />
                  Refresh
                </button>
              </div>

              {ledger.length === 0 ? (
                <div
                  id="empty-state"
                  style={{
                    textAlign: 'center', padding: '56px 32px',
                    border: '2px dashed #E2E8F0', borderRadius: '12px',
                    background: '#FAFBFC',
                  }}
                >
                  <div style={{
                    width: '52px', height: '52px', borderRadius: '14px',
                    background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 16px',
                  }}>
                    <Inbox size={24} color="#818CF8" />
                  </div>
                  <p style={{ fontWeight: 600, color: '#334155', fontSize: '15px', margin: '0 0 6px' }}>
                    No ledger entries yet
                  </p>
                  <p style={{ color: '#94A3B8', fontSize: '13px', margin: 0 }}>
                    Submit a payout to see entries appear here.
                  </p>
                </div>
              ) : (
                <div id="ledger-table" style={{ borderRadius: '10px', border: '1px solid #F1F5F9', overflow: 'hidden' }}>
                  {/* Table header */}
                  <div style={{
                    display: 'grid', gridTemplateColumns: '120px 140px 1fr 160px',
                    padding: '10px 16px', background: '#F8FAFC',
                    borderBottom: '1px solid #F1F5F9',
                  }}>
                    {['Type', 'Amount', 'Payout ID', 'Date'].map(h => (
                      <span key={h} style={{ fontSize: '11px', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {h}
                      </span>
                    ))}
                  </div>

                  {/* Rows */}
                  {ledger.map((entry, i) => {
                    const b = badge(entry.entry_type)
                    const isPos = entry.amount_paise >= 0
                    return (
                      <div
                        key={entry.id}
                        style={{
                          display: 'grid', gridTemplateColumns: '120px 140px 1fr 160px',
                          padding: '13px 16px',
                          borderBottom: i < ledger.length - 1 ? '1px solid #F8FAFC' : 'none',
                          alignItems: 'center',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = '#FAFBFE'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        {/* Badge */}
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: '5px',
                          padding: '3px 10px', borderRadius: '100px',
                          background: b.bg, color: b.color, border: `1px solid ${b.border}`,
                          fontSize: '12px', fontWeight: 600,
                        }}>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: b.dot, flexShrink: 0 }} />
                          {entry.entry_type}
                        </span>

                        {/* Amount */}
                        <span style={{
                          fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                          color: isPos ? '#059669' : '#DC2626', fontSize: '14px',
                        }}>
                          {fmt(entry.amount_paise)}
                        </span>

                        {/* Payout ID */}
                        <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#94A3B8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {entry.payout_id ? entry.payout_id : '—'}
                        </span>

                        {/* Date */}
                        <span style={{ fontSize: '13px', color: '#64748B' }}>
                          {fmtDate(entry.created_at)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────

function StatCard({ label, value, icon, iconBg, valueColor }) {
  return (
    <div style={{
      background: 'white', borderRadius: '14px',
      border: '1px solid #E8ECF4',
      padding: '20px 24px',
      boxShadow: '0 2px 12px rgba(79,70,229,0.05), 0 1px 3px rgba(0,0,0,0.03)',
      transition: 'box-shadow 0.2s, transform 0.2s',
    }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 6px 24px rgba(79,70,229,0.10)'; e.currentTarget.style.transform = 'translateY(-1px)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 2px 12px rgba(79,70,229,0.05)'; e.currentTarget.style.transform = '' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <p style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#94A3B8', margin: '0 0 10px' }}>
            {label}
          </p>
          <p style={{ fontSize: '30px', fontWeight: 700, color: valueColor, margin: 0, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.5px' }}>
            {value}
          </p>
        </div>
        <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {icon}
        </div>
      </div>
    </div>
  )
}

function TabButton({ active, icon, label, onClick, badge: badgeProp }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: '7px',
        padding: '14px 20px', background: 'none', border: 'none',
        cursor: 'pointer',
        borderBottom: active ? '2px solid #4F46E5' : '2px solid transparent',
        color: active ? '#4F46E5' : '#64748B',
        fontWeight: active ? 600 : 500, fontSize: '14px',
        transition: 'all 0.15s', marginBottom: '-1px',
      }}
    >
      {icon}
      {label}
      {badgeProp && (
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: '4px',
          padding: '2px 7px', borderRadius: '100px', fontSize: '10px', fontWeight: 700,
          background: '#EEF2FF', color: '#4F46E5', border: '1px solid #C7D2FE',
          letterSpacing: '0.04em',
        }}>
          <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#4F46E5', animation: 'pulse 1s infinite' }} />
          {badgeProp}
        </span>
      )}
    </button>
  )
}

function Spinner() {
  return (
    <span style={{
      width: '16px', height: '16px', borderRadius: '50%',
      border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white',
      display: 'inline-block', animation: 'spin 0.7s linear infinite',
    }} />
  )
}

// ── Shared field styles ─────────────────────────────────────────────
const labelStyle = {
  display: 'flex', alignItems: 'center', gap: '5px',
  fontSize: '13px', fontWeight: 600, color: '#374151',
  marginBottom: '7px',
}

const fieldStyle = {
  width: '100%', padding: '11px 14px',
  border: '1.5px solid #E2E8F0', borderRadius: '9px',
  fontSize: '14px', color: '#0F172A', background: '#FAFBFF',
  outline: 'none', transition: 'border-color 0.15s, box-shadow 0.15s',
  fontFamily: 'Inter, system-ui, sans-serif', boxSizing: 'border-box',
}

const applyFocus = (el) => {
  el.style.borderColor = '#4F46E5'
  el.style.boxShadow = '0 0 0 3px rgba(79,70,229,0.12)'
  el.style.background = 'white'
}

const applyBlur = (el) => {
  el.style.borderColor = '#E2E8F0'
  el.style.boxShadow = 'none'
  el.style.background = '#FAFBFF'
}
