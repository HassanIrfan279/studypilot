import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CheckCircle2, ChevronRight, FileText, ListTodo, Presentation } from 'lucide-react'
import { api, fmtDate } from '../api'
import { useLive } from '../live'
import { titleCase } from '../components/CourseTag'

const iconFor = (title) => (/\.pptx?$/i.test(title) ? Presentation : FileText)

export default function Course() {
  const { id } = useParams()
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.get(`/api/courses/${id}`).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message)) }, [id, tick])
  if (!data) return <p className="text-base text-slate-600">{error ? `Couldn't load this course (${error}). It will retry on the next sync.` : 'Loading course…'}</p>

  return (
    <div className="space-y-7">
      <h1 className="text-3xl font-extrabold">{titleCase(data.course?.name)}</h1>
      <section>
        <h2 className="text-2xl font-bold mb-3 flex items-center gap-2"><FileText size={22} className="text-brand" /> Lectures</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {data.materials.map((m) => {
            const Icon = iconFor(m.title)
            return (
              <Link key={m.file_id} to={`/lecture/${m.file_id}`} className="card !p-4 hover:border-slate-400 transition flex items-center gap-3">
                <Icon size={28} className="text-slate-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate">{m.title}</p>
                  <p className={`text-sm flex items-center gap-1 ${m.analyzed ? 'text-emerald-800' : 'text-slate-600'}`}>
                    {m.analyzed ? <><CheckCircle2 size={15} /> Analyzed by Gemini</> : 'Open to analyze'}
                  </p>
                </div>
                <ChevronRight size={20} className="text-slate-400" />
              </Link>
            )
          })}
          {data.materials.length === 0 && <p className="text-slate-600">No lecture files yet.</p>}
        </div>
      </section>
      <section>
        <h2 className="text-2xl font-bold mb-3 flex items-center gap-2"><ListTodo size={22} className="text-brand" /> Coursework</h2>
        <div className="card !p-0 divide-y divide-slate-100">
          {data.items.map((it) => (
            <Link key={it.id} to={`/prep/${it.id}`} className="flex justify-between gap-4 px-5 py-3.5 hover:bg-slate-50">
              <span className="font-semibold">{it.title} <span className="text-slate-500 uppercase text-xs ml-2 tracking-wide">{it.kind}</span></span>
              <span className="text-slate-700 tabular">{fmtDate(it.due)}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
