import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, Briefcase, CalendarClock, Check, ChevronDown, ChevronUp, Copy, ExternalLink,
  FileText, Loader2, MailCheck, MessageSquareText, Wand2, PencilLine, Plus, RefreshCw, Search, Send, ShieldCheck, Sparkles,
  Trophy, Upload, X,
} from 'lucide-react'
import { api } from '../api'
import { useLive } from '../live'
import CvBuilder from '../components/CvBuilder'

const COLUMNS = [
  { key: 'waiting', title: 'Waiting for you', statuses: ['ready', 'needs_info'], icon: Sparkles, tone: 'text-indigo-700' },
  { key: 'applied', title: 'Applied', statuses: ['applied'], icon: Send, tone: 'text-sky-700' },
  { key: 'interview', title: 'Interviews', statuses: ['interview'], icon: CalendarClock, tone: 'text-amber-700' },
  { key: 'offer', title: 'Offers', statuses: ['offer'], icon: Trophy, tone: 'text-emerald-700' },
]
const STATUS_LABEL = {
  found: 'Maybe', shortlisted: 'Writing…', needs_info: 'Needs your answer', ready: 'Ready to send',
  applied: 'Applied', interview: 'Interview', offer: 'Offer', rejected: 'Not selected', skipped: 'Skipped',
}

function ScoreBadge({ score }) {
  if (score == null) return null
  const cls = score >= 75 ? 'bg-emerald-100 text-emerald-900' : score >= 55 ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'
  return <span className={`text-sm font-bold px-2 py-0.5 rounded-lg tabular ${cls}`}>{score}/100</span>
}

function CopyBtn({ text }) {
  const [done, setDone] = useState(false)
  return (
    <button className="btn-ghost !py-1 !px-2 text-sm" onClick={() => {
      navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) })
    }}>{done ? <Check size={15} /> : <Copy size={15} />}{done ? 'Copied' : 'Copy'}</button>
  )
}

function CvUpload({ onDone, compact }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const input = useRef(null)
  const pick = async (file) => {
    if (!file) return
    if (file.type !== 'application/pdf') { setErr('Please choose a PDF.'); return }
    setBusy(true); setErr(null)
    try {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file)
      })
      await api.post('/api/internships/cv', { pdf_base64: b64 })
      onDone()
    } catch (e) { setErr(e.message) } finally { setBusy(false); if (input.current) input.current.value = '' }
  }
  return (
    <div className={compact ? '' : 'card text-center py-10'}>
      {!compact && <>
        <Upload size={36} className="mx-auto text-brand" />
        <h2 className="text-xl font-extrabold mt-3">Upload your CV to start</h2>
        <p className="text-slate-600 mt-1 max-w-xl mx-auto">
          The career agent reads it once, then finds internships that fit you, writes each
          application and tracks the replies. It only asks you when it truly needs something.
        </p>
      </>}
      <input ref={input} type="file" accept="application/pdf" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
      <button className={compact ? 'btn-ghost !py-1.5' : 'btn-primary mt-5'} onClick={() => input.current?.click()} disabled={busy}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : <Upload size={18} />}
        {busy ? 'Reading your CV…' : compact ? 'Replace CV' : 'Choose CV (PDF)'}
      </button>
      {err && <p className="text-red-700 mt-2 text-sm">{err}</p>}
    </div>
  )
}

