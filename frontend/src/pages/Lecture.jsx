import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AlertTriangle, Clock, Gauge, Lightbulb, Loader2, ScrollText, Target } from 'lucide-react'
import { api } from '../api'
import UrduText from '../components/UrduToggle'

export default function Lecture() {
  const { fileId } = useParams()
  const [a, setA] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setA(null); setError(null)
    api.get(`/api/lectures/${fileId}`).then(setA).catch((e) => setError(e.message))
  }, [fileId])

  if (error) return <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={22} /> {error}</div>
  if (!a) return (
    <div className="card text-lg flex items-center gap-3">
      <Loader2 size={24} className="animate-spin text-brand" /> Gemini is reading this lecture. The first time takes about 15 seconds, then it's cached.
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-extrabold">{a.title}</h1>
        <div className="flex gap-3 mt-3 flex-wrap items-center text-[15px] font-semibold">
          <span className="text-slate-600">{a.file_name}</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 text-amber-950"><Gauge size={16} /> Difficulty {a.difficulty}/5</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-100 text-indigo-950 tabular"><Clock size={16} /> About {a.estimated_study_hours}h to study</span>
        </div>
      </div>

      <section className="card">
        <h2 className="text-2xl font-bold mb-2 flex items-center gap-2"><ScrollText size={22} className="text-brand" /> Summary</h2>
        <UrduText text={a.summary} className="text-lg leading-relaxed max-w-[75ch]" />
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-3 flex items-center gap-2"><Lightbulb size={22} className="text-amber-600" /> Key concepts, explained simply</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {a.key_concepts.map((c, i) => (
            <div key={i} className="card">
              <h3 className="font-bold text-xl text-slate-900 mb-1.5">{c.name}</h3>
              <UrduText text={c.simple_explanation} className="text-[17px] leading-relaxed" />
            </div>
          ))}
        </div>
      </section>

      <section className="card !bg-amber-50 !border-amber-300">
        <h2 className="text-2xl font-bold mb-2 flex items-center gap-2 text-amber-950"><Target size={22} /> Likely exam points</h2>
        <ul className="list-disc pl-6 space-y-1.5 text-lg">
          {a.likely_exam_points.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      </section>
    </div>
  )
}
