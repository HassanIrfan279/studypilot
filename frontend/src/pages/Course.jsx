import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, fmtDate } from '../api'
import { useLive } from '../live'

export default function Course() {
  const { id } = useParams()
  const { tick } = useLive()
  const [data, setData] = useState(null)
  useEffect(() => { api.get(`/api/courses/${id}`).then(setData) }, [id, tick])
  if (!data) return <p className="text-lg">Loading…</p>

  return (
    <div className="space-y-6">
      <h1 className="text-4xl font-extrabold">{data.course?.name}</h1>
      <section>
        <h2 className="text-2xl font-bold mb-3">📄 Lectures</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {data.materials.map((m) => (
            <Link key={m.file_id} to={`/lecture/${m.file_id}`} className="card hover:shadow-md flex items-center gap-3">
              <span className="text-3xl">📄</span>
              <div className="flex-1 min-w-0">
                <p className="font-bold truncate">{m.title}</p>
                <p className={`text-sm ${m.analyzed ? 'text-emerald-700' : 'text-slate-500'}`}>
                  {m.analyzed ? '✓ Analyzed by Gemini' : 'Click to analyze'}
                </p>
              </div>
            </Link>
          ))}
          {data.materials.length === 0 && <p className="text-slate-500">No lecture files yet.</p>}
        </div>
      </section>
      <section>
        <h2 className="text-2xl font-bold mb-3">📝 Coursework</h2>
        <div className="space-y-2">
          {data.items.map((it) => (
            <Link key={it.id} to={`/prep/${it.id}`} className="card !py-3 flex justify-between hover:shadow-md">
              <span className="font-semibold">{it.title} <span className="text-slate-500 uppercase text-xs ml-2">{it.kind}</span></span>
              <span className="text-slate-600">{fmtDate(it.due)}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