function Questions({ questions, onAnswered }) {
  const [vals, setVals] = useState({})
  const [busy, setBusy] = useState(null)
  if (!questions.length) return null
  const send = async (q) => {
    if (!vals[q]?.trim()) return
    setBusy(q)
    try { await api.post('/api/internships/answer', { question: q, answer: vals[q].trim() }); onAnswered() }
    finally { setBusy(null) }
  }
  return (
    <div className="card !bg-amber-50 !border-amber-300 space-y-3">
      <h2 className="text-lg font-extrabold text-amber-950 flex items-center gap-2"><AlertTriangle size={20} /> The agent needs a few facts from you</h2>
      <p className="text-sm text-amber-900">It never makes things up in an application, so it asks instead. Each answer is reused for every future application.</p>
      {questions.map((q) => (
        <div key={q} className="flex gap-2 flex-wrap items-center">
          <label className="font-semibold flex-1 min-w-[16rem]">{q}</label>
          <input className="border border-slate-300 rounded-xl px-3 py-2 flex-[2] min-w-[14rem] bg-white" value={vals[q] || ''}
            onChange={(e) => setVals({ ...vals, [q]: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && send(q)}
            placeholder="Your answer" />
          <button className="btn-primary !py-2" onClick={() => send(q)} disabled={busy === q}>
            {busy === q ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} Save
          </button>
        </div>
      ))}
    </div>
  )
}

function Detail({ it, canDraft, reload }) {
  const app = it.app || {}
  const [letter, setLetter] = useState(app.cover_letter || '')
  const [editing, setEditing] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)
  useEffect(() => { setLetter(app.cover_letter || '') }, [app.cover_letter])

  const act = async (name, fn) => {
    setBusy(name); setNote(null)
    try { await fn(); reload() } catch (e) { setNote({ ok: false, text: e.message }) } finally { setBusy(null) }
  }
  const approve = () => act('approve', async () => {
    const r = await api.post(`/api/internships/${it.id}/approve`)
    if (r.open) window.open(r.open, '_blank', 'noopener')
    setNote({ ok: true, text: r.method === 'email'
      ? (r.draft ? 'Draft created in Gmail with your CV attached. Review it and press Send. StudyPilot will notice.' : r.note)
      : 'Application page opened. Paste the ready answers below, submit, then click “I submitted it”.' })
  })

  return (
    <div className="mt-4 space-y-4 border-t border-slate-200 pt-4">
      {it.red_flags?.length > 0 && (
        <div className="rounded-xl bg-red-50 border border-red-200 p-3 text-red-900 text-sm">
          <b>Red flags:</b> {it.red_flags.join(' · ')}
        </div>
      )}
      {it.timing_note && <p className="text-sm text-slate-700 flex gap-2"><CalendarClock size={16} className="shrink-0 mt-0.5" />{it.timing_note}</p>}

      {it.status === 'needs_info' && it.questions?.length > 0 && (
        <p className="text-sm font-semibold text-amber-800">Waiting on your answer above: {it.questions.join(' / ')}</p>
      )}

      {app.cover_letter ? (
        <>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-bold">Cover letter</h4>
              <span className="text-sm text-slate-500 truncate">Subject: {app.subject}</span>
              <div className="ml-auto flex gap-1">
                <CopyBtn text={letter} />
                <button className="btn-ghost !py-1 !px-2 text-sm" onClick={() => setEditing(!editing)}><PencilLine size={15} />{editing ? 'Done' : 'Edit'}</button>
              </div>
            </div>
            {editing ? (
              <div className="space-y-2">
                <textarea className="w-full border border-slate-300 rounded-xl p-3 min-h-[220px] text-[15px] leading-relaxed" value={letter} onChange={(e) => setLetter(e.target.value)} />
                <button className="btn-primary !py-1.5" disabled={busy === 'save'} onClick={() => act('save', async () => {
                  await api.patch(`/api/internships/${it.id}/app`, { cover_letter: letter }); setEditing(false)
                })}>{busy === 'save' ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} Save letter</button>
              </div>
            ) : (
              <p className="whitespace-pre-wrap text-[15px] leading-relaxed bg-slate-50 rounded-xl p-4 border border-slate-200">{app.cover_letter}</p>
            )}
          </div>

          {app.cv_highlights?.length > 0 && (
            <div>
              <h4 className="font-bold mb-1">CV highlights for this role</h4>
              <ul className="list-disc pl-6 space-y-0.5 text-[15px]">{app.cv_highlights.map((b, i) => <li key={i}>{b}</li>)}</ul>
            </div>
          )}

          {app.answers?.length > 0 && (
            <div>
              <h4 className="font-bold mb-2">Ready answers for the application form</h4>
              <div className="space-y-2">
                {app.answers.map((qa, i) => (
                  <div key={i} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex gap-2 items-start">
                      <p className="font-semibold flex-1">{qa.question}</p>
                      <CopyBtn text={qa.answer} />
                    </div>
                    <p className="text-[15px] text-slate-700 mt-1 whitespace-pre-wrap">{qa.answer}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {app.interview_prep && (
            <div>
              <h4 className="font-bold mb-1">Interview prep sheet</h4>
              <pre className="whitespace-pre-wrap font-sans text-[15px] leading-relaxed bg-amber-50 border border-amber-200 rounded-xl p-4">{app.interview_prep}</pre>
            </div>
          )}

          {app.follow_up && it.status === 'applied' && (
            <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
              <h4 className="font-bold">Follow-up email (no reply for 10 days)</h4>
              <p className="text-sm text-slate-600">Subject: {app.follow_up.subject}</p>
              <p className="whitespace-pre-wrap text-[15px] mt-2">{app.follow_up.body}</p>
              <button className="btn-primary !py-1.5 mt-3" disabled={busy === 'fu'} onClick={() => act('fu', async () => {
                const r = await api.post(`/api/internships/${it.id}/follow-up`); if (r.open) window.open(r.open, '_blank', 'noopener')
              })}><MailCheck size={16} /> Approve follow-up</button>
            </div>
          )}

          <div className="flex gap-2 flex-wrap items-center">
            <input className="border border-slate-300 rounded-xl px-3 py-2 flex-1 min-w-[14rem]" value={instruction}
              onChange={(e) => setInstruction(e.target.value)} placeholder="Ask for changes, e.g. “mention my FYP”, “shorter”" />
            <button className="btn-ghost" disabled={busy === 'rewrite'} onClick={() => act('rewrite', async () => {
              await api.post(`/api/internships/${it.id}/write`, { instruction }); setInstruction('')
            })}>{busy === 'rewrite' ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} Rewrite</button>
          </div>
        </>
      ) : (
        ['found', 'shortlisted', 'skipped', 'rejected'].includes(it.status) && (
          <button className="btn-primary" disabled={busy === 'write'} onClick={() => act('write', () => api.post(`/api/internships/${it.id}/write`, {}))}>
            {busy === 'write' ? <Loader2 size={16} className="animate-spin" /> : <PencilLine size={16} />} Write an application anyway
          </button>
        )
      )}

      {note && <p className={`text-sm font-semibold ${note.ok ? 'text-emerald-800' : 'text-red-800'}`}>{note.text}</p>}

      <div className="flex gap-2 flex-wrap">
        {it.status === 'ready' && (
          <button className="btn-primary" disabled={busy === 'approve'} onClick={approve}>
            {busy === 'approve' ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
            {it.apply_method === 'email' ? (canDraft ? 'Approve: create Gmail draft' : 'Approve: open Gmail') : 'Approve: open application page'}
          </button>
        )}
        {['ready', 'needs_info', 'found', 'shortlisted'].includes(it.status) && (
          <button className="btn-ghost" onClick={() => act('applied', () => api.post(`/api/internships/${it.id}/status/applied`))}><Check size={16} /> I submitted it</button>
        )}
        {it.status === 'applied' && (
          <button className="btn-ghost" onClick={() => act('iv', () => api.post(`/api/internships/${it.id}/status/interview`))}><CalendarClock size={16} /> Got an interview</button>
        )}
        {['applied', 'interview'].includes(it.status) && <>
          <button className="btn-ghost" onClick={() => act('offer', () => api.post(`/api/internships/${it.id}/status/offer`))}><Trophy size={16} /> Got an offer</button>
          <button className="btn-ghost" onClick={() => act('rej', () => api.post(`/api/internships/${it.id}/status/rejected`))}><X size={16} /> Not selected</button>
        </>}
        {!['skipped', 'applied', 'interview', 'offer'].includes(it.status) && (
          <button className="btn-ghost" onClick={() => act('skip', () => api.post(`/api/internships/${it.id}/status/skipped`))}><X size={16} /> Skip</button>
        )}
        {it.url && <a className="btn-ghost" href={it.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={16} /> Posting</a>}
        {it.doc_link && <a className="btn-ghost" href={it.doc_link} target="_blank" rel="noopener noreferrer"><FileText size={16} /> Drive copy</a>}
      </div>

      {it.timeline?.length > 0 && (
        <details className="text-sm text-slate-600">
          <summary className="cursor-pointer font-semibold">What the agent did ({it.timeline.length})</summary>
          <ul className="mt-2 space-y-1">
            {[...it.timeline].reverse().map((e, i) => (
              <li key={i}><span className="tabular text-slate-400 mr-2">{new Date(e.ts * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>{e.text}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function ApplicationPanel({ it, canDraft, reload, onClose }) {
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-label={`${it.title} at ${it.company}`}>
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="absolute right-0 inset-y-0 w-full max-w-[760px] bg-white shadow-2xl overflow-y-auto slide-in">
        <div className="sticky top-0 bg-white/95 backdrop-blur border-b border-slate-200 px-6 py-4 flex items-start gap-3 z-10">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-500">{it.company} · {it.location || '—'} · {it.source}</p>
            <h2 className="text-xl font-extrabold leading-snug">{it.title}</h2>
            {it.reasoning && <p className="text-sm text-slate-600 mt-1">{it.reasoning}</p>}
          </div>
          <ScoreBadge score={it.score} />
          <button className="btn-ghost !p-2" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </div>
        <div className="px-6 pb-8 -mt-2">
          <Detail it={it} canDraft={canDraft} reload={reload} />
        </div>
      </div>
    </div>
  )
}

function Card({ it, open, onToggle, canDraft, reload }) {
  return (
    <div className={`card !p-4 ${open ? 'ring-2 ring-indigo-300' : ''}`}>
      <button className="w-full text-left" onClick={onToggle}>
        <div className="flex gap-2 items-start">
          <div className="flex-1 min-w-0">
            <p className="font-bold leading-snug">{it.title}</p>
            <p className="text-slate-700">{it.company}</p>
            <p className="text-sm text-slate-500 truncate">{it.location || '—'} · {it.source}</p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <ScoreBadge score={it.score} />
            <ChevronDown size={18} className="text-slate-400 -rotate-90" />
          </div>
        </div>
        <div className="mt-2 flex gap-2 flex-wrap items-center">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${it.status === 'needs_info' ? 'bg-amber-200 text-amber-950' : it.status === 'ready' ? 'bg-indigo-100 text-indigo-900' : 'bg-slate-100 text-slate-700'}`}>{STATUS_LABEL[it.status] || it.status}</span>
          {it.red_flags?.length > 0 && <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-red-100 text-red-900">⚠ check</span>}
          {it.deadline && <span className="text-xs text-slate-500">Apply by {it.deadline}</span>}
        </div>
        {it.reasoning && <p className="text-sm text-slate-600 mt-2 line-clamp-2">{it.reasoning}</p>}
      </button>
    </div>
  )
}

export default function Internships() {
  const { tick, logs } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(null)
  const [searching, setSearching] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [add, setAdd] = useState({ text: '', url: '' })
  const [addBusy, setAddBusy] = useState(false)
  const [addErr, setAddErr] = useState(null)
  const [showOthers, setShowOthers] = useState(false)
  const [cvOpen, setCvOpen] = useState(null)   // null | 'view' | 'chat'

  const load = () => api.get('/api/internships').then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  useEffect(() => { load() }, [tick])
  useEffect(() => {
    if (!searching) return
    const t = setTimeout(() => setSearching(false), 90000)
    return () => clearTimeout(t)
  }, [searching])

  if (error) return <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={22} /> {error}</div>
  if (!data) return <div className="card flex items-center gap-3"><Loader2 className="animate-spin text-brand" /> Loading internships…</div>

  const items = data.items || []
  const p = data.profile
  const search = async () => { setSearching(true); try { await api.post('/api/internships/run') } catch { setSearching(false) } }
  const submitAdd = async () => {
    setAddBusy(true); setAddErr(null)
    try { await api.post('/api/internships/add', add); setAdd({ text: '', url: '' }); setShowAdd(false); load() }
    catch (e) { setAddErr(e.message) } finally { setAddBusy(false) }
  }
  const others = items.filter((it) => ['found', 'shortlisted', 'skipped', 'rejected'].includes(it.status))
  const questions = [...new Set([...(p?.gaps || []), ...items.filter((i) => i.status === 'needs_info').flatMap((i) => i.questions || [])])]
    .filter((q) => !(q in (data.answers || {})))
  const toggle = (id) => setOpen(open === id ? null : id)

  const openItem = items.find((it) => it.id === open)
  return (
    <div className="space-y-5">
      <div className="card flex items-center gap-5 flex-wrap">
        <Briefcase size={34} className="text-brand" />
        <div className="flex-1 min-w-[16rem]">
          <h1 className="text-2xl font-extrabold">Internship agent</h1>
          <p className="text-slate-600">Finds internships that fit you, decides which are worth it, writes each application and tracks replies in Gmail. Nothing is sent without your OK.</p>
        </div>
        {p && (
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary" onClick={search} disabled={searching}>
              {searching ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />} {searching ? 'Searching… (see agent log)' : 'Find internships now'}
            </button>
            <button className="btn-ghost" onClick={() => setShowAdd(!showAdd)}><Plus size={18} /> Add a posting</button>
            <button className="btn-ghost" onClick={() => api.post('/api/internships/track').then(load)} title="Check Gmail for replies now"><RefreshCw size={18} /> Check replies</button>
          </div>
        )}
      </div>

      {!p && !cvOpen && (
        <div className="grid md:grid-cols-2 gap-5">
          <div className="card text-center py-10">
            <MessageSquareText size={36} className="mx-auto text-brand" />
            <h2 className="text-xl font-extrabold mt-3">No CV? Let the agent write it</h2>
            <p className="text-slate-600 mt-1 max-w-md mx-auto">It asks you about your studies, projects and skills, one question at a time, then writes a clean CV as a Google Doc and PDF.</p>
            <button className="btn-primary mt-5" onClick={() => setCvOpen('chat')}><Wand2 size={18} /> Build my CV with the agent</button>
          </div>
          <CvUpload onDone={load} />
        </div>
      )}

      {cvOpen && <CvBuilder key={cvOpen} start={cvOpen === 'chat'} onClose={() => setCvOpen(null)} onChanged={load} />}

      {p && (
        <div className="card !py-4 flex gap-4 flex-wrap items-center">
          <div className="flex-1 min-w-[18rem]">
            <p className="font-bold">{p.name || 'Your profile'} · {[p.degree, p.semester && `semester ${p.semester}`, p.university].filter(Boolean).join(', ')}</p>
            <div className="flex gap-1.5 flex-wrap mt-2">
              {(p.preferred_roles || []).map((r) => <span key={r} className="text-sm font-semibold px-2 py-0.5 rounded-lg bg-indigo-100 text-indigo-900">{r}</span>)}
              {(p.skills || []).slice(0, 10).map((s) => <span key={s} className="text-sm px-2 py-0.5 rounded-lg bg-slate-100 text-slate-700">{s}</span>)}
            </div>
          </div>
          <div className="text-sm text-slate-600 space-y-1">
            <p>Searches: job emails · Bayt.com Pakistan · remote boards · {data.web_search ? 'web' : <span title="Gemini Google Search isn't enabled on this API key">web (off)</span>}</p>
            <p>{data.last_run ? `Last search ${new Date(data.last_run * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })} · runs daily` : 'Not searched yet'}</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button className="btn-ghost !py-1.5" onClick={() => setCvOpen(cvOpen ? null : 'view')}><FileText size={18} /> {cvOpen ? 'Hide CV' : 'My CV'}</button>
            <button className="btn-ghost !py-1.5" onClick={() => setCvOpen('chat')}><Wand2 size={18} /> Build / improve CV</button>
            <CvUpload onDone={load} compact />
          </div>
        </div>
      )}

      {p && (() => {
        const feed = (logs || []).filter((l) => l.agent === 'Career').slice(-6).reverse()
        if (!feed.length) return null
        return (
          <div className="card !py-4">
            <h2 className="font-extrabold flex items-center gap-2 mb-2">
              {searching ? <Loader2 size={18} className="animate-spin text-brand" /> : <Sparkles size={18} className="text-brand" />}
              What the agent is doing
            </h2>
            <ul className="space-y-1.5">
              {feed.map((l) => (
                <li key={l.id} className={`text-sm rounded-lg px-3 py-1.5 ${l.level === 'warn' ? 'bg-amber-50 text-amber-950' : l.level === 'success' ? 'bg-emerald-50 text-emerald-950' : l.level === 'error' ? 'bg-red-50 text-red-900' : 'bg-slate-50 text-slate-800'}`}>
                  <span className="tabular text-slate-400 mr-2">{new Date(l.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>{l.message}
                </li>
              ))}
            </ul>
          </div>
        )
      })()}

      <Questions questions={questions} onAnswered={load} />

      {showAdd && (
        <div className="card space-y-3">
          <h2 className="text-lg font-extrabold">Add a posting you found</h2>
          <input className="w-full border border-slate-300 rounded-xl px-3 py-2" placeholder="Link (optional)" value={add.url} onChange={(e) => setAdd({ ...add, url: e.target.value })} />
          <textarea className="w-full border border-slate-300 rounded-xl p-3 min-h-[140px]" placeholder="Paste the posting text (best for LinkedIn posts)" value={add.text} onChange={(e) => setAdd({ ...add, text: e.target.value })} />
          {addErr && <p className="text-red-700 text-sm">{addErr}</p>}
          <button className="btn-primary" disabled={addBusy || (!add.text.trim() && !add.url.trim())} onClick={submitAdd}>
            {addBusy ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />} {addBusy ? 'Judging the fit and writing…' : 'Judge & write application'}
          </button>
        </div>
      )}

      {p && (
        <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-4 items-start">
          {COLUMNS.map((col) => {
            const list = items.filter((it) => col.statuses.includes(it.status))
            const Icon = col.icon
            return (
              <section key={col.key} className="space-y-3 min-w-0">
                <h2 className={`font-extrabold text-lg flex items-center gap-2 ${col.tone}`}><Icon size={20} /> {col.title} <span className="text-slate-400 tabular">{list.length}</span></h2>
                {list.length === 0 && <p className="text-sm text-slate-500 card !p-4 !shadow-none border-dashed">Nothing here yet.</p>}
                {list.map((it) => <Card key={it.id} it={it} open={open === it.id} onToggle={() => toggle(it.id)} canDraft={data.can_draft} reload={load} />)}
              </section>
            )
          })}
        </div>
      )}

      {p && others.length > 0 && (
        <div className="space-y-3">
          <button className="font-bold text-slate-700 flex items-center gap-2" onClick={() => setShowOthers(!showOthers)}>
            {showOthers ? <ChevronUp size={18} /> : <ChevronDown size={18} />} Also considered ({others.length}): maybes, skipped and closed
          </button>
          {showOthers && (
            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {others.map((it) => <Card key={it.id} it={it} open={open === it.id} onToggle={() => toggle(it.id)} canDraft={data.can_draft} reload={load} />)}
            </div>
          )}
        </div>
      )}
      {openItem && <ApplicationPanel it={openItem} canDraft={data.can_draft} reload={load} onClose={() => setOpen(null)} />}
    </div>
  )
}
