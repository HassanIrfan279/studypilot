import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
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

  if (error) return <div className="card !bg-red-50 text-red-800">⚠ {error}</div>
  if (!a) return (
    <div className="card text-lg flex items-center gap-3">
      <span className="animate-spin text-2xl">⏳</span> Gemini is reading this lecture… (first time takes ~15s, then it's cached)
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <p className="text-slate-500 font-semibold">{a.file_name}</p>
        <h1 className="text-4xl font-extrabold">{a.title}</h1>
        <div className="flex gap-3 mt-3 text-sm font-bold">
          <span className="px-3 py-1 rounded-full bg-amber-100 text-amber-900">Difficulty {a.difficulty}/5</span>
          <span className="px-3 py-1 rounded-full bg-indigo-100 text-indigo-900">~{a.estimated_study_hours}h to study</span>
        </div>
      </div>

      <section className="card">
        <h2 className="text-2xl font-bold mb-2">📝 Summary</h2>
        <UrduText text={a.summary} className="text-lg leading-relaxed" />
      </section>

      <section>
        <h2 className="text-2xl font-bold mb-3">💡 Key concepts, explained simply</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {a.key_concepts.map((c, i) => (
            <div key={i} className="card">
              <h3 className="font-bold text-lg text-indigo-800 mb-1">{c.name}</h3>
              <UrduText text={c.simple_explanation} />
            </div>
          ))}
        </div>
      </section>

      <section className="card !bg-amber-50 !border-amber-300">
        <h2 className="text-2xl font-bold mb-2">🎯 Likely exam points</h2>
        <ul className="list-disc pl-6 space-y-1 text-lg">
          {a.likely_exam_points.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      </section>
    </div>
  )
}
