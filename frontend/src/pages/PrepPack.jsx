import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, daysLeftLabel, fmtDate } from '../api'
import Quiz from '../components/Quiz'
import ReadinessRing from '../components/ReadinessRing'

export default function PrepPack() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const [pack, setPack] = useState(null)
  const [error, setError] = useState(null)
  const quizRef = useRef(null)

  const load = (refresh = false) => {
    setError(null)
    api.get(`/api/prep/${id}${refresh ? '?refresh=true' : ''}`).then(setPack).catch((e) => setError(e.message))
  }
  useEffect(() => { setPack(null); load() }, [id])
  useEffect(() => {
    if (pack && params.get('quiz')) quizRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [pack, params])

  const finish = async (score) => {
    const r = await api.post(`/api/quiz/${id}/result`, { score })
    setPack((p) => ({ ...p, readiness: r }))
  }

  if (error) return <div className="card !bg-red-50 text-red-800">⚠ {error}</div>
  if (!pack) return (
    <div className="card text-lg flex items-center gap-3">
      <span className="animate-spin text-2xl">⏳</span> Building your prep pack: reading lectures, writing questions, finding videos…
    </div>
  )

  const a = pack.assessment
  return (
    <div className="space-y-6">
      <div className="card flex items-center gap-6">
        <div className="flex-1">
          <p className="font-bold text-indigo-700">{pack.course_name} · Prep pack</p>
          <h1 className="text-4xl font-extrabold">{a.title}</h1>
          <p className="text-lg text-slate-600 mt-1">Due {fmtDate(a.due)}</p>
          <div className="flex gap-2 mt-3">
            <Link to={`/panic/${id}`} className="btn-danger">🚨 Panic mode</Link>
            <button className="btn-ghost" onClick={() => { setPack(null); load(true) }}>↻ Rebuild</button>
          </div>
        </div>
        <ReadinessRing score={pack.readiness?.score || 0} size={110} />
      </div>

      {pack.lectures.length === 0 && (
        <div className="card text-slate-600">No lecture files found for this course yet. Ask your teacher to upload slides, or add them in Classroom.</div>
      )}

      {pack.lectures.map((l) => (
        <section key={l.file_id} className="card">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold flex-1">📄 {l.title}</h2>
            <Link to={`/lecture/${l.file_id}`} className="btn-ghost !py-1">Full breakdown →</Link>
          </div>
          <p className="text-lg mb-3">{l.summary}</p>
          <h3 className="font-bold text-amber-800">🎯 Likely exam points</h3>
          <ul className="list-disc pl-6">{l.likely_exam_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </section>
      ))}

      {pack.videos?.some((v) => v.videos.length) && (
        <section>
          <h2 className="text-2xl font-bold mb-3">▶️ Best explainer videos</h2>
          {pack.videos.map((t) => (
            <div key={t.topic} className="mb-4">
              <p className="font-semibold text-slate-600 mb-2">{t.topic}</p>
              <div className="grid md:grid-cols-3 gap-3">
                {t.videos.map((v) => (
                  <a key={v.video_id} href={v.url} target="_blank" rel="noreferrer" className="card !p-0 overflow-hidden hover:shadow-md">
                    <img src={v.thumbnail} alt="" className="w-full aspect-video object-cover" />
                    <div className="p-3">
                      <p className="font-semibold leading-snug line-clamp-2">{v.title}</p>
                      <p className="text-sm text-slate-500">{v.channel}</p>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      <section ref={quizRef}>
        <Quiz questions={pack.quiz?.questions || []} onFinish={finish} title="✏️ Practice quiz (from your lectures)" />
      </section>
    </div>
  )
}
