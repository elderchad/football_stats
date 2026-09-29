import { useEffect, useState } from 'react'
import { fetchAudit, type AuditReport } from './api'

export default function DataAudit() {
  const [report, setReport] = useState<AuditReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = (refresh: boolean) => {
    setLoading(true)
    setError(null)
    fetchAudit(refresh)
      .then(setReport)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => load(false), [])

  return (
    <section>
      <p className="lede">
        Every check compares the data behind the charts against a structural expectation or a
        second, independently published source. The first run downloads reference files and
        can take a minute.
      </p>

      <div className="controls">
        {report && (
          <span className="audit-summary">
            <span className="audit-badge pass">{report.summary.pass} pass</span>
            <span className="audit-badge warn">{report.summary.warn} warn</span>
            <span className="audit-badge fail">{report.summary.fail} fail</span>
            {report.summary.error > 0 && (
              <span className="audit-badge error">{report.summary.error} error</span>
            )}
            <span className="audit-meta">Generated {new Date(report.generated_at).toLocaleString()}</span>
          </span>
        )}
        <div className="button-group">
          <button type="button" onClick={() => load(true)} disabled={loading}>
            {loading ? 'Running…' : 'Re-run audit'}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {!report && loading && <p className="note">Running audit…</p>}

      {report && (
        <>
          <div className="audit-list">
            {report.checks.map((check) => (
              <details key={check.id} className={`audit-check ${check.status}`} open={check.status === 'fail' || check.status === 'error'}>
                <summary>
                  <span className={`audit-badge ${check.status}`}>{check.status}</span>
                  <span className="audit-title">{check.title}</span>
                  <span className="audit-meta">
                    {check.scope} · {check.checked.toLocaleString()} checked · {check.issue_count} issue
                    {check.issue_count === 1 ? '' : 's'}
                  </span>
                </summary>
                {check.note && <p className="audit-note">{check.note}</p>}
                {check.issues.length > 0 && (
                  <ul className="audit-issues">
                    {check.issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                    {check.issue_count > check.issues.length && (
                      <li>…and {check.issue_count - check.issues.length} more</li>
                    )}
                  </ul>
                )}
              </details>
            ))}
          </div>

          <h3 className="audit-heading">What cannot be verified</h3>
          <ul className="audit-limitations">
            {report.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
