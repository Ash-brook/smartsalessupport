import { useCallback, useEffect, useState } from 'react'
import { api, type Action, type DetailResponse, type QueueItem } from '../api'
import Queue from '../components/Queue'
import ReviewDetail from '../components/ReviewDetail'

const POLL_MS = 10_000 // PRD 7.3: queue auto-refreshes every 10s

export default function Review() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<DetailResponse | null>(null)
  const [editedBody, setEditedBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const loadQueue = useCallback(async () => {
    try {
      const res = await api.queue('pending')
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setToast((e as Error).message)
    }
  }, [])

  // Initial load + polling. loadQueue only setState()s inside its async .then, so this is
  // the legitimate "subscribe to an external system" effect pattern, not a sync cascade.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadQueue()
    const id = setInterval(loadQueue, POLL_MS)
    return () => clearInterval(id)
  }, [loadQueue])

  // Load detail when a row is selected. (Detail is cleared explicitly in runAction.)
  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    api
      .detail(selectedId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        setEditedBody(d.draft.final_body ?? d.draft.body)
      })
      .catch((e) => !cancelled && setToast((e as Error).message))
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  async function runAction(action: Action, extra: Record<string, string> = {}) {
    if (!selectedId) return
    setBusy(true)
    try {
      const res = await api.act(selectedId, { action, ...extra })
      showToast(`Draft ${res.status} (audit ${res.audit_event_id.slice(0, 8)})`)
      setSelectedId(null)
      setDetail(null)
      await loadQueue()
    } catch (e) {
      showToast((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="review">
      <Queue items={items} total={total} selectedId={selectedId} onSelect={setSelectedId} />
      {detail ? (
        <ReviewDetail
          detail={detail}
          editedBody={editedBody}
          onEditBody={setEditedBody}
          onApprove={() => runAction('approve')}
          onEditApprove={() => runAction('edit', { edited_body: editedBody })}
          onReject={(reason) => runAction('reject', { rejection_reason: reason })}
          busy={busy}
        />
      ) : (
        <section className="detail empty-detail">
          <p>Select an email from the queue to review its AI draft.</p>
        </section>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
