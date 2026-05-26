import { useEffect, useState } from 'react'
import { api, type Metrics } from '../api'

function pct(x: number) {
  return `${Math.round(x * 100)}%`
}

const ACTION_LABELS: Record<string, string> = {
  auto_approved: 'Auto-approved',
  drafted: 'Sent to review',
  approved: 'Approved',
  edited_and_approved: 'Edited & approved',
  rejected: 'Rejected',
}

export default function Dashboard() {
  const [m, setM] = useState<Metrics | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.metrics().then(setM).catch((e) => setError((e as Error).message))
  }, [])

  if (error) return <div className="dashboard"><p className="muted">Failed to load: {error}</p></div>
  if (!m) return <div className="dashboard"><p className="muted">Loading metrics…</p></div>

  const maxCat = Math.max(1, ...m.category_breakdown.map((c) => c.count))

  return (
    <div className="dashboard">
      <h2>Manager Dashboard</h2>

      <div className="kpi-grid">
        <Kpi label="Zero-touch resolution" value={pct(m.zero_touch_rate)} sub={`${m.auto_approved} auto of ${m.processed}`} accent="green" />
        <Kpi label="HITL intervention" value={pct(m.hitl_rate)} sub={`${m.hitl} need review`} accent="amber" />
        <Kpi label="Agent edit rate" value={pct(m.edit_rate)} sub="of approved drafts" />
        <Kpi label="Rejection rate" value={pct(m.rejection_rate)} sub="of agent decisions" accent="red" />
        <Kpi label="Pending review" value={String(m.pending)} sub="in queue now" />
        <Kpi label="Sent" value={String(m.sent)} sub="replies dispatched" />
      </div>

      <div className="dash-cols">
        <div className="card">
          <h4>Category breakdown (predicted intent)</h4>
          {m.category_breakdown.map((c) => (
            <div key={c.intent} className="bar-row">
              <span className="bar-label">{c.intent}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(c.count / maxCat) * 100}%` }} />
              </div>
              <span className="bar-val">{c.count}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <h4>Top rejection reasons</h4>
          {m.top_rejection_reasons.length === 0 && <p className="muted">No rejections yet.</p>}
          {m.top_rejection_reasons.map((r) => (
            <div key={r.reason} className="kv">
              <span>{r.reason}</span>
              <b>{r.count}</b>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h4>Recent activity (audit log)</h4>
        <table className="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Agent</th>
              <th>Customer</th>
              <th>Subject</th>
            </tr>
          </thead>
          <tbody>
            {m.audit_log.map((row, i) => (
              <tr key={i}>
                <td>{new Date(row.timestamp).toLocaleString()}</td>
                <td>
                  <span className={`badge action ${row.action}`}>
                    {ACTION_LABELS[row.action] ?? row.action}
                  </span>
                </td>
                <td>{row.agent_id ?? '—'}</td>
                <td>{row.customer_name}</td>
                <td className="subject-cell">{row.subject}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string
  sub?: string
  accent?: 'green' | 'amber' | 'red'
}) {
  return (
    <div className={`kpi ${accent ?? ''}`}>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}
