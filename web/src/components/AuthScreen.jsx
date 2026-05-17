import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { googleLogin } from '../lib/auth';
import { Eye, EyeOff, AlertCircle, Layers, Shield, Zap, Clock, ArrowRight } from 'lucide-react';

export default function AuthScreen({ onLogin }) {
  const location = useLocation();
  const navigate = useNavigate();
  const isSignup = location.pathname === '/signup';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      setLoading(true);
      setError('');
      const data = await googleLogin(credentialResponse.credential);
      onLogin(data);
      navigate('/');
    } catch (err) {
      setError(err.message || 'Google login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Login failed');
      onLogin(data);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, name })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Signup failed');
      onLogin(data);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#F8F7FF' }}>

      {/* ── Left Decorative Panel ── */}
      <div style={{
        display: 'none',
        width: '50%',
        background: 'linear-gradient(135deg, #4F46E5 0%, #6D28D9 100%)',
        position: 'relative',
        overflow: 'hidden',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px',
      }} className="auth-left-panel">
        {/* Geometric blobs */}
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.12 }} viewBox="0 0 600 900" preserveAspectRatio="xMidYMid slice">
          <circle cx="80" cy="120" r="220" fill="white" />
          <circle cx="520" cy="180" r="160" fill="white" />
          <circle cx="300" cy="700" r="280" fill="white" />
          <circle cx="30" cy="800" r="130" fill="white" />
          <polygon points="430,40 490,76 490,148 430,184 370,148 370,76" fill="white" opacity="0.6" />
          <polygon points="140,420 200,456 200,528 140,564 80,528 80,456" fill="white" opacity="0.6" />
          <polygon points="530,520 590,556 590,628 530,664 470,628 470,556" fill="white" opacity="0.4" />
        </svg>

        {/* Content */}
        <div style={{ position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: '340px' }}>
          {/* Logo mark */}
          <div style={{
            width: '72px', height: '72px', borderRadius: '20px',
            background: 'rgba(255,255,255,0.18)',
            backdropFilter: 'blur(12px)',
            border: '1px solid rgba(255,255,255,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '20px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          }}>
            <Layers style={{ width: '32px', height: '32px', color: 'white' }} />
          </div>
          <h1 style={{ color: 'white', fontSize: '28px', fontWeight: 700, letterSpacing: '-0.5px', margin: 0 }}>Playto</h1>
          <p style={{ color: 'rgba(199,210,254,0.9)', fontSize: '14px', marginTop: '4px', marginBottom: '48px' }}>Payout Engine</p>

          {/* Feature list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
            {[
              { icon: Shield, title: 'Secure by default', desc: 'Bank-grade encryption on every transaction' },
              { icon: Zap, title: 'Real-time processing', desc: 'Payouts dispatched within seconds' },
              { icon: Clock, title: 'Idempotent operations', desc: 'Safe retry on every API call' },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                <div style={{
                  width: '38px', height: '38px', borderRadius: '10px', flexShrink: 0,
                  background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon style={{ width: '16px', height: '16px', color: 'white' }} />
                </div>
                <div>
                  <p style={{ color: 'white', fontWeight: 600, fontSize: '14px', margin: 0 }}>{title}</p>
                  <p style={{ color: 'rgba(199,210,254,0.8)', fontSize: '13px', marginTop: '2px' }}>{desc}</p>
                </div>
              </div>
            ))}
          </div>

          <p style={{ color: 'rgba(199,210,254,0.6)', fontSize: '12px', marginTop: '48px', textAlign: 'center' }}>
            Trusted by merchants across India
          </p>
        </div>
      </div>

      {/* ── Right Auth Panel ── */}
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px',
        minHeight: '100vh',
      }}>
        <div style={{ width: '100%', maxWidth: '420px' }}>

          {/* Mobile logo */}
          <div className="auth-mobile-logo" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '32px' }}>
            <div style={{
              width: '36px', height: '36px', borderRadius: '10px',
              background: 'linear-gradient(135deg, #4F46E5, #6D28D9)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Layers style={{ width: '18px', height: '18px', color: 'white' }} />
            </div>
            <span style={{ fontWeight: 700, fontSize: '18px', color: '#0F172A' }}>Playto</span>
          </div>

          {/* Heading */}
          <div style={{ marginBottom: '28px' }}>
            <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.5px', margin: 0, lineHeight: 1.2 }}>
              {isSignup ? 'Create your account' : 'Welcome back'}
            </h2>
            <p style={{ color: '#64748B', fontSize: '15px', marginTop: '8px' }}>
              {isSignup ? 'Fill in your details to get started.' : 'Enter your credentials to access your dashboard.'}
            </p>
          </div>

          {/* Segmented Tab Control */}
          <div style={{
            display: 'flex',
            background: '#F1F5F9',
            borderRadius: '12px',
            padding: '4px',
            marginBottom: '24px',
            gap: '4px',
          }}>
            <Link
              to="/login"
              style={{
                flex: 1, textAlign: 'center',
                padding: '9px 16px',
                borderRadius: '9px',
                fontSize: '14px',
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'all 0.15s ease',
                ...((!isSignup) ? {
                  background: 'white',
                  color: '#0F172A',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
                } : {
                  color: '#64748B',
                }),
              }}
            >
              Sign In
            </Link>
            <Link
              to="/signup"
              style={{
                flex: 1, textAlign: 'center',
                padding: '9px 16px',
                borderRadius: '9px',
                fontSize: '14px',
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'all 0.15s ease',
                ...(isSignup ? {
                  background: 'white',
                  color: '#0F172A',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
                } : {
                  color: '#64748B',
                }),
              }}
            >
              Sign Up
            </Link>
          </div>

          {/* Error Banner */}
          {error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '12px 16px', borderRadius: '10px',
              background: '#FEF2F2', border: '1px solid #FECACA',
              marginBottom: '20px',
            }}>
              <AlertCircle style={{ width: '16px', height: '16px', color: '#DC2626', flexShrink: 0 }} />
              <p style={{ fontSize: '14px', color: '#DC2626', margin: 0 }}>{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={isSignup ? handleSignup : handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {isSignup && (
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
                  Full Name
                </label>
                <input
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  required
                  style={inputStyle}
                  onFocus={e => Object.assign(e.target.style, inputFocusStyle)}
                  onBlur={e => Object.assign(e.target.style, inputBlurStyle)}
                />
              </div>
            )}

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
                Email address
              </label>
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                style={inputStyle}
                onFocus={e => Object.assign(e.target.style, inputFocusStyle)}
                onBlur={e => Object.assign(e.target.style, inputBlurStyle)}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  style={{ ...inputStyle, paddingRight: '44px' }}
                  onFocus={e => Object.assign(e.target.style, inputFocusStyle)}
                  onBlur={e => Object.assign(e.target.style, inputBlurStyle)}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  style={{
                    position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                    color: '#94A3B8', display: 'flex', alignItems: 'center',
                  }}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '13px 24px', marginTop: '4px',
                background: loading ? '#A5B4FC' : 'linear-gradient(135deg, #4F46E5 0%, #6D28D9 100%)',
                color: 'white', border: 'none', borderRadius: '10px',
                fontSize: '15px', fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
                boxShadow: loading ? 'none' : '0 4px 16px rgba(79,70,229,0.35)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                transition: 'all 0.2s ease',
              }}
            >
              {loading ? (
                <>
                  <span style={{
                    width: '16px', height: '16px', borderRadius: '50%',
                    border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white',
                    animation: 'spin 0.7s linear infinite', display: 'inline-block',
                  }} />
                  {isSignup ? 'Creating account…' : 'Signing in…'}
                </>
              ) : (
                <>
                  {isSignup ? 'Create Account' : 'Sign In'}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '24px 0' }}>
            <div style={{ flex: 1, height: '1px', background: '#E2E8F0' }} />
            <span style={{ fontSize: '12px', color: '#94A3B8', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              or continue with
            </span>
            <div style={{ flex: 1, height: '1px', background: '#E2E8F0' }} />
          </div>

          {/* Google Button */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => setError('Google login was cancelled or failed.')}
              text={isSignup ? 'signup_with' : 'signin_with'}
              size="large"
              theme="outline"
              shape="rectangular"
              width="380"
            />
          </div>

          {/* Footer link */}
          <p style={{ marginTop: '24px', textAlign: 'center', fontSize: '14px', color: '#64748B' }}>
            {isSignup ? (
              <>Already have an account?{' '}
                <Link to="/login" style={{ color: '#4F46E5', fontWeight: 600, textDecoration: 'none' }}>
                  Sign in
                </Link>
              </>
            ) : (
              <>Don't have an account?{' '}
                <Link to="/signup" style={{ color: '#4F46E5', fontWeight: 600, textDecoration: 'none' }}>
                  Sign up
                </Link>
              </>
            )}
          </p>
        </div>
      </div>

      {/* Spin keyframe */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (min-width: 1024px) {
          .auth-left-panel { display: flex !important; }
          .auth-mobile-logo { display: none !important; }
        }
      `}</style>
    </div>
  );
}

const inputStyle = {
  width: '100%', padding: '11px 14px',
  border: '1.5px solid #E2E8F0', borderRadius: '9px',
  fontSize: '15px', color: '#0F172A', background: 'white',
  outline: 'none', transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
  fontFamily: 'Inter, system-ui, sans-serif',
  boxSizing: 'border-box',
};

const inputFocusStyle = {
  borderColor: '#4F46E5',
  boxShadow: '0 0 0 3px rgba(79,70,229,0.12)',
};

const inputBlurStyle = {
  borderColor: '#E2E8F0',
  boxShadow: 'none',
};
