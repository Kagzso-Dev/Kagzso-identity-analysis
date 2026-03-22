import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import logo from './assets/logo.png';

const rawBaseUrl = (import.meta.env.VITE_API_URL || '').replace(/\/$/, "");
const API_URL = `${rawBaseUrl || ''}/api`;
const CREDENTIALS = { username: 'Kagzso', password: 'Kagzso@123' };

const MAX_ATTEMPTS = 5;
const LOCKOUT_SECONDS = 30;

function Login({ onLogin }) {
  const [username, setUsername]       = useState('');
  const [password, setPassword]       = useState('');
  const [showPassword, setShowPass]   = useState(false);
  const [submitting, setSubmitting]   = useState(false);
  const [error, setError]             = useState('');
  const [shaking, setShaking]         = useState(false);
  const [attempts, setAttempts]       = useState(0);
  const [lockoutLeft, setLockoutLeft] = useState(0);
  const usernameRef = useRef(null);

  // Auto-focus username on mount
  useEffect(() => { usernameRef.current?.focus(); }, []);

  // Lockout countdown
  useEffect(() => {
    if (lockoutLeft <= 0) return;
    const id = setTimeout(() => setLockoutLeft(s => s - 1), 1000);
    return () => clearTimeout(id);
  }, [lockoutLeft]);

  const shake = () => {
    setShaking(true);
    setTimeout(() => setShaking(false), 520);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (lockoutLeft > 0 || submitting) return;

    if (!username.trim() || !password) {
      setError('Please fill in all fields.');
      shake();
      return;
    }

    setSubmitting(true);
    setError('');

    // Simulate a short auth delay — feels trustworthy, prevents timing attacks
    setTimeout(() => {
      if (username === CREDENTIALS.username && password === CREDENTIALS.password) {
        sessionStorage.setItem('kagzso_auth', '1');
        setAttempts(0);
        onLogin();
      } else {
        const next = attempts + 1;
        setAttempts(next);
        if (next >= MAX_ATTEMPTS) {
          setLockoutLeft(LOCKOUT_SECONDS);
          setError(`Too many failed attempts. Locked for ${LOCKOUT_SECONDS}s.`);
        } else {
          setError(`Invalid credentials. ${MAX_ATTEMPTS - next} attempt${MAX_ATTEMPTS - next !== 1 ? 's' : ''} remaining.`);
        }
        shake();
        setSubmitting(false);
      }
    }, 700);
  };

  const locked = lockoutLeft > 0;

  return (
    <div className="login-page">
      <div className={`login-card${shaking ? ' login-shake' : ''}`}>

        {/* Brand */}
        <div className="login-brand">
          <div className="logo-circle" style={{ margin: '0 auto 18px', width: '84px', height: '84px' }}>
            <img src={logo} alt="Kagzso Logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
          <h1 className="logo-text" style={{ fontSize: '34px', marginBottom: '6px' }}>Kagzso</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '10px', letterSpacing: '3.5px', textTransform: 'uppercase' }}>
            Identity Analysis Platform
          </p>
        </div>

        {/* Divider */}
        <div style={{ height: '1px', background: 'var(--card-border)', margin: '24px 0' }} />

        <form onSubmit={handleSubmit} className="login-form" noValidate>

          {/* Username */}
          <div className="login-field">
            <label htmlFor="l-user">Username</label>
            <input
              id="l-user"
              ref={usernameRef}
              type="text"
              autoComplete="username"
              placeholder="Enter username"
              value={username}
              disabled={locked || submitting}
              onChange={e => { setUsername(e.target.value); setError(''); }}
            />
          </div>

          {/* Password */}
          <div className="login-field">
            <label htmlFor="l-pass">Password</label>
            <div className="password-wrap">
              <input
                id="l-pass"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter password"
                value={password}
                disabled={locked || submitting}
                onChange={e => { setPassword(e.target.value); setError(''); }}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowPass(v => !v)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                disabled={locked || submitting}
              >
                {showPassword ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          {/* Error / Lockout */}
          {(error || locked) && (
            <div className={`login-error${locked ? ' login-error--locked' : ''}`}>
              {locked
                ? <>Locked — retry in <strong>{lockoutLeft}s</strong></>
                : error}
            </div>
          )}

          {/* Attempt dots */}
          {attempts > 0 && !locked && (
            <div className="attempt-dots" aria-label={`${attempts} failed attempt(s)`}>
              {Array.from({ length: MAX_ATTEMPTS }).map((_, i) => (
                <span key={i} className={`attempt-dot${i < attempts ? ' attempt-dot--used' : ''}`} />
              ))}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className={`login-btn${submitting ? ' login-btn--loading' : ''}`}
            disabled={locked || submitting}
            aria-busy={submitting}
          >
            {submitting ? (
              <span className="login-spinner" aria-hidden="true" />
            ) : locked ? (
              `Locked (${lockoutLeft}s)`
            ) : (
              'Sign In'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

const LOADER_PHASES = [
  'Authenticating session...',
  'Loading OCR engine...',
  'Initializing workspace...',
  'Almost ready...',
];

function AppLoader({ logo }) {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setPhase(p => (p + 1 < LOADER_PHASES.length ? p + 1 : p));
    }, 600);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="loader-screen">
      <div className="loader-content">
        <div className="loader-ring">
          <div className="logo-circle loader-logo">
            <img src={logo} alt="Kagzso" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        </div>
        <h1 className="logo-text" style={{ fontSize: '32px', marginTop: '24px', marginBottom: '6px' }}>
          Kagzso
        </h1>
        <p className="loader-phase">{LOADER_PHASES[phase]}</p>
        <div className="loader-bar-track" style={{ marginTop: '28px' }}>
          <div className="loader-bar-fill" />
        </div>
        <div className="loader-dots">
          {LOADER_PHASES.map((_, i) => (
            <span key={i} className={`loader-dot${i <= phase ? ' loader-dot--active' : ''}`} />
          ))}
        </div>
      </div>
    </div>
  );
}

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => sessionStorage.getItem('kagzso_auth') === '1');
  const [isLoading, setIsLoading] = useState(false);
  const [files, setFiles] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [serverStatus, setServerStatus] = useState('checking');
  const [showWebcam, setShowWebcam] = useState(false);
  const [webcamError, setWebcamError] = useState(null);

  const imageInputRef = useRef(null);
  const pdfInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const abortControllerRef = useRef(null);
  const serverStatusRef = useRef('checking');

  useEffect(() => {
    let timeoutId = null;
    let cancelled = false;
    const checkServer = async () => {
      try {
        const res = await fetch(`${API_URL}/health`);
        const status = res.ok ? 'online' : 'offline';
        if (!cancelled) { serverStatusRef.current = status; setServerStatus(status); }
      } catch {
        if (!cancelled) { serverStatusRef.current = 'offline'; setServerStatus('offline'); }
      }
      if (!cancelled) {
        timeoutId = setTimeout(checkServer, 10_000); // Check every 10s to catch cold starts faster
      }
    };
    checkServer();
    return () => { cancelled = true; clearTimeout(timeoutId); };
  }, []);

  const startWebcam = async () => {
    setWebcamError(null);
    setShowWebcam(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch {
      setWebcamError('Camera access denied or not available on this device.');
    }
  };

  useEffect(() => {
    if (showWebcam && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [showWebcam]);

  const stopWebcam = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setShowWebcam(false);
    setWebcamError(null);
  };

  const captureFromWebcam = () => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d').drawImage(videoRef.current, 0, 0);
    canvas.toBlob(blob => {
      const file = new File([blob], `scan_${Date.now()}.jpg`, { type: 'image/jpeg' });
      setFiles(prev => [...prev, file]);
      stopWebcam();
    }, 'image/jpeg', 0.95);
  };

  const addFiles = (newFiles) => {
    setFiles(prev => [...prev, ...Array.from(newFiles)]);
    setError(null);
  };

  const handleBatchUpload = async () => {
    if (files.length === 0) return;
    setProcessing(true);
    setError(null);
    setProgress({ current: 0, total: files.length });
    abortControllerRef.current = new AbortController();
    const newResults = [];
    for (let i = 0; i < files.length; i++) {
      if (abortControllerRef.current.signal.aborted) break;
      setProgress({ current: i + 1, total: files.length });
      const formData = new FormData();
      formData.append('file', files[i]);
      try {
        const response = await axios.post(`${API_URL}/scan`, formData, {
          signal: abortControllerRef.current.signal
        });
        newResults.push({ ...response.data, filename: files[i].name });
      } catch (err) {
        if (axios.isCancel(err)) break;
        newResults.push({ filename: files[i].name, error: 'Failed to extract' });
      }
    }
    setResults(prev => [...prev, ...newResults]);
    setFiles([]);
    setProcessing(false);
  };

  const cancelProcessing = () => {
    if (abortControllerRef.current) abortControllerRef.current.abort();
  };

  const downloadExcel = () => window.open(`${API_URL}/export`, '_blank');

  const clearHistory = async () => {
    try {
      await axios.delete(`${API_URL}/clear`);
      setResults([]);
      setError(null);
    } catch {
      setResults([]);
      setError('Note: UI cleared, but server might still have data.');
    }
  };

  const clearQueue = () => {
    setFiles([]);
    if (imageInputRef.current) imageInputRef.current.value = '';
    if (pdfInputRef.current) pdfInputRef.current.value = '';
  };

  const options = [
    {
      id: 'live',
      title: 'Live Scan',
      subtitle: 'Real-time camera scanning',
      icon: (
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M23 7l-7 5 7 5V7z"/>
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
      ),
      action: startWebcam,
    },
    {
      id: 'image',
      title: 'Upload Image',
      subtitle: 'Select JPG or PNG from gallery',
      icon: (
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21 15 16 10 5 21"/>
        </svg>
      ),
      action: () => imageInputRef.current?.click(),
    },
    {
      id: 'pdf',
      title: 'Upload PDF',
      subtitle: 'Select a PDF document',
      icon: (
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
      ),
      action: () => pdfInputRef.current?.click(),
    },
  ];

  if (!isLoggedIn) {
    return <Login onLogin={() => {
      setIsLoading(true);
      setTimeout(() => { setIsLoading(false); setIsLoggedIn(true); }, 2400);
    }} />;
  }

  if (isLoading) {
    return <AppLoader logo={logo} />;
  }

  return (
    <div className="container">

      {/* ── Top bar: logo + sign-out in one row ── */}
      <header className="top-bar">
        <div className="brand-row">
          <div className="logo-circle top-bar-logo">
            <img src={logo} alt="Kagzso Logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
          <div className="brand-text">
            <h1 className="logo-text">Kagzso</h1>
            <div className="status-row">
              <span className={`status-dot status-dot--${serverStatus}`} />
              <span className="status-label">System {serverStatus}</span>
            </div>
          </div>
        </div>

        <button
          onClick={() => { sessionStorage.removeItem('kagzso_auth'); setIsLoggedIn(false); }}
          className="btn-secondary signout-btn"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
          Sign Out
        </button>
      </header>

      <p className="subtitle">AUTOMATED BATCH DOCUMENT ANALYZER</p>

      {/* Hidden file inputs */}
      <input ref={imageInputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
        onChange={e => { addFiles(e.target.files); e.target.value = ''; }} />
      <input ref={pdfInputRef} type="file" accept="application/pdf" multiple hidden
        onChange={e => { addFiles(e.target.files); e.target.value = ''; }} />

      {/* Webcam Modal */}
      {showWebcam && (
        <div className="webcam-overlay" onClick={e => e.target === e.currentTarget && stopWebcam()}>
          <div className="webcam-modal">
            <div className="webcam-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ef4444', boxShadow: '0 0 8px #ef4444', animation: 'pulse 1.5s infinite' }}></div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '700' }}>Live Scan</h3>
              </div>
              <button className="btn-secondary" onClick={stopWebcam}
                style={{ width: 'auto', padding: '8px 16px', fontSize: '14px' }}>
                Close
              </button>
            </div>
            {webcamError ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#f87171', fontSize: '14px' }}>
                {webcamError}
              </div>
            ) : (
              <video ref={videoRef} autoPlay playsInline muted className="webcam-video" />
            )}
            <button
              onClick={captureFromWebcam}
              disabled={!!webcamError}
              className={!webcamError ? 'btn-primary-active' : ''}
              style={{ marginTop: '16px' }}
            >
              Capture Document
            </button>
          </div>
        </div>
      )}

      {/* Main Card */}
      <div className="card">
        <div style={{ marginBottom: '24px' }}>
          <h2>AI Identity Scanner</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
            Scan or upload any Indian identity document
          </p>
        </div>

        <div className="option-cards">
          {options.map(opt => (
            <div key={opt.id} className="option-card" onClick={opt.action} role="button" tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && opt.action()}>
              <div className="option-icon">{opt.icon}</div>
              <div className="option-info">
                <div className="option-title">{opt.title}</div>
                <div className="option-subtitle">{opt.subtitle}</div>
              </div>
              <svg className="option-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          ))}
        </div>

        {/* Queue Banner */}
        {files.length > 0 && !processing && (
          <div className="queue-banner">
            <span style={{ color: 'var(--text-primary)', fontWeight: '600', fontSize: '14px' }}>
              {files.length} document{files.length > 1 ? 's' : ''} queued
            </span>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleBatchUpload}
                disabled={serverStatus === 'offline'}
                className={serverStatus !== 'offline' ? 'btn-primary-active' : ''}
                style={{ width: 'auto', padding: '10px 24px', fontSize: '14px' }}
              >
                {serverStatus === 'offline' ? 'Server Offline' : 'Analyze'}
              </button>
              <button onClick={clearQueue} className="btn-secondary"
                style={{ width: 'auto', padding: '10px 16px', fontSize: '14px' }}>
                Clear
              </button>
            </div>
          </div>
        )}

        {processing && (
          <div className="progress-container">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Processing documents...</span>
              <span style={{ fontSize: '13px', color: 'var(--primary)', fontWeight: 'bold' }}>
                {progress.current} / {progress.total}
              </span>
            </div>
            <div className="progress-track">
              <div className="progress-bar" style={{ width: `${(progress.current / progress.total) * 100}%` }}></div>
            </div>
            <button onClick={cancelProcessing} className="btn-secondary"
              style={{ marginTop: '16px', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
              Cancel Analysis
            </button>
          </div>
        )}

        {error && (
          <div style={{ padding: '16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '12px', color: '#f87171', marginTop: '20px', fontSize: '14px' }}>
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="card">
          <div className="history-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
            <div>
              <h2 style={{ marginBottom: '4px' }}>Session History</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: 0 }}>
                Successfully processed <span style={{ color: 'var(--primary)', fontWeight: 'bold' }}>{results.length}</span> documents
              </p>
            </div>
            <div className="actions" style={{ display: 'flex', gap: '12px' }}>
              <button onClick={downloadExcel} className="btn-success" style={{ width: 'auto', padding: '12px 24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Export Excel
                </div>
              </button>
              <button onClick={clearHistory} className="btn-secondary" style={{ width: 'auto', padding: '12px 24px' }}>
                Clear History
              </button>
            </div>
          </div>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Type</th>
                  <th>Name</th>
                  <th>Father's Name</th>
                  <th>ID Number</th>
                  <th>DOB</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {results.map((res, idx) => (
                  <tr key={idx}>
                    <td data-label="Filename" style={{ color: 'var(--text-primary)', fontWeight: '500' }}>{res.filename}</td>
                    <td data-label="Type">
                      <span style={{
                        padding: '4px 8px',
                        background:
                          res.document_type === 'PAN CARD' ? 'rgba(251, 146, 60, 0.15)' :
                          res.document_type === 'VOTER ID' ? 'rgba(167, 139, 250, 0.15)' :
                          res.document_type === 'AADHAAR' ? 'rgba(0, 242, 255, 0.2)' :
                          res.document_type === 'DRIVING LICENSE' ? 'rgba(34, 197, 94, 0.15)' :
                          res.document_type === 'PASSPORT' ? 'rgba(236, 72, 153, 0.15)' :
                          'rgba(255, 255, 255, 0.05)',
                        borderRadius: '6px',
                        color:
                          res.document_type === 'PAN CARD' ? '#fb923c' :
                          res.document_type === 'VOTER ID' ? '#a78bfa' :
                          res.document_type === 'AADHAAR' ? 'var(--primary)' :
                          res.document_type === 'DRIVING LICENSE' ? '#22c55e' :
                          res.document_type === 'PASSPORT' ? '#ec4899' :
                          'var(--text-secondary)',
                        fontSize: '11px', fontWeight: '800', letterSpacing: '0.5px'
                      }}>
                        {res.document_type || 'UNKNOWN'}
                      </span>
                    </td>
                    <td data-label="Name">{res.name || '-'}</td>
                    <td data-label="Father's Name" style={{ fontSize: '13px' }}>{res.father_name || '-'}</td>
                    <td data-label="ID Number">{res.id_number || '-'}</td>
                    <td data-label="DOB">{res.dob || '-'}</td>
                    <td data-label="Location" style={{ fontSize: '12px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {res.address || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ textAlign: 'center', padding: '24px 0 8px', color: 'var(--text-secondary)', fontSize: '12px', letterSpacing: '0.5px' }}>
        Supports: Aadhaar · PAN · Passport · Driving License · Voter ID
      </div>

    </div>
  );
}

export default App;
