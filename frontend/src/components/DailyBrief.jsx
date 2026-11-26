import { useEffect, useState } from 'react'
import { RotateCw, Sun, Volume2 } from 'lucide-react'
import { api } from '../api'
import { announce } from '../voice'

// Gemini writes the brief as "Due soon / What changed / Study today" sections; render them as columns.
function parse(text) {
  const clean = text.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/\p{Extended_Pictographic}️?\s*/gu, '')
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

export default function DailyBrief({ tick }) {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = (refresh = false) => {
    setLoading(true)
    api.get(`/api/brief${refresh ? '?refresh=true' : ''}`).then(setBrief).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => load(), [tick])

  const sections = brief ? parse(brief.text) : null
  return (
    <section className="rounded-2xl bg-indigo-950 text-white p-6 shadow-lg">
      <div className="flex items-center gap-3 mb-4">
        <Sun size={24} className="text-amber-300" />
        <h2 className="text-2xl font-extrabold">Your daily brief</h2>
        <div className="ml-auto flex gap-2">
          {brief && (
            <button className="btn-on-dark !py-1.5" onClick={() => announce(brief.text.replace(/[*#-]/g, ''))}>
              <Volume2 size={18} /> Read aloud
            </button>
          )}
          <button className="btn-on-dark !py-1.5 !px-2.5" onClick={() => load(true)} disabled={loading} aria-label="Refresh brief">
            <RotateCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
      {!brief && <p className="text-lg text-indigo-200">{loading ? 'Gemini is writing your brief…' : 'Sync to get your brief.'}</p>}
      {brief && sections && (
        <div className="grid md:grid-cols-3 gap-5">
          {sections.map((s) => (
            <div key={s.head}>
              <h3 className="text-sm font-bold uppercase tracking-wide text-amber-200 mb-1.5">{s.head}</h3>
              {s.lines.map((l, i) => <p key={i} className="text-[17px] leading-relaxed text-white">{l}</p>)}
            </div>
          ))}
        </div>
      )}
      {brief && !sections && <p className="whitespace-pre-wrap text-lg leading-relaxed">{brief.text.replace(/\*\*/g, '')}</p>}
    </section>
  )
}
