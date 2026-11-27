import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlarmClock, AlertTriangle, Bot, CalendarClock, Gauge } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import CourseTag from '../components/CourseTag'
import DailyBrief from '../components/DailyBrief'
import { CoachDashboard } from '../components/Coach'
import DeadlineCard from '../components/DeadlineCard'

// Dashboard, top to bottom: quick numbers -> today's brief -> what the agents need -> deadlines
export default function Dashboard() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [course, setCourse] = useState('all')

  const load = () => api.get('/api/dashboard').then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  useEffect(() => { load() }, [tick])

  const items = data?.items || []
  // Only show courses that have something coming up; old terms stay out of the way
  const activeIds = new Set(items.map((i) => i.course_id))
  const courses = (data?.courses || []).filter((c) => activeIds.has(c.id))
  const week = items.filter((i) => i.days_left !== null && i.days_left >= 0 && i.days_left <= 7)
  const overdue = items.filter((i) => i.days_left !== null && i.days_left < 0)
  const ready = week.length ? Math.round(week.reduce((n, i) => n + (i.readiness?.score || 0), 0) / week.length) : null
  const shown = course === 'all' ? items : items.filter((i) => i.course_id === course)
  const hour = new Date().getHours()
  const hello = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const stats = [
    { icon: CalendarClock, label: 'Due this week', value: week.length, tone: 'text-indigo-700 bg-indigo-50' },
    { icon: AlarmClock, label: 'Overdue', value: overdue.length, tone: overdue.length ? 'text-rose-700 bg-rose-50' : 'text-slate-600 bg-slate-100' },
    { icon: Gauge, label: 'Avg readiness', value: ready === null ? '–' : `${ready}%`, tone: ready !== null && ready < 50 ? 'text-amber-700 bg-amber-50' : 'text-emerald-700 bg-emerald-50' },
  ]
  const chip = (on) => `px-3.5 py-1.5 rounded-full text-sm font-semibold border transition ${on ? 'bg-slate-900 text-white border-slate-900' : 'bg-white border-slate-200 hover:border-slate-400'}`

  return (
    <div className="space-y-8">
      {/* 1. Greeting + quick numbers */}
      <section className="flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-[14rem]">
          <p className="text-slate-500 font-semibold">{new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          <h2 className="text-3xl font-extrabold tracking-tight">{hello}</h2>
        </div>
        <div className="grid grid-cols-3 gap-3 w-full sm:w-auto">
          {stats.map(({ icon: Icon, label, value, tone }) => (
            <div key={label} className="sp-stat border-slate-200 sm:min-w-[8.5rem]">
              <span className={`inline-grid place-items-center w-8 h-8 rounded-lg ${tone}`}><Icon size={17} /></span>
              <p className="text-2xl font-extrabold mt-1.5 tabular">{value}</p>
              <p className="text-xs font-semibold text-slate-500">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Today's brief */}
      <section className="space-y-3">
        <h3 className="sp-section-title">Today</h3>
        <DailyBrief tick={tick} />
      </section>

      {/* 3. What the agents need from you, and what they did overnight */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="sp-section-title flex-1">From your agents</h3>
          <Link to="/agents" className="text-sm font-semibold text-brand inline-flex items-center gap-1.5 hover:underline"><Bot size={16} /> Meet the team</Link>
        </div>
        <CoachDashboard />
      </section>

      {/* 4. Deadlines, filterable by course */}
      <section className="space-y-4">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h3 className="sp-section-title">Upcoming deadlines</h3>
          <span className="text-sm text-slate-500">Most urgent first{data?.last_sync && ` · synced ${fmtDate(data.last_sync)}`}</span>
        </div>
        {courses.length > 0 && (
          <div className="flex gap-2 flex-wrap items-center" role="tablist" aria-label="Filter by course">
            <button role="tab" aria-selected={course === 'all'} onClick={() => setCourse('all')} className={chip(course === 'all')}>All courses</button>
            {courses.map((c) => (
              <button key={c.id} role="tab" aria-selected={course === c.id} onClick={() => setCourse(c.id)} className={chip(course === c.id)}>
                <CourseTag name={c.name} color={c.color_hex} />
              </button>
            ))}
            {course !== 'all' && <Link to={`/course/${course}`} className="text-sm font-semibold text-brand ml-1 hover:underline">Open course →</Link>}
          </div>
        )}
        {error && (
          <div className="card !bg-red-50 !border-red-300 text-red-900 flex gap-3 items-center">
            <AlertTriangle size={22} /> {error}. Showing the last data I had.
          </div>
        )}
        {!data && !error && <p className="text-base text-slate-600">Loading deadlines…</p>}
        {data && items.length === 0 && (
          <div className="card text-base text-slate-700">No deadlines yet. The agent is syncing your Classroom; watch the activity feed.</div>
        )}
        <div className="space-y-4">
          {shown.map((it) => <DeadlineCard key={it.id} item={it} onChange={load} />)}
        </div>
      </section>
    </div>
  )
}
