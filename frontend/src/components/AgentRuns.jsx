import { useState } from 'react'
import {
  AlertTriangle, BrainCircuit, Briefcase, CalendarX2, CheckCircle2, ChevronDown, CircleHelp, ClipboardX,
  GraduationCap, Loader2, Mail, MessageCircle, School, ShieldAlert, UserRound, Wrench,
} from 'lucide-react'

const TRIGGER = {
  classroom: { icon: School, label: 'Teacher change' },
  clash: { icon: CalendarX2, label: 'Calendar clash' },
  missed: { icon: ClipboardX, label: 'Missed session' },
  quiz: { icon: GraduationCap, label: 'Quiz result' },
  audit: { icon: ShieldAlert, label: 'Audit' },
  profile: { icon: UserRound, label: 'Your profile' },
  gmail: { icon: Mail, label: 'Class email' },
  career: { icon: Briefcase, label: 'Internship hunt' },
}
const STEP = {
  think: { icon: BrainCircuit, cls: 'text-indigo-900 bg-indigo-50', label: 'Thinking' },
  act: { icon: Wrench, cls: 'text-slate-900 bg-white', label: 'Action' },
  ok: { icon: CheckCircle2, cls: 'text-emerald-900 bg-emerald-50/60', label: 'Result' },
  warn: { icon: AlertTriangle, cls: 'text-amber-950 bg-amber-50', label: 'Warning' },
  ask: { icon: CircleHelp, cls: 'text-amber-950 bg-amber-100', label: 'Asked you' },
  say: { icon: MessageCircle, cls: 'text-white bg-indigo-700', label: 'Told you' },
}
const STATUS = {
  running: 'bg-indigo-100 text-indigo-900',
  done: 'bg-emerald-100 text-emerald-900',
  fallback: 'bg-amber-100 text-amber-950',
}

function secs(run) {
  const end = run.ended || Date.now() / 1000
  return Math.max(0, Math.round(end - run.started))
}

function RunCard({ run, open, onToggle }) {
  const t = TRIGGER[run.trigger] || { icon: BrainCircuit, label: run.trigger }
  const Icon = t.icon
  const steps = (run.steps || []).filter((s) => s.kind !== 'ok' || open)
  return (
    <li className="rounded-xl border border-slate-200 overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-slate-50">
        <span className="grid place-items-center w-9 h-9 rounded-lg bg-slate-900 text-white shrink-0"><Icon size={18} /></span>
        <span className="flex-1 min-w-0">
          <span className="block text-xs font-semibold text-slate-500">{t.label} · {new Date(run.started * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          <span className="block font-bold leading-snug truncate">{run.title}</span>
        </span>
        <span className={`text-xs font-bold px-2 py-1 rounded-md inline-flex items-center gap-1 tabular ${STATUS[run.status] || STATUS.done}`}>
          {run.status === 'running' && <Loader2 size={13} className="animate-spin" />}
          {run.status === 'running' ? 'working' : run.status === 'fallback' ? 'backup rules' : `${secs(run)}s`}
        </span>
        <ChevronDown size={18} className={`text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ol className="px-3 pb-3 space-y-1.5">
          {steps.map((s) => {
            const st = STEP[s.kind] || STEP.act
            const SIcon = st.icon
            return (
              <li key={s.id} className={`slide-in flex gap-2.5 rounded-lg px-2.5 py-2 text-[14.5px] leading-snug ${st.cls}`}>
                <SIcon size={16} className="shrink-0 mt-0.5" />
                <span className={s.kind === 'ok' ? 'font-mono text-[12.5px] break-all opacity-80' : ''}>{s.text}</span>
              </li>
            )
          })}
          {run.status === 'running' && (
            <li className="flex gap-2.5 px-2.5 py-1.5 text-slate-500 text-sm"><Loader2 size={15} className="animate-spin" /> Gemini is deciding the next step…</li>
          )}
        </ol>
      )}
    </li>
  )
}

export default function AgentRuns({ runs }) {
  const [openId, setOpenId] = useState(null)
  if (!runs.length) {
    return <p className="text-slate-600 p-4">No agent runs yet. When a teacher changes something, or you add a clashing event, Gemini takes over here.</p>
  }
  const current = openId ?? runs[0]?.id
  return (
    <ol className="space-y-2 p-3">
      {runs.map((r) => (
        <RunCard key={r.id} run={r} open={r.id === current} onToggle={() => setOpenId(r.id === current ? -1 : r.id)} />
      ))}
    </ol>
  )
}
