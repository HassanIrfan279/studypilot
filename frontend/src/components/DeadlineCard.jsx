import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, CircleHelp, PencilLine, Search, Siren } from 'lucide-react'
import { api, daysLeftLabel, fmtDate, urgencyClass } from '../api'
import CourseTag from './CourseTag'
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
    <article className="card flex gap-6 items-center">
      <div className="flex-1 min-w-0">
        <h3 className="text-2xl font-bold leading-tight">{item.title}</h3>
        <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap mt-2 text-[16px]">
          <CourseTag name={item.course_name} color={item.color} />
          <span className={`text-xs font-bold uppercase tracking-wide px-2 py-1 rounded-md ${item.kind === 'quiz' ? 'bg-fuchsia-100 text-fuchsia-900' : 'bg-slate-100 text-slate-700'}`}>
            {item.kind}
          </span>
          {item.due && <span className="text-slate-700 tabular">{fmtDate(item.due)}</span>}
          {item.source === 'announcement' && (
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-amber-900 bg-amber-100 px-2 py-1 rounded-md"
              title={item.description || 'Found by Gemini inside a class announcement'}>
              <Search size={15} /> Found in announcement
            </span>
          )}
        </div>

        {!item.due ? (
          <div className="mt-4 p-3.5 bg-amber-50 border border-amber-300 rounded-xl flex gap-3 items-center flex-wrap">
            <CircleHelp size={20} className="text-amber-800" />
            <span className="font-semibold text-amber-950">When is this due? I won't guess.</span>
            <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)}
              aria-label="Due date" className="border border-amber-300 bg-white rounded-lg px-2 py-1" />
            <button className="btn-primary !py-1.5" onClick={saveDue} disabled={saving || !due}>
              {saving ? 'Planning…' : 'Save & plan'}
            </button>
          </div>
        ) : (
          <div className="flex gap-2 mt-4 flex-wrap">
            <Link to={`/prep/${item.id}`} className="btn-primary !py-1.5"><BookOpen size={18} /> Prep pack</Link>
            <Link to={`/prep/${item.id}?quiz=1`} className="btn-ghost !py-1.5"><PencilLine size={18} /> Practice quiz</Link>
            <Link to={`/panic/${item.id}`} className="btn-ghost !py-1.5 !text-red-700"><Siren size={18} /> Panic mode</Link>
          </div>
        )}
      </div>
      <div className="flex flex-col items-center gap-3 shrink-0">
        <span className={`px-3 py-1 rounded-full text-sm font-bold tabular ${urgencyClass(item.days_left)}`}>
          {daysLeftLabel(item.days_left)}
        </span>
        <ReadinessRing score={item.readiness?.score || 0} />
      </div>
    </article>
  )
}
