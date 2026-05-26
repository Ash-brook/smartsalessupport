import { useRef, useState } from 'react'
import { api, type IntakeResult } from '../api'

// Simulates the company's incoming-mail feed: drop real complaint files and the system
// reads them, files them as inbox emails, and runs the AI pipeline. No typing allowed.
export default function Intake() {
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<IntakeResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const out = await api.intake(Array.from(fileList))
      setResults((prev) => [...out, ...prev]) // newest first
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="intake">
      <h2>Mail Intake</h2>
      <p className="muted">
        Drop incoming customer complaints — Outlook <code>.msg</code>, Gmail <code>.eml</code>,
        PDFs, or images/screenshots. The system reads each one, files it, and runs it through
        the AI pipeline. Handled drafts appear under <strong>Agent Review</strong>.
      </p>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''} ${busy ? 'busy' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".eml,.msg,.pdf,.png,.jpg,.jpeg,.gif,.webp,message/rfc822,application/pdf,image/*"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="dropzone-icon">📥</div>
        {busy ? (
          <p>Reading and processing…</p>
        ) : (
          <p>
            <strong>Drag &amp; drop complaint files here</strong>
            <br />
            or click to browse
          </p>
        )}
      </div>

      {error && <p className="intake-error">⚠ {error}</p>}

      {results.length > 0 && (
        <div className="card intake-results">
          <h4>Processed files</h4>
          <table className="audit-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Read as</th>
                <th>Customer</th>
                <th>Intent</th>
                <th>Routing</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td className="subject-cell">{r.filename}</td>
                  <td>{r.source}</td>
                  <td>{r.customer_name ?? '—'}</td>
                  <td>{r.intent ?? '—'}</td>
                  <td>
                    {r.outcome && (
                      <span className={`badge tag ${r.outcome === 'auto' ? 'auto' : 'hitl'}`}>
                        {r.outcome === 'auto' ? 'Auto-sent' : 'To review'}
                      </span>
                    )}
                  </td>
                  <td>
                    {r.ok ? (
                      <span className="badge conf">✓ processed</span>
                    ) : (
                      <span className="badge flag" title={r.error ?? ''}>
                        ✗ {r.error}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
