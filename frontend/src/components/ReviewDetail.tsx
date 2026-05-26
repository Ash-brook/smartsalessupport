import { diffWords } from 'diff'
import { useState } from 'react'
import type { DetailResponse } from '../api'

// Words that should be visually flagged in the original email (PRD 7.1).
const FLAG_WORDS = [
  'refund',
  'legal',
  'lawyer',
  'sue',
  'complaint',
  'unacceptable',
  'terrible',
  'cancel',
  'urgent',
]
const FLAG_RE = new RegExp(`\\b(${FLAG_WORDS.join('|')})\\b`, 'gi')

function HighlightedEmail({ text }: { text: string }) {
  const parts = text.split(FLAG_RE)
  return (
    <p className="email-body">
      {parts.map((part, i) =>
        FLAG_WORDS.includes(part.toLowerCase()) ? (
          <mark key={i}>{part}</mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  )
}

function Diff({ original, edited }: { original: string; edited: string }) {
  const changes = diffWords(original, edited)
  if (changes.every((c) => !c.added && !c.removed)) {
    return <p className="diff-none">No edits yet.</p>
  }
  return (
    <p className="diff">
      {changes.map((c, i) => (
        <span key={i} className={c.added ? 'added' : c.removed ? 'removed' : ''}>
          {c.value}
        </span>
      ))}
    </p>
  )
}

interface Props {
  detail: DetailResponse
  editedBody: string
  onEditBody: (v: string) => void
  onApprove: () => void
  onEditApprove: () => void
  onReject: (reason: string) => void
  busy: boolean
}

export default function ReviewDetail({
  detail,
  editedBody,
  onEditBody,
  onApprove,
  onEditApprove,
  onReject,
  busy,
}: Props) {
  const { draft, email, context } = detail
  const [rejectOpen, setRejectOpen] = useState(false)
  const [reason, setReason] = useState('')
  const edited = editedBody !== draft.body

  return (
    <section className="detail">
      {/* Centre column: original email + draft editor */}
      <div className="detail-main">
        <div className="panel email-panel">
          <div className="panel-head">
            <h3>Original Email</h3>
            <span className="from">
              {email.customer_name} &lt;{email.customer_email}&gt;
            </span>
          </div>
          <div className="email-subject">{email.subject}</div>
          <HighlightedEmail text={email.body_text} />
        </div>

        <div className="panel draft-panel">
          <div className="panel-head">
            <h3>AI Draft</h3>
            <span className="charcount">{editedBody.length} chars{edited ? ' · edited' : ''}</span>
          </div>
          <textarea
            className="draft-editor"
            value={editedBody}
            onChange={(e) => onEditBody(e.target.value)}
            spellCheck
          />
          <div className="diff-box">
            <span className="diff-label">Diff vs. original draft</span>
            <Diff original={draft.body} edited={editedBody} />
          </div>

          <div className="action-bar">
            <button className="btn approve" disabled={busy} onClick={onApprove}>
              Approve
            </button>
            <button className="btn edit" disabled={busy || !edited} onClick={onEditApprove}>
              Edit &amp; Approve
            </button>
            <button className="btn reject" disabled={busy} onClick={() => setRejectOpen(true)}>
              Reject
            </button>
          </div>
        </div>
      </div>

      {/* Right column: metadata sidebar */}
      <aside className="sidebar">
        <div className="card">
          <h4>Customer</h4>
          <div className="kv">
            <span>Name</span>
            <b>{context.customer.name}</b>
          </div>
          <div className="kv">
            <span>Tier</span>
            <b className={`tier ${context.customer.account_tier.toLowerCase()}`}>
              {context.customer.account_tier}
            </b>
          </div>
          <div className="kv">
            <span>Lifetime value</span>
            <b>${context.customer.lifetime_value_usd.toLocaleString()}</b>
          </div>
          <div className="kv">
            <span>Country</span>
            <b>{context.customer.country}</b>
          </div>
        </div>

        <div className="card">
          <h4>Classification</h4>
          <div className="kv">
            <span>Intent</span>
            <b>{draft.intent ?? '—'}</b>
          </div>
          <div className="kv">
            <span>Confidence</span>
            <b>{draft.confidence != null ? `${Math.round(draft.confidence * 100)}%` : '—'}</b>
          </div>
          <div className="kv">
            <span>Model flagged</span>
            <b>{draft.requires_human_review ? 'Yes' : 'No'}</b>
          </div>
          {draft.reasoning && <p className="reasoning">{draft.reasoning}</p>}
          {draft.flags.length > 0 && (
            <div className="flags">
              {draft.flags.map((f) => (
                <span key={f} className="badge flag">
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h4>Recent Orders</h4>
          {context.recent_orders.map((o) => (
            <div key={o.order_id} className="order">
              <span>{o.product_name}</span>
              <span className={`badge order-status ${o.status.toLowerCase()}`}>{o.status}</span>
              <span className="amount">${o.amount_usd}</span>
            </div>
          ))}
          {context.recent_orders.length === 0 && <p className="muted">No orders</p>}
        </div>
      </aside>

      {rejectOpen && (
        <div className="modal-backdrop" onClick={() => setRejectOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Reject draft</h3>
            <p className="muted">A reason is required — it’s recorded in the audit trail.</p>
            <textarea
              autoFocus
              value={reason}
              placeholder="e.g. Draft missed the refund policy detail"
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setRejectOpen(false)}>
                Cancel
              </button>
              <button
                className="btn reject"
                disabled={!reason.trim() || busy}
                onClick={() => {
                  onReject(reason.trim())
                  setRejectOpen(false)
                  setReason('')
                }}
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
