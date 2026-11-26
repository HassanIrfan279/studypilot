import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate } from '../api'
import { useLive } from '../live'

export default function Plan() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)

  const load = () => api.get('/api/plan').then(setData)
  useEffect(() => { load() }, [tick])

  const act = async (key, fn) => {
    setBusy(key)
    try { await fn(); await load() } finally { setBusy(null) }
  }

  if (!data) return <p className="text-lg">Loading…</p>

  // group sessions by day
  const byDay = {}
  data.sessions.forEach((s) => {
    const day = new Date(s.start).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' })
    ;(byDay[day] ||= []).push(s)
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-4xl font-extrabold flex-1">📅 Study plan</h1>
        <button className="btn-primary" disabled={busy === 'all'}
          onClick={() => act('all', () => api.post('/api/plan/all'))}>
          {busy === 'all' ? 'Planning…' : '✨ Plan everything'}
        </button>
        <a href="https://calendar.google.com" target="_blank" rel="noreferrer" className="btn-ghost">Open Google Calendar ↗</a>
      </div>

      <section className="card">
        <h2 className="text-xl font-bold mb-3">🧠 Agent's priority order</h2>
        <ol className="space-y-2">
          {data.priorities.map((p, i) => (
            <li key={p.id} className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-brand text-white font-bold flex items-center justify-center">{i + 1}</span>
              <Link to={`/prep/${p.id}`} className="font-semibold flex-1 hover:underline">{p.course_name} — {p.title}</Link>
              <span className="text-slate-500 text-sm">due {fmtDate(p.due)}</span>
              <button className="btn-ghost !py-1 text-sm" disabled={busy === p.id}
                onClick={() => act(p.id, () => api.post(`/api/plan/${p.id}/replan`))}>
                {busy === p.id ? '…' : '↻ Re-plan'}
              </button>
            </li>
          ))}
        </ol>
      </section>

      {Object.keys(byDay).length === 0 && <div className="card text-slate-600">No study sessions yet. Click “Plan everything”.</div>}
      {Object.entries(byDay).map(([day, sessions]) => (
        <section key={day}>
          <h2 className="text-xl font-bold mb-2">{day}</h2>
          <div className="space-y-2">
            {sessions.map((s) => (
              <div key={s.event_id} className={`card !py-3 flex items-center gap-4 ${s.done ? 'opacity-60' : ''}`}
                style={{ borderLeft: `8px solid ${s.color}` }}>
                <span className="font-mono font-bold text-lg w-32">
                  {new Date(s.start).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}–
                  {new Date(s.end).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                </span>
                <Link to={`/prep/${s.assessment_id}`} className="flex-1 font-semibold hover:underline">{s.title}</Link>
                {s.done ? (
                  <span className="text-emerald-700 font-bold">✓ Done</span>
                ) : (
                  <button className="btn-ghost !py-1" disabled={busy === s.event_id}
                    onClick={() => act(s.event_id, () => api.post(`/api/sessions/${s.event_id}/done`))}>
                    Mark done
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
