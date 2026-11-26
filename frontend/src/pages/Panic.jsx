import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AlertTriangle, Loader2, Siren, Zap } from 'lucide-react'
import { api } from '../api'
import Quiz from '../components/Quiz'

export default function Panic() {
  const { id } = useParams()
  const [sheet, setSheet] = useState(null)
  const [error, setError] = useState(null)
  const [secs, setSecs] = useState(20 * 60)

  useEffect(() => {
    const t0 = Date.now()
    api.get(`/api/panic/${id}?minutes=120`).then((s) => { setSheet({ ...s, took: ((Date.now() - t0) / 1000).toFixed(1) }) }).catch((e) => setError(e.message))
  }, [id])
  useEffect(() => {
    if (!sheet) return
    const t = setInterval(() => setSecs((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(t)
  }, [sheet])

  if (error) return <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={22} /> {error}</div>
  if (!sheet) return (
    <div className="rounded-2xl bg-red-700 text-white text-2xl font-bold flex items-center gap-3 p-6">
      <Loader2 size={28} className="animate-spin" /> Panic mode: building your 20-minute cram sheet…
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-red-700 text-white flex items-center gap-6 p-6 shadow-lg">
        <Siren size={44} className="shrink-0 text-red-200" />
        <div className="flex-1">
          <h1 className="text-3xl font-extrabold leading-tight">{sheet.headline}</h1>
          <p className="text-red-100 mt-1.5 text-lg">Panic mode for {sheet.assessment.title} · built in <span className="tabular">{sheet.took}</span>s</p>
        </div>
        <div className="text-center">
          <div className="text-5xl font-extrabold tabular">{String(Math.floor(secs / 60)).padStart(2, '0')}:{String(secs % 60).padStart(2, '0')}</div>
          <p className="text-red-100">cram timer</p>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {sheet.top_topics.map((t, i) => (
          <div key={i} className="card">
            <h2 className="text-xl font-extrabold mb-2 flex gap-2.5 items-baseline">
              <span className="text-red-700 tabular">{i + 1}.</span> {t.topic}
            </h2>
            <ul className="list-disc pl-6 space-y-1 text-[17px]">{t.must_know.map((m, j) => <li key={j}>{m}</li>)}</ul>
          </div>
        ))}
      </div>

      {sheet.last_minute_tips?.length > 0 && (
        <div className="card !bg-amber-50 !border-amber-300">
          <h2 className="text-xl font-bold mb-2 flex items-center gap-2 text-amber-950"><Zap size={20} /> Last-minute tips</h2>
          <ul className="list-disc pl-6 space-y-1 text-[17px]">{sheet.last_minute_tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}

      <Quiz questions={sheet.rapid_quiz} title="Rapid quiz: 5 questions"
        onFinish={(score) => api.post(`/api/quiz/${id}/result`, { score })} />
    </div>
  )
}
