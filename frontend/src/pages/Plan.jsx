import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ExternalLink, RotateCw, Sparkles } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import CourseTag from '../components/CourseTag'
import SessionCheck from '../components/SessionCheck'

const time = (iso) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

export default function Plan() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)
  const [checking, setChecking] = useState(null)

  const load = () => api.get('/api/plan').then(setData)
  useEffect(() => { load() }, [tick])

  const act = async (key, fn) => {
    setBusy(key)
    try { await fn(); await load() } finally { setBusy(null) }
  }

  if (!data) return <p className="text-base text-slate-600">Loading your plan…</p>

  const byDay = {}
  data.sessions.filter((s) => !s.past || s.done).forEach((s) => {
    const day = new Date(s.start).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
    ;(byDay[day] ||= []).push(s)
  })

  return (
    <div className="space-y-7">
      {checking && <SessionCheck session={checking} onClose={() => { setChecking(null); load() }} />}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-2xl font-extrabold flex-1">Study plan</h1>
        <button className="btn-primary" disabled={busy === 'all'} onClick={() => act('all', () => api.post('/api/plan/all'))}>
          <Sparkles size={18} /> {busy === 'all' ? 'Planning…' : 'Plan everything'}
        </button>
        <a href="https://calendar.google.com" target="_blank" rel="noreferrer" className="btn-ghost">
          Google Calendar <ExternalLink size={17} />
        </a>
      </div>

      <section className="card">
        <h2 className="text-xl font-bold">What to focus on first</h2>
        <p className="text-slate-600 mb-4">Ranked by the agent: days left × quiz weight × lecture difficulty × how ready you are.</p>
        <ol className="divide-y divide-slate-100">
          {data.priorities.map((p, i) => (
            <li key={p.id} className="flex items-center gap-4 py-3">
              <span className="w-9 h-9 rounded-full bg-brand text-white font-bold grid place-items-center tabular shrink-0">{i + 1}</span>
              <Link to={`/prep/${p.id}`} className="flex-1 min-w-0 group">
                <span className="block font-semibold text-base group-hover:underline underline-offset-4">{p.title}</span>
                <CourseTag name={p.course_name} color={p.color} className="text-sm !font-medium !text-slate-600" />
              </Link>
              <span className="text-slate-600 tabular hidden md:block">due {fmtDate(p.due)}</span>
              <button className="btn-ghost !py-1.5 text-sm" disabled={busy === p.id}
                onClick={() => act(p.id, () => api.post(`/api/plan/${p.id}/replan`))}>
                <RotateCw size={16} className={busy === p.id ? 'animate-spin' : ''} /> Re-plan
              </button>
            </li>
          ))}
        </ol>
      </section>

      {Object.keys(byDay).length === 0 && <div className="card text-slate-700">No study sessions yet. Click “Plan everything”.</div>}
      {Object.entries(byDay).map(([day, sessions]) => (
        <section key={day}>
          <h2 className="text-xl font-bold mb-3">{day}</h2>
          <div className="card !p-0 divide-y divide-slate-100">
            {sessions.map((s) => (
              <div key={s.event_id} className={`flex items-center gap-4 px-5 py-3.5 ${s.done ? 'opacity-55' : ''}`}>
                <span className="w-3.5 h-3.5 rounded-full shrink-0" style={{ background: s.color }} />
                <span className="font-bold text-base tabular w-36 shrink-0">{time(s.start)}–{time(s.end)}</span>
                <Link to={`/prep/${s.assessment_id}`} className="flex-1 min-w-0 font-medium hover:underline underline-offset-4">
                  {s.title.replace(/^📘\s*/, '')}
                </Link>
                {s.done ? (
                  <span className="text-emerald-700 font-bold flex items-center gap-1.5"><Check size={18} /> Done</span>
                ) : (
                  <button className="btn-ghost !py-1.5" onClick={() => setChecking(s)}>
                    <Check size={17} /> Mark done
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
