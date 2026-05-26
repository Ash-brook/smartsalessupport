import type { QueueItem } from '../api'

function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}

interface Props {
  items: QueueItem[]
  total: number
  selectedId: string | null
  onSelect: (id: string) => void
}

export default function Queue({ items, total, selectedId, onSelect }: Props) {
  return (
    <aside className="queue">
      <div className="queue-head">
        <h2>Review Queue</h2>
        <span className="queue-count">{total} waiting</span>
      </div>
      <ul className="queue-list">
        {items.map((it) => (
          <li
            key={it.draft_id}
            className={`queue-row ${selectedId === it.draft_id ? 'selected' : ''}`}
            onClick={() => onSelect(it.draft_id)}
          >
            <div className="queue-row-top">
              <span className="cust">{it.customer_name}</span>
              <span className="wait">{timeAgo(it.received_at)}</span>
            </div>
            <div className="queue-row-subject">{it.subject}</div>
            <div className="queue-row-meta">
              {it.intent && <span className="badge intent">{it.intent}</span>}
              {it.confidence != null && (
                <span className="badge conf">{Math.round(it.confidence * 100)}%</span>
              )}
              <span className={`badge tag ${it.status === 'pending' ? 'hitl' : 'auto'}`}>
                {it.status === 'pending' ? 'HITL' : it.status}
              </span>
              {it.flags.length > 0 && <span className="badge flag">⚑ {it.flags.length}</span>}
            </div>
          </li>
        ))}
        {items.length === 0 && <li className="queue-empty">Queue is empty 🎉</li>}
      </ul>
    </aside>
  )
}
