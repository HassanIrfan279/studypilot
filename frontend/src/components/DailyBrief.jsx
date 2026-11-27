import { useEffect, useState } from 'react'
import { AlarmClock, BookOpenCheck, RotateCw, Sparkles, Sun, Volume2 } from 'lucide-react'
import { api } from '../api'
import { announce } from '../voice'

// Gemini writes the brief as "Due soon / What changed / Study today" sections; render them as columns.
function parse(text) {
  const clean = (text || '').replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/\p{Extended_Pictographic}️?\s*/gu, '')
  const heads = ['Due soon', 'What changed', 'Study today']
  const sections = []
  let current = null
  for (const raw of clean.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const head = heads.find((h) => line.toLowerCase().replace(/[:：]$/, '').startsWith(h.toLowerCase()))
    if (head) {
      current = { head, lines: [] }
      sections.push(current)
      const rest = line.slice(head.length).replace(/^[:：\s-]+/, '')
      if (rest) current.lines.push(rest)
    } else if (current) {
      current.lines.push(line.replace(/^[-•*]\s*/, ''))
    }
  }
  return sections.length ? sections : null
}

// Three sections, three colors: urgent (rose), news (sky), action (emerald)
const THEME = {
  'Due soon': { icon: AlarmClock, cls: 'from-rose-600 to-orange-600' },
  'What changed': { icon: Sparkles, cls: 'from-sky-600 to-cyan-700' },
  'Study today': { icon: BookOpenCheck, cls: 'from-emerald-600 to-teal-700' },
}

export default function DailyBrief({ tick }) {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = (refresh = false) => {
    setLoading(true)
    api.get(`/api/brief${refresh ? '?refresh=true' : ''}`).then(setBrief).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => load(), [tick])

  const sections = brief?.text ? parse(brief.text) : null
  return (
    <section className="sp-hero relative overflow-hidden rounded-3xl text-white p-5 md:p-6 shadow-lg">
      <div className="relative z-10 flex items-center gap-3 mb-4">
        <Sun size={24} className="text-amber-300" />
        <h2 className="text-xl font-extrabold">Your daily brief</h2>
        <div className="ml-auto flex gap-2">
          {brief && (
            <button className="btn-on-dark !py-1.5" onClick={() => announce(brief.text.replace(/[*#-]/g, ''))}>
              <Volume2 size={18} /> <span className="hidden sm:inline">Read aloud</span>
            </button>
          )}
          <button className="btn-on-dark !py-1.5 !px-2.5" onClick={() => load(true)} disabled={loading} aria-label="Refresh brief">
            <RotateCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
      {!brief && <p className="relative z-10 text-base text-indigo-200">{loading ? 'Gemini is writing your brief…' : 'Sync to get your brief.'}</p>}
      {brief && sections && (
        <div className="relative z-10 grid md:grid-cols-3 gap-4">
          {sections.map((s, i) => {
            const t = THEME[s.head] || THEME['What changed']
            const Icon = t.icon
            return (
              <div key={s.head} className={`sp-rise rounded-2xl p-4 bg-gradient-to-br ${t.cls} ring-1 ring-white/15 shadow-lg`}
                style={{ animationDelay: `${i * 80}ms` }}>
                <h3 className="flex items-center gap-2 text-sm font-extrabold uppercase tracking-wide mb-2">
                  <span className="grid place-items-center w-7 h-7 rounded-lg bg-white/20"><Icon size={16} /></span>{s.head}
                </h3>
                <div className="space-y-1.5">
                  {s.lines.map((l, j) => <p key={j} className="text-[15px] leading-relaxed text-white">{l}</p>)}
                </div>
              </div>
            )
          })}
        </div>
      )}
      {brief && !sections && <p className="relative z-10 whitespace-pre-wrap text-base leading-relaxed">{brief.text.replace(/\*\*/g, '')}</p>}
    </section>
  )
}
