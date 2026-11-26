import { useEffect, useRef } from 'react'
import { useLive } from '../live'

const AGENT_STYLE = {
  Coordinator: 'bg-indigo-100 text-indigo-800',
  Sync: 'bg-sky-100 text-sky-800',
  Tutor: 'bg-violet-100 text-violet-800',
  Planner: 'bg-emerald-100 text-emerald-800',
  Voice: 'bg-pink-100 text-pink-800',
}
const LEVEL_STYLE = {
  info: 'border-slate-200',
  success: 'border-emerald-400',
  warn: 'border-amber-400',
  error: 'border-red-500 bg-red-50',
}

export default function ActivityLog() {
  const { logs } = useLive()
  const box = useRef(null)
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' })
  }, [logs])

  return (
    <div className="card !p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-200 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
        <h2 className="font-bold text-lg">Agent activity</h2>
        <span className="ml-auto text-sm text-slate-500">live</span>
      </div>
      <div ref={box} className="h-[420px] overflow-y-auto p-3 space-y-2">
        {logs.length === 0 && <p className="text-slate-500 p-3">Waiting for the agent…</p>}
        {logs.map((l) => (
          <div key={l.id} className={`slide-in border-l-4 rounded-lg px-3 py-2 bg-white ${LEVEL_STYLE[l.level] || ''}`}>
            <div className="flex items-center gap-2 text-xs mb-0.5">
              <span className={`px-2 py-0.5 rounded-full font-bold ${AGENT_STYLE[l.agent] || 'bg-slate-100'}`}>{l.agent}</span>
              <span className="text-slate-400">{new Date(l.ts * 1000).toLocaleTimeString()}</span>
            </div>
            <p className="text-[15px] leading-snug">{l.message}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
