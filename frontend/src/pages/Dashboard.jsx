import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import DailyBrief from '../components/DailyBrief'
import DeadlineCard from '../components/DeadlineCard'

export default function Dashboard() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = () => api.get('/api/dashboard').then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  useEffect(() => { load() }, [tick])

  return (
    <div className="space-y-6">
      <DailyBrief tick={tick} />

      {data?.courses?.length > 0 && (
        <div className="flex gap-3 flex-wrap">
          {data.courses.map((c) => (
            <Link key={c.id} to={`/course/${c.id}`}
              className="px-4 py-2 rounded-xl bg-white border-2 font-bold hover:shadow"
              style={{ borderColor: c.color_hex, color: c.color_hex }}>
              {c.name}
            </Link>
          ))}
        </div>
      )}

      <div className="flex items-end gap-3">
        <h2 className="text-3xl font-extrabold">Upcoming deadlines</h2>
        <span className="text-slate-500 mb-1">sorted by urgency{data?.last_sync && ` · last sync ${fmtDate(data.last_sync)}`}</span>
      </div>

      {error && <div className="card !bg-red-50 !border-red-300 text-red-800">⚠ {error} — showing last known data.</div>}
      {!data && !error && <p className="text-lg text-slate-500">Loading…</p>}
      {data && data.items.length === 0 && (
        <div className="card text-lg text-slate-600">No deadlines yet. The agent is syncing your Classroom — watch the activity log →</div>
      )}
      <div className="space-y-4">
        {data?.items.map((it) => <DeadlineCard key={it.id} item={it} onChange={load} />)}
      </div>
    </div>
  )
}
