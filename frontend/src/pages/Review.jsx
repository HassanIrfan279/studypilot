import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AlertTriangle, Loader2, Repeat2 } from 'lucide-react'
import { api } from '../api'
import Quiz from '../components/Quiz'

// Spaced-repetition review: 4 fresh questions on topics the student got wrong before
export default function Review() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setData(null); setError(null)
    api.get(`/api/reviews/${id}/quiz`).then(setData).catch((e) => setError(e.message))
  }, [id])

  if (error) return <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={22} /> {error}</div>
  if (!data) return <div className="card flex items-center gap-3"><Loader2 className="animate-spin text-brand" /> Writing your review questions…</div>
  const r = data.review
  return (
    <div className="space-y-5">
      <div className="card flex items-center gap-4">
        <Repeat2 size={32} className="text-brand" />
        <div>
          <h1 className="text-2xl font-extrabold">Spaced review · day {r.interval}</h1>
          <p className="text-slate-600">You got these wrong before: <b>{r.topics.join(', ')}</b>. Four quick questions to make them stick.</p>
        </div>
      </div>
      <Quiz questions={data.quiz?.questions || []} title="Review quiz"
        onFinish={(score) => api.post(`/api/reviews/${id}/result`, { score })} />
    </div>
  )
}
