import React, { useState, useEffect } from 'react';
import './App.css';

// The API URL — your FastAPI backend
const API_URL = 'http://localhost:8000';

// Status badge colors based on failure category
const CATEGORY_COLORS = {
  dependency_error: '#e74c3c',
  test_failure: '#e67e22',
  build_error: '#c0392b',
  infrastructure_error: '#8e44ad',
  auth_error: '#d35400',
  timeout: '#16a085',
  configuration_error: '#2980b9',
  unknown: '#7f8c8d'
};

// Confidence badge colors
const CONFIDENCE_COLORS = {
  high: '#27ae60',
  medium: '#f39c12',
  low: '#e74c3c'
};

function FailureCard({ failure, onAnalyze }) {
  const [analyzing, setAnalyzing] = useState(false);
  const [agentResult, setAgentResult] = useState(null);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const response = await fetch(
        `${API_URL}/failures/${failure.id}/analyze`,
        { method: 'POST' }
      );
      const data = await response.json();
      setAgentResult(data.agent_analysis);
    } catch (err) {
      setAgentResult('Agent analysis failed. Please try again.');
    }
    setAnalyzing(false);
  };

  return (
    <div className="failure-card">
      <div className="card-header">
        <div className="card-title">
          <span className="repo-name">{failure.repository}</span>
          <span
            className="category-badge"
            style={{
              backgroundColor:
                CATEGORY_COLORS[failure.failure_category] || '#7f8c8d'
            }}
          >
            {failure.failure_category || 'unknown'}
          </span>
        </div>
        <div className="card-meta">
          <span>Run #{failure.run_id}</span>
          <span>Branch: {failure.branch}</span>
          <span
            className="status-badge"
            style={{
              backgroundColor:
                failure.status === 'analyzed' ? '#27ae60' : '#f39c12'
            }}
          >
            {failure.status}
          </span>
        </div>
      </div>

      <div className="card-body">
        {failure.root_cause && (
          <div className="analysis-section">
            <div className="section-label">
              Root Cause
              {failure.confidence && (
                <span
                  className="confidence-badge"
                  style={{
                    backgroundColor:
                      CONFIDENCE_COLORS[failure.confidence] || '#7f8c8d'
                  }}
                >
                  {failure.confidence} confidence
                </span>
              )}
            </div>
            <p className="section-content">{failure.root_cause}</p>
          </div>
        )}

        {failure.suggested_fix && (
          <div className="analysis-section">
            <div className="section-label">Suggested Fix</div>
            <p className="section-content">{failure.suggested_fix}</p>
          </div>
        )}

        {failure.additional_context && (
          <div className="analysis-section">
            <div className="section-label">Additional Context</div>
            <p className="section-content">{failure.additional_context}</p>
          </div>
        )}

        <div className="card-footer">
          <div className="timestamps">
            <span>
              Processed:{' '}
              {failure.processed_at
                ? new Date(failure.processed_at).toLocaleString()
                : 'N/A'}
            </span>
          </div>

          <button
            className="analyze-btn"
            onClick={handleAnalyze}
            disabled={analyzing}
          >
            {analyzing ? 'Agent Analyzing...' : 'Run Agent Analysis'}
          </button>
        </div>

        {agentResult && (
          <div className="agent-result">
            <div className="section-label">Agent Analysis</div>
            <p className="section-content">{agentResult}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function StatsBar({ failures }) {
  const total = failures.length;
  const analyzed = failures.filter(f => f.status === 'analyzed').length;
  const categories = {};
  failures.forEach(f => {
    const cat = f.failure_category || 'unknown';
    categories[cat] = (categories[cat] || 0) + 1;
  });
  const topCategory = Object.entries(categories).sort(
    (a, b) => b[1] - a[1]
  )[0];

  return (
    <div className="stats-bar">
      <div className="stat">
        <div className="stat-number">{total}</div>
        <div className="stat-label">Total Failures</div>
      </div>
      <div className="stat">
        <div className="stat-number">{analyzed}</div>
        <div className="stat-label">Analyzed</div>
      </div>
      <div className="stat">
        <div className="stat-number">{total - analyzed}</div>
        <div className="stat-label">Pending</div>
      </div>
      <div className="stat">
        <div className="stat-number">
          {topCategory ? topCategory[0].replace('_', ' ') : 'N/A'}
        </div>
        <div className="stat-label">Top Failure Type</div>
      </div>
    </div>
  );
}

function App() {
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchFailures = async () => {
    try {
      const response = await fetch(`${API_URL}/failures`);
      if (!response.ok) throw new Error('Failed to fetch failures');
      const data = await response.json();
      setFailures(data.failures || []);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError('Cannot connect to PipeLine AI backend. Is it running?');
    }
    setLoading(false);
  };

  // Fetch on mount and every 30 seconds
  useEffect(() => {
    fetchFailures();
    const interval = setInterval(fetchFailures, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">PipeLine AI</h1>
          <span className="app-subtitle">
            AI-powered CI/CD failure analysis
          </span>
        </div>
        <div className="header-right">
          {lastRefresh && (
            <span className="last-refresh">
              Last updated: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button className="refresh-btn" onClick={fetchFailures}>
            Refresh
          </button>
        </div>
      </header>

      <main className="app-main">
        {loading && (
          <div className="loading">Loading failures...</div>
        )}

        {error && (
          <div className="error-banner">{error}</div>
        )}

        {!loading && !error && (
          <>
            <StatsBar failures={failures} />

            <div className="section-header">
              <h2>Recent Failures</h2>
              <span className="failure-count">
                {failures.length} failure{failures.length !== 1 ? 's' : ''}
              </span>
            </div>

            {failures.length === 0 ? (
              <div className="empty-state">
                <p>No failures recorded yet.</p>
                <p>
                  Send a webhook to{' '}
                  <code>POST /webhook/github</code> to get started.
                </p>
              </div>
            ) : (
              <div className="failures-grid">
                {failures.map(failure => (
                  <FailureCard
                    key={failure.id}
                    failure={failure}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;