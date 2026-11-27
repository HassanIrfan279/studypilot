import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import CourseTag from '../components/CourseTag'
import DailyBrief from '../components/DailyBrief'
import { CoachDashboard } from '../components/Coach'
import DeadlineCard from '../components/DeadlineCard'

export default function Dashboard() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = () => api.get('/api/dashboard').then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  useEffect(() => { load() }, [tick])

  // Only show courses that have something coming up; old terms stay out of the way
  const activeIds = new Set((data?.items || []).map((i) => i.course_id))
  const courses = (data?.courses || []).filter((c) => activeIds.has(c.id))

  return (
    <div className="space-y-7">
      <DailyBrief tick={tick} />
      <CoachDashboard />

      {courses.length > 0 && (
        <div className="flex gap-2.5 flex-wrap">
          {courses.map((c) => (
            <Link key={c.id} to={`/course/${c.id}`}
              className="px-4 py-2 rounded-xl bg-white border border-slate-200 hover:border-slate-400 transition">
              <CourseTag name={c.name} color={c.color_hex} />
            </Link>
          ))}
        </div>
      )}

      <div className="flex items-baseline gap-4 flex-wrap">
        <h1 className="text-2xl font-extrabold">Upcoming deadlines</h1>
        <span className="text-slate-600">Most urgent first{data?.last_sync && ` · synced ${fmtDate(data.last_sync)}`}</span>
      </div>

      {error && (
        <div className="card !bg-red-50 !border-red-300 text-red-900 flex gap-3 items-center">
          <AlertTriangle size={22} /> {error}. Showing the last data I had.
        </div>
      )}
      {!data && !error && <p className="text-base text-slate-600">Loading deadlines…</p>}
      {data && data.items.length === 0 && (
        <div className="card text-base text-slate-700">No deadlines yet. The agent is syncing your Classroom; watch the activity feed.</div>
      )}
      <div className="space-y-4">
        {data?.items.map((it) => <DeadlineCard key={it.id} item={it} onChange={load} />)}
      </div>
    </div>
  )
}
