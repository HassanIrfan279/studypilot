import { useEffect, useRef } from 'react'
import { BrainCircuit, CalendarClock, GraduationCap, Mic, RefreshCw } from 'lucide-react'
import { useLive } from '../live'

const AGENTS = {
  Coordinator: { icon: BrainCircuit, cls: 'bg-indigo-600 text-white' },
  Sync: { icon: RefreshCw, cls: 'bg-sky-600 text-white' },
  Tutor: { icon: GraduationCap, cls: 'bg-violet-600 text-white' },
  Planner: { icon: CalendarClock, cls: 'bg-emerald-600 text-white' },
  Voice: { icon: Mic, cls: 'bg-pink-600 text-white' },
}
const LEVEL = {
  info: 'bg-white',
  success: 'bg-emerald-50',
  warn: 'bg-amber-50',
  error: 'bg-red-50',
}

export default function ActivityLog() {
  const { logs } = useLive()
  const box = useRef(null)
  const first = useRef(true)
  useEffect(() => {
    if (!box.current || !logs.length) return
    // jump to the newest entry on load, then glide for each new step
    box.current.scrollTo({ top: box.current.scrollHeight, behavior: first.current ? 'auto' : 'smooth' })
    first.current = false
  }, [logs])

  return (
    <section className="card !p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-200 flex items-center gap-2.5">
        <span className="relative flex w-2.5 h-2.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
          <span className="relative inline-flex w-2.5 h-2.5 rounded-full bg-emerald-500" />
        </span>
        <h2 className="font-bold text-lg">Agent activity</h2>
        <span className="ml-auto text-sm text-slate-500">every step, live</span>
      </div>
      <ol ref={box} className="h-[440px] overflow-y-auto p-3 space-y-1.5" aria-live="polite">
        {logs.length === 0 && <li className="text-slate-500 p-3">Waiting for the agent…</li>}
        {logs.map((l) => {
          const a = AGENTS[l.agent] || { icon: BrainCircuit, cls: 'bg-slate-600 text-white' }
          const Icon = a.icon
          return (
            <li key={l.id} className={`slide-in rounded-xl px-3 py-2.5 flex gap-3 ${LEVEL[l.level] || 'bg-white'}`}>
              <span className={`grid place-items-center w-8 h-8 rounded-lg shrink-0 ${a.cls}`} title={l.agent}>
                <Icon size={17} strokeWidth={2.3} />
              </span>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2 text-xs">
                  <span className="font-bold text-slate-800">{l.agent}</span>
                  <span className="text-slate-500 tabular">{new Date(l.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                </div>
                <p className={`text-[15px] leading-snug ${l.level === 'error' ? 'text-red-900' : 'text-slate-900'}`}>
                  {l.message.replace(/^[🔊🛠📅🔎✅✔💬🎙🚨]\s*/u, '')}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
