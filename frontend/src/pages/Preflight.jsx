import { useEffect, useState } from 'react'
import { BellRing, CheckCircle2, Flame, KeyRound, Loader2, Plane, RotateCw, XCircle } from 'lucide-react'
import { api, loginUrl } from '../api'

// One screen to run right before going on stage: every service the demo depends on.
export default function Preflight() {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(null)   // 'check' | 'warm' | 'alert'
  const [note, setNote] = useState(null)

  const check = async () => {
    setBusy('check'); setNote(null)
    try { setResult(await api.get('/api/preflight')) }
    catch (e) { setNote({ ok: false, text: `Couldn't run the checks: ${e.message}` }) }
    finally { setBusy(null) }
  }
  useEffect(() => { check() }, [])

  const warm = async () => {
    setBusy('warm')
    try {
      await api.post('/api/warmup')
      setNote({ ok: true, text: 'Warm-up started: reading lectures, booking the plan, building prep packs and notes. Wait for “All set” in the agent log (a few minutes), then run the checks again.' })
    } catch (e) { setNote({ ok: false, text: `Warm-up failed to start: ${e.message}` }) }
    finally { setBusy(null) }
  }

  const alert = async () => {
    setBusy('alert')
    try {
      const r = await api.post('/api/notify/test')
      setNote(r.sent ? { ok: true, text: 'Test alert sent. Check your phone.' } : { ok: false, text: 'No alert channel accepted the message.' })
    } catch (e) { setNote({ ok: false, text: e.message }) }
    finally { setBusy(null) }
  }

  const failed = result?.checks.filter((c) => !c.ok) || []
  return (
    <div className="space-y-5 max-w-4xl">
      <div className="card flex items-center gap-5 flex-wrap">
        <Plane size={34} className="text-brand" />
        <div className="flex-1 min-w-[16rem]">
          <h1 className="text-2xl font-extrabold">Pre-flight check</h1>
          <p className="text-slate-600">Run this right before the demo. It tests every service StudyPilot needs, without changing anything.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn-primary" onClick={check} disabled={!!busy}>
            {busy === 'check' ? <Loader2 size={18} className="animate-spin" /> : <RotateCw size={18} />} Run checks
          </button>
          <button className="btn-ghost" onClick={warm} disabled={!!busy}>
            {busy === 'warm' ? <Loader2 size={18} className="animate-spin" /> : <Flame size={18} />} Warm up
          </button>
          <button className="btn-ghost" onClick={alert} disabled={!!busy}>
            {busy === 'alert' ? <Loader2 size={18} className="animate-spin" /> : <BellRing size={18} />} Send test alert
          </button>
          <a className="btn-ghost" href={loginUrl} title="Google testing-mode sign-ins last 7 days: renew the day before the demo">
            <KeyRound size={18} /> Renew Google sign-in
          </a>
        </div>
      </div>

      {note && <div className={`card !py-3 ${note.ok ? '!bg-emerald-50 text-emerald-950' : '!bg-red-50 text-red-950'}`}>{note.text}</div>}

      {result && (
        <div className={`card !py-4 flex items-center gap-3 text-lg font-bold ${result.ok ? '!bg-emerald-600 text-white' : '!bg-amber-100 text-amber-950'}`}>
          {result.ok ? <CheckCircle2 size={26} /> : <XCircle size={26} />}
          {result.ok ? 'All systems go. You are ready for the stage.' : `${failed.length} thing${failed.length > 1 ? 's' : ''} to fix before the demo`}
          <span className="ml-auto text-sm font-medium opacity-80 tabular">{new Date(result.checked_at).toLocaleTimeString()}</span>
        </div>
      )}

      <ul className="card !p-0 divide-y divide-slate-200">
        {!result && busy === 'check' && <li className="p-5 flex items-center gap-3"><Loader2 size={20} className="animate-spin text-brand" /> Checking Google, Gemini, voice, alerts…</li>}
        {result?.checks.map((c) => (
          <li key={c.name} className="p-4 flex items-start gap-3">
            {c.ok ? <CheckCircle2 size={22} className="text-emerald-600 shrink-0 mt-0.5" /> : <XCircle size={22} className="text-red-600 shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              <p className="font-semibold">{c.name}</p>
              <p className="text-sm text-slate-600 break-words">{c.detail}</p>
              {c.fix && <p className="text-sm font-semibold text-red-800 mt-1">Fix: {c.fix}</p>}
            </div>
            <span className="text-sm text-slate-500 tabular shrink-0">{(c.ms / 1000).toFixed(1)}s</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
