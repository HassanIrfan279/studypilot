import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, daysLeftLabel, fmtDate, urgencyClass } from '../api'
import ReadinessRing from './ReadinessRing'

export default function DeadlineCard({ item, onChange }) {
  const [due, setDue] = useState('')
  const [saving, setSaving] = useState(false)

  const saveDue = async () => {
    if (!due) return
    setSaving(true)
    try { await api.post(`/api/items/${item.id}/due`, { due }); onChange?.() } finally { setSaving(false) }
  }

  return (
    <div className="card !p-0 overflow-hidden flex">
      <div className="w-2 shrink-0" style={{ background: item.color }} />
      <div className="p-5 flex-1 flex gap-5 items-center min-w-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-bold" style={{ color: item.color }}>{item.course_name}</span>
            <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded-full ${item.kind === 'quiz' ? 'bg-fuchsia-100 text-fuchsia-800' : 'bg-slate-100 text-slate-700'}`}>
              {item.kind}
            </span>
            {item.source === 'announcement' && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800" title="Found by Gemini inside an announcement">
                🔎 found in announcement
              </span>
            )}
          </div>
          <h3 className="text-xl font-bold truncate">{item.title}</h3>
          <p className="text-slate-600">{fmtDate(item.due)}</p>
          {!item.due ? (
            <div className="mt-3 p-3 bg-amber-50 border border-amber-300 rounded-xl flex gap-2 items-center flex-wrap">
              <span className="font-semibold text-amber-900">❓ When is this due? I won't guess.</span>
              <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)}
                className="border rounded-lg px-2 py-1" />
              <button className="btn-primary !py-1" onClick={saveDue} disabled={saving}>Save</button>
            </div>
          ) : (
            <div className="flex gap-2 mt-3 flex-wrap">
              <Link to={`/prep/${item.id}`} className="btn-primary !py-1.5">📚 Prep pack</Link>
              <Link to={`/prep/${item.id}?quiz=1`} className="btn-ghost !py-1.5">✏️ Practice quiz</Link>
              <Link to={`/panic/${item.id}`} className="btn-ghost !py-1.5 !text-red-700">🚨 Panic mode</Link>
            </div>
          )}
        </div>
        <div className="flex flex-col items-center gap-2 shrink-0">
          <span className={`px-3 py-1 rounded-full text-sm font-bold ${urgencyClass(item.days_left)}`}>
            {daysLeftLabel(item.days_left)}
          </span>
          <ReadinessRing score={item.readiness?.score || 0} />
        </div>
      </div>
    </div>
  )
}
