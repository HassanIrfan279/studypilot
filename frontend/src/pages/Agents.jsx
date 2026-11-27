import { ArrowRight, Sparkles } from 'lucide-react'
import AgentAvatar from '../components/AgentAvatar'
import { AGENTS } from '../agents'
import { useLive } from '../live'

function ago(ts) {
  const s = Date.now() / 1000 - ts
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

const FLOW = [
  ['scout', 'notices a change'],
  ['atlas', 'decides what to do'],
  ['chrono', 'plans the time'],
  ['aegis', 'checks the plan'],
  ['echo', 'tells you'],
]

export default function Agents() {
  const { logs } = useLive()
  const last = Object.fromEntries(AGENTS.map((a) => [a.id, [...(logs || [])].reverse().find(a.match)]))
  const byId = Object.fromEntries(AGENTS.map((a) => [a.id, a]))

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="sp-hero relative overflow-hidden rounded-3xl p-8 md:p-10 text-white">
        <div className="relative z-10 max-w-2xl xl:max-w-[46%]">
          <p className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-200 bg-white/10 rounded-full px-3 py-1">
            <Sparkles size={15} /> 8 AI agents · working for you around the clock
          </p>
          <h1 className="text-3xl md:text-4xl font-extrabold mt-4 leading-tight">Meet your agent team</h1>
          <p className="text-indigo-100 text-lg mt-3">
            Each agent has one job. Together they watch your classes, plan your time, teach you, protect your
            sleep, and chase your career, and they tell you what they did and why.
          </p>
        </div>
        <div className="absolute right-6 bottom-0 hidden xl:flex items-end gap-1 z-10" aria-hidden="true">
          {AGENTS.slice(0, 5).map((a, i) => (
            <div key={a.id} className="sp-rise" style={{ animationDelay: `${i * 90}ms` }}>
              <AgentAvatar agent={a} size={i === 2 ? 132 : 104} />
            </div>
          ))}
        </div>
      </section>

      {/* How they work together */}
      <section className="card">
        <h2 className="text-lg font-extrabold mb-4">How they work together</h2>
        <ol className="flex flex-wrap items-center gap-y-4">
          {FLOW.map(([id, what], i) => (
            <li key={id} className="flex items-center">
              <div className="flex flex-col items-center text-center w-28">
                <AgentAvatar agent={byId[id]} size={60} />
                <span className="font-bold mt-1">{byId[id].name}</span>
                <span className="text-xs text-slate-500 leading-tight">{what}</span>
              </div>
              {i < FLOW.length - 1 && <span className="sp-flow mx-1 hidden sm:block" aria-hidden="true"><ArrowRight size={20} /></span>}
            </li>
          ))}
        </ol>
        <p className="text-sm text-slate-600 mt-4">
          Alongside them: <b>Sage</b> teaches, <b>Luna</b> reviews your day every night, and <b>Nova</b> runs your internship hunt.
        </p>
      </section>

      {/* The team */}
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {AGENTS.map((a, i) => {
          const l = last[a.id]
          const active = l && Date.now() / 1000 - l.ts < 120
          return (
            <article key={a.id} className="sp-agent-card sp-rise card !p-5 flex flex-col"
              style={{ animationDelay: `${i * 70}ms`, '--agent': a.color }}>
              <div className="flex items-center gap-3">
                <AgentAvatar agent={a} size={84} active={active} />
                <div className="min-w-0">
                  <h3 className="text-xl font-extrabold leading-tight">{a.name}</h3>
                  <p className="text-sm font-semibold" style={{ color: a.color }}>{a.role}</p>
                  <p className={`text-xs font-bold mt-1 inline-flex items-center gap-1.5 ${active ? 'text-emerald-700' : 'text-slate-500'}`}>
                    <span className={`w-2 h-2 rounded-full ${active ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
                    {active ? 'Working now' : l ? `Active ${ago(l.ts)}` : 'Standing by'}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-[15px] text-slate-800">{a.mission}</p>
              <ul className="mt-3 space-y-1.5 text-sm text-slate-700 flex-1">
                {a.does.map((d) => (
                  <li key={d} className="flex gap-2"><span className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: a.color }} />{d}</li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {a.uses.map((u) => <span key={u} className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700">{u}</span>)}
              </div>
              {l && (
                <p className="mt-3 text-xs text-slate-500 border-t border-slate-100 pt-2 line-clamp-2" title={l.message}>
                  <b className="text-slate-700">Latest:</b> {l.message}
                </p>
              )}
            </article>
          )
        })}
      </section>
    </div>
  )
}
