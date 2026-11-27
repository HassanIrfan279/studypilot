import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check, Clock, ExternalLink, Loader2, Mail, Moon, Pencil, Repeat2, Scale, Target, TrendingUp, X,
} from 'lucide-react'
import { api } from '../api'
import { useLive } from '../live'

// Shared loader: the coach state (habits, goals, reviews, proposals, last nightly review)
export function useCoach() {
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const load = () => api.get('/api/coach').then(setData).catch(() => {})
  useEffect(() => { load() }, [tick])
  return [data, load]
}

function Proposal({ p, reload }) {
  const [busy, setBusy] = useState(null)
  const [editing, setEditing] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [err, setErr] = useState(null)
  const act = async (action) => {
    setBusy(action); setErr(null)
    try { await api.post(`/api/proposals/${p.id}/${action}`, { feedback }); setEditing(false); reload() }
    catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  const changes = p.plan?.changes || []
  const items = Object.fromEntries((p.plan?.workload?.items || []).map((i) => [i.item_id, i]))
  const isEmail = p.kind === 'email'
  return (
    <div className="card !border-amber-300 !bg-amber-50 space-y-3">
      <div className="flex items-start gap-3">
        <span className="grid place-items-center w-10 h-10 rounded-xl bg-amber-500 text-white shrink-0">
          {isEmail ? <Mail size={20} /> : <Scale size={20} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-amber-900">{isEmail ? 'Drafted for you, never sent' : 'Needs your OK before I change anything'}</p>
          <h3 className="text-lg font-extrabold text-amber-950">{p.title}</h3>
          <p className="text-[15px] text-slate-800 mt-1">{p.message}</p>
        </div>
      </div>
      {!isEmail && changes.length > 0 && (
        <ul className="grid sm:grid-cols-2 gap-2">
          {changes.map((c) => {
            const it = items[c.item_id] || {}
            const before = it.booked_sessions ?? '?'
            return (
              <li key={c.item_id} className="rounded-xl bg-white border border-amber-200 p-3">
                <p className="font-bold leading-snug">{it.title || c.item_id}</p>
                <p className="text-sm text-slate-500">{it.course} · {it.readiness ?? '?'}% ready (goal {it.target ?? '?'}%)</p>
                <p className="text-sm font-semibold mt-1 tabular">{before} → {c.sessions} session{c.sessions === 1 ? '' : 's'} × {c.minutes_each} min</p>
                <p className="text-sm text-slate-700">{c.reason}</p>
              </li>
            )
          })}
        </ul>
      )}
      {editing && (
        <div className="flex gap-2 flex-wrap">
          <input className="flex-1 min-w-[16rem] border border-slate-300 rounded-xl px-3 py-2 bg-white" value={feedback} autoFocus
            onChange={(e) => setFeedback(e.target.value)} placeholder="What should change? e.g. “keep all 3 CN sessions, cut the lab instead”" />
          <button className="btn-primary" disabled={!feedback.trim() || busy} onClick={() => act('change')}>
            {busy === 'change' ? <Loader2 size={17} className="animate-spin" /> : <Pencil size={17} />} Rethink plan
          </button>
        </div>
      )}
      {err && <p className="text-sm text-red-800">{err}</p>}
      <div className="flex gap-2 flex-wrap">
        {isEmail ? (
          <>
            {p.link && <a className="btn-primary" href={p.link} target="_blank" rel="noopener noreferrer"><ExternalLink size={17} /> Open the Gmail draft</a>}
            <button className="btn-ghost" disabled={!!busy} onClick={() => act('dismiss')}><Check size={17} /> Got it</button>
          </>
        ) : (
          <>
            <button className="btn-primary" disabled={!!busy} onClick={() => act('approve')}>
              {busy === 'approve' ? <Loader2 size={17} className="animate-spin" /> : <Check size={17} />} Approve
            </button>
            <button className="btn-ghost" disabled={!!busy} onClick={() => setEditing(!editing)}><Pencil size={17} /> Change</button>
            <button className="btn-ghost" disabled={!!busy} onClick={() => act('dismiss')}><X size={17} /> Keep my plan</button>
          </>
        )}
      </div>
    </div>
  )
}

// Dashboard: proposals waiting for approval, the nightly review, and review quizzes due
export function CoachDashboard() {
  const [data, load] = useCoach()
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)
  if (!data) return null
  const due = (data.reviews || []).filter((r) => r.due_now)
  const soon = (data.reviews || []).filter((r) => !r.due_now).slice(0, 3)
  const runReview = async () => {
    setBusy('review'); setNote(null)
    try { await api.post('/api/review/run'); setNote('Review started: watch the Decisions panel. It takes about a minute.') }
    finally { setTimeout(() => setBusy(null), 4000) }
  }
  const workload = async () => {
    setBusy('work'); setNote(null)
    try { const r = await api.post('/api/workload/check'); setNote(r.message) ; load() }
    catch (e) { setNote(e.message) } finally { setBusy(null) }
  }
  const lr = data.last_review
  return (
    <div className="space-y-4">
      {(data.proposals || []).map((p) => <Proposal key={p.id} p={p} reload={load} />)}

      <div className="card space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <Moon size={22} className="text-brand" />
          <h2 className="text-lg font-extrabold flex-1">Nightly review</h2>
          <button className="btn-ghost !py-1.5" onClick={workload} disabled={!!busy}>
            {busy === 'work' ? <Loader2 size={16} className="animate-spin" /> : <Scale size={16} />} Check my workload
          </button>
          <button className="btn-ghost !py-1.5" onClick={runReview} disabled={!!busy}>
            {busy === 'review' ? <Loader2 size={16} className="animate-spin" /> : <Moon size={16} />} Run review now
          </button>
        </div>
        {lr ? (
          <p className="text-[15px] text-slate-800 leading-relaxed">{lr.text}
            <span className="block text-sm text-slate-500 mt-1">{new Date(lr.ts * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</span></p>
        ) : (
          <p className="text-slate-600">Every night at {data.review_hour}:00 I review your day, learn when you actually study, escalate deadlines you're not ready for, and plan tomorrow.</p>
        )}
        {note && <p className="text-sm font-semibold text-indigo-900">{note}</p>}
      </div>

      {(due.length > 0 || soon.length > 0) && (
        <div className="card space-y-2">
          <h2 className="text-lg font-extrabold flex items-center gap-2"><Repeat2 size={20} className="text-brand" /> Spaced review</h2>
          <p className="text-sm text-slate-600">What you got wrong comes back after 1, 3 and 7 days, so it sticks.</p>
          {due.map((r) => (
            <Link key={r.id} to={`/review/${r.id}`} className="flex items-center gap-3 rounded-xl bg-indigo-50 border border-indigo-200 px-3 py-2 hover:bg-indigo-100">
              <Repeat2 size={18} className="text-brand" />
              <span className="flex-1"><b>Due now:</b> {r.topics.join(', ')} <span className="text-slate-500">· {r.title}</span></span>
              <span className="text-sm font-bold text-brand">Start →</span>
            </Link>
          ))}
          {soon.map((r) => (
            <p key={r.id} className="text-sm text-slate-600 flex gap-2 items-center"><Clock size={15} /> {r.due_date}: {r.topics.join(', ')} ({r.title})</p>
          ))}
        </div>
      )}
    </div>
  )
}

const GRADES = ['', 'A', 'B+', 'B', 'C']
const PUSH = { light: 'bg-emerald-100 text-emerald-900', steady: 'bg-sky-100 text-sky-900', hard: 'bg-red-100 text-red-900' }

// Study plan page: goals per course + what the agent learned about your habits
export function CoachPlan() {
  const [data, load] = useCoach()
  const [saving, setSaving] = useState(null)
  if (!data) return null
  const setGoal = async (cid, grade) => {
    setSaving(cid)
    try { await api.put(`/api/goals/${cid}`, { grade }); load() } finally { setSaving(null) }
  }
  const h = data.habits
  return (
    <div className="grid xl:grid-cols-2 gap-5">
      <div className="card space-y-3">
        <h2 className="text-lg font-extrabold flex items-center gap-2"><Target size={20} className="text-brand" /> Goals</h2>
        <p className="text-sm text-slate-600">Set a target grade. I track your readiness against it and push harder (more study hours, earlier escalation) when you fall behind.</p>
        <ul className="divide-y divide-slate-100">
          {data.goals.map((c) => (
            <li key={c.course_id} className="py-2.5 flex items-center gap-3 flex-wrap">
              <span className="flex-1 min-w-[10rem] font-semibold">{c.course}</span>
              {c.goal && c.current !== null && (
                <span className="text-sm tabular text-slate-600">{c.current}% / {c.target}%</span>
              )}
              {c.goal && <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${PUSH[c.push]}`}>{c.push === 'hard' ? 'pushing hard' : c.push === 'light' ? 'on track' : 'steady'}</span>}
              <select className="border border-slate-300 rounded-lg px-2 py-1" value={c.goal} disabled={saving === c.course_id}
                onChange={(e) => setGoal(c.course_id, e.target.value)} aria-label={`Goal for ${c.course}`}>
                {GRADES.map((g) => <option key={g} value={g}>{g ? `Goal: ${g}` : 'No goal'}</option>)}
              </select>
            </li>
          ))}
        </ul>
      </div>

      <div className="card space-y-3">
        <h2 className="text-lg font-extrabold flex items-center gap-2"><TrendingUp size={20} className="text-brand" /> Your study habits</h2>
        <p className="text-sm text-slate-600">
          {h.learning
            ? `Still learning: ${h.sessions} finished session${h.sessions === 1 ? '' : 's'} so far. After 6, I'll start moving sessions to the times you actually show up.`
            : h.preference
              ? `You study best in the ${h.preference.bucket}, so new sessions are planned around ${h.preference.hour}:00.`
              : 'No clear pattern yet. I keep watching which sessions you complete.'}
        </p>
        <div className="space-y-2">
          {Object.entries(h.by_time).map(([k, v]) => (
            <div key={k} className="flex items-center gap-3">
              <span className="w-24 capitalize text-sm font-semibold">{k}</span>
              <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden">
                <div className={`h-full rounded-full ${v.rate >= 0.6 ? 'bg-emerald-500' : v.rate >= 0.3 ? 'bg-amber-400' : 'bg-red-400'}`}
                  style={{ width: `${v.total ? Math.max(4, v.rate * 100) : 0}%` }} />
              </div>
              <span className="w-28 text-sm tabular text-slate-600 text-right">{v.total ? `${v.done}/${v.total} done` : 'no data'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
