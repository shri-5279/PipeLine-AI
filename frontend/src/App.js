import React, { useState, useEffect } from 'react';
import './App.css';

const API_URL = 'http://localhost:8000';

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

const CONFIDENCE_COLORS = {
  high: '#27ae60',
  medium: '#f39c12',
  low: '#e74c3c'
};

function formatAgentAnalysis(text) {
  if (!text) return [];

  // Split on numbered steps like "1.", "2.", etc or newlines
  // This turns a wall of text into clean readable steps
  const lines = text
    .replace(/\\n/g, '\n')
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 0);

  // Group into numbered steps and regular sentences
  const steps = [];
  let currentStep = null;

  lines.forEach(line => {
    // Matches "1." or "1)" at start of line
    const stepMatch = line.match(/^(\d+)[.)]\s+(.+)/);
    if (stepMatch) {
      if (currentStep) steps.push(currentStep);
      currentStep = { type: 'step', number: stepMatch[1], text: stepMatch[2] };
    } else if (line.startsWith('Additionally') || line.startsWith('Note') || line.startsWith('If')) {
      if (currentStep) { steps.push(currentStep); currentStep = null; }
      steps.push({ type: 'note', text: line });
    } else {
      if (currentStep) {
        currentStep.text += ' ' + line;
      } else {
        steps.push({ type: 'paragraph', text: line });
      }
    }
  });

  if (currentStep) steps.push(currentStep);
  return steps;
}

function AgentAnalysisDisplay({ text }) {
  const parts = formatAgentAnalysis(text);

  return (
    <div className="agent-analysis-content">
      {parts.map((part, i) => {
        if (part.type === 'step') {
          return (
            <div key={i} className="agent-step">
              <span className="step-number">{part.number}</span>
              <span className="step-text">{part.text}</span>
            </div>
          );
        }
        if (part.type === 'note') {
          return (
            <div key={i} className="agent-note">
              <span className="note-icon">💡</span>
              <span>{part.text}</span>
            </div>
          );
        }
        return (
          <p key={i} className="agent-paragraph">{part.text}</p>
        );
      })}
    </div>
  );
}

function FailureCard({ failure }) {
  const [analyzing, setAnalyzing] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const [expanded, setExpanded] = useState(true);

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
      <div className="card-header" onClick={() => setExpanded(!expanded)}>
        <div className="card-title">
          <span className="expand-icon">{expanded ? '▾' : '▸'}</span>
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

      {expanded && (
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
              Processed:{' '}
              {failure.processed_at
                ? new Date(failure.processed_at).toLocaleString()
                : 'N/A'}
            </div>
            <button
              className="analyze-btn"
              onClick={handleAnalyze}
              disabled={analyzing}
            >
              {analyzing ? '⟳ Agent Analyzing...' : '⚡ Run Agent Analysis'}
            </button>
          </div>

          {agentResult && (
            <div className="agent-result">
              <div className="agent-result-header">
                <span className="agent-icon">🤖</span>
                <span className="section-label" style={{ margin: 0 }}>
                  Agent Analysis
                </span>
              </div>
              <AgentAnalysisDisplay text={agentResult} />
            </div>
          )}
        </div>
      )}
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
        <div className="stat-number" style={{ color: '#27ae60' }}>
          {analyzed}
        </div>
        <div className="stat-label">Analyzed</div>
      </div>
      <div className="stat">
        <div
          className="stat-number"
          style={{ color: total - analyzed > 0 ? '#f39c12' : '#27ae60' }}
        >
          {total - analyzed}
        </div>
        <div className="stat-label">Pending</div>
      </div>
      <div className="stat">
        <div className="stat-number" style={{ fontSize: '16px', textTransform: 'capitalize' }}>
          {topCategory ? topCategory[0].replace(/_/g, ' ') : 'N/A'}
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
      if (!response.ok) throw new Error('Failed to fetch');
      const data = await response.json();
      setFailures(data.failures || []);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError('Cannot connect to PipeLine AI backend. Is it running?');
    }
    setLoading(false);
  };

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
        {loading && <div className="loading">Loading failures...</div>}

        {error && <div className="error-banner">{error}</div>}

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
                  <FailureCard key={failure.id} failure={failure} />
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