import { useState } from 'react'
import { Lightbulb } from 'lucide-react'

// In-app MCQ quiz. Calls onFinish(score 0..1) when submitted.
export default function Quiz({ questions = [], onFinish, onNewQuestions, title = 'Practice quiz' }) {
  const [answers, setAnswers] = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [loadingNew, setLoadingNew] = useState(false)
  if (!questions.length) return <p className="text-slate-500">No questions yet.</p>

  const correct = questions.filter((q, i) => answers[i] === q.correct_index).length
  const submit = () => {
    setSubmitted(true)
    const wrong = questions.filter((q, i) => answers[i] !== q.correct_index).map((q) => q.question)
    onFinish?.(correct / questions.length, wrong)
  }
  const reset = () => { setAnswers({}); setSubmitted(false) }
  const fresh = async () => {
    setLoadingNew(true)
    try { await onNewQuestions(); reset() } finally { setLoadingNew(false) }
  }

  return (
    <div className="space-y-5">
      <h3 className="text-2xl font-extrabold">{title}</h3>
      {questions.map((q, i) => (
        <div key={i} className="card">
          <p className="font-bold text-base mb-3">{i + 1}. {q.question}</p>
          <div className="grid gap-2">
            {q.options.map((opt, j) => {
              const picked = answers[i] === j
              let cls = picked ? 'border-indigo-600 bg-indigo-50' : 'border-slate-200 hover:bg-slate-50'
              if (submitted && j === q.correct_index) cls = 'border-emerald-600 bg-emerald-50'
              else if (submitted && picked) cls = 'border-red-500 bg-red-50'
              return (
                <button key={j} disabled={submitted} onClick={() => setAnswers({ ...answers, [i]: j })}
                  className={`text-left border-2 rounded-xl px-4 py-2 ${cls}`}>
                  <span className="font-bold mr-2">{'ABCD'[j]}.</span>{opt}
                </button>
              )
            })}
          </div>
          {submitted && (
            <p className="mt-3 text-slate-800 flex gap-2 items-start">
              <Lightbulb size={19} className="text-amber-600 shrink-0 mt-0.5" /> {q.explanation}
            </p>
          )}
        </div>
      ))}
      {!submitted ? (
        <button className="btn-primary text-base" onClick={submit}
          disabled={Object.keys(answers).length < questions.length}>
          Submit answers ({Object.keys(answers).length}/{questions.length})
        </button>
      ) : (
        <div className={`card flex items-center gap-4 flex-wrap ${correct / questions.length >= 0.6 ? '!bg-emerald-50 !border-emerald-300' : '!bg-red-50 !border-red-300'}`}>
          <span className="text-2xl font-extrabold tabular">{correct}/{questions.length}</span>
          <span className="text-base flex-1 min-w-[14rem]">
            {correct / questions.length >= 0.6
              ? 'Score saved. Your readiness is updated.'
              : 'Not good enough yet. The agent is booking extra time on what you missed.'}
          </span>
          {onNewQuestions && (
            <button className="btn-primary" onClick={fresh} disabled={loadingNew}>
              {loadingNew ? 'Writing new questions…' : 'Retake with new questions'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
