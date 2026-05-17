import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import './App.css'

import AuthScreen from './components/AuthScreen'
import Dashboard from './components/Dashboard'

/* ── Protected Route Middleware ────────────── */
function ProtectedRoute({ children, isAuthenticated }) {
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [merchantId, setMerchantId] = useState(localStorage.getItem('merchant_id'))
  const isAuthenticated = !!token

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

  return (
    <Routes>
      {/* ── Auth Routes ─────────────────────── */}
      <Route
        path="/login"
        element={
          isAuthenticated
            ? <Navigate to="/" replace />
            : <AuthScreen onLogin={handleLogin} />
        }
      />
      <Route
        path="/signup"
        element={
          isAuthenticated
            ? <Navigate to="/" replace />
            : <AuthScreen onLogin={handleLogin} />
        }
      />

      {/* ── Protected Dashboard Route ────────── */}
      <Route
        path="/"
        element={
          <ProtectedRoute isAuthenticated={isAuthenticated}>
            <Dashboard
              token={token}
              merchantId={merchantId}
              onLogout={handleLogout}
            />
          </ProtectedRoute>
        }
      />

      {/* ── Catch-all → redirect to login ────── */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

export default App
