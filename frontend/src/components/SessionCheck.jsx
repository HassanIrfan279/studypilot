import { useEffect, useState } from 'react'
import { GraduationCap, Loader2, X } from 'lucide-react'
import { api } from '../api'
import Quiz from './Quiz'

// Strict teacher: a session only counts as done after passing a 3-question check.
export default function SessionCheck({ session, onClose }) {
  const [quiz, setQuiz] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.post(`/api/sessions/${session.event_id}/check`).then(setQuiz).catch((e) => setError(e.message))
  }, [session.event_id])

  const finish = async (score, wrong) => {
    setResult(await api.post(`/api/sessions/${session.event_id}/verify`, { score, wrong }))
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/60 flex items-start justify-center overflow-y-auto p-6" role="dialog" aria-modal="true">
      <div className="bg-slate-50 rounded-3xl max-w-3xl w-full p-7 shadow-2xl my-6">
        <div className="flex items-start gap-4 mb-5">
          <span className="grid place-items-center w-12 h-12 rounded-2xl bg-slate-900 text-white shrink-0"><GraduationCap size={26} /></span>
          <div className="flex-1">
            <h2 className="text-2xl font-extrabold">Prove it first</h2>
            <p className="text-slate-700">A session only counts once you get at least 2 of these 3 right. The questions are new every time.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1 text-slate-500 hover:text-slate-900"><X size={24} /></button>
        </div>
        {error && <p className="text-red-800">{error}</p>}
        {!quiz && !error && <p className="flex items-center gap-2 text-base"><Loader2 className="animate-spin" /> Writing your check questions…</p>}
        {quiz && <Quiz questions={quiz.questions} onFinish={finish} title={session.title.replace(/^📘\s*/, '')} />}
        {result && (
          <div className={`mt-5 rounded-2xl p-5 text-base font-semibold ${result.passed ? 'bg-emerald-100 text-emerald-950' : 'bg-red-100 text-red-950'}`}>
            {result.message}
            <div className="mt-3"><button className="btn-primary" onClick={onClose}>{result.passed ? 'Back to my plan' : 'OK, I’ll review'}</button></div>
          </div>
        )}
      </div>
    </div>
  )
}
