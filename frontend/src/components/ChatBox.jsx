import { useEffect, useRef, useState } from 'react'
import { Mic, MessageSquareText, SendHorizontal } from 'lucide-react'
import { api } from '../api'
import { subscribe } from '../voice'

// Text chat with the same agent + tools as voice. Also shows the live voice transcript.
export default function ChatBox() {
  const [msgs, setMsgs] = useState([
    { role: 'agent', text: "Hi! Ask me anything — \"What's due this week?\", \"Quiz me on OOP\", \"Am I ready?\"" },
  ])
  const [voiceLines, setVoiceLines] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const box = useRef(null)

  useEffect(() => subscribe((s) => setVoiceLines(s.transcript)), [])
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }) }, [msgs, voiceLines])

  const send = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')
    setMsgs((m) => [...m, { role: 'user', text }])
    setBusy(true)
    try {
      const { reply } = await api.post('/api/chat', { message: text })
      setMsgs((m) => [...m, { role: 'agent', text: reply }])
    } catch (err) {
      setMsgs((m) => [...m, { role: 'agent', text: `Sorry, that didn't work: ${err.message}` }])
    } finally {
      setBusy(false)
    }
  }

  const all = [...msgs, ...voiceLines.map((v) => ({ ...v, voice: true }))]
  return (
    <div className="card !p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-200 font-bold text-lg flex items-center gap-2.5">
        <MessageSquareText size={20} className="text-brand" /> Ask StudyPilot
      </div>
      <div ref={box} className="h-[300px] overflow-y-auto p-4 space-y-3">
        {all.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : ''}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2 whitespace-pre-wrap ${m.role === 'user' ? 'bg-brand text-white' : 'bg-slate-100'}`}>
              {m.voice && <span className="text-xs opacity-70 flex items-center gap-1 mb-0.5"><Mic size={12} /> voice</span>}
              {m.text}
            </div>
          </div>
        ))}
        {busy && <div className="text-slate-500">StudyPilot is thinking…</div>}
      </div>
      <form onSubmit={send} className="p-3 border-t border-slate-200 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type in English or Urdu…"
          className="flex-1 rounded-xl border border-slate-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        <button className="btn-primary !px-3" disabled={busy || !input.trim()} aria-label="Send"><SendHorizontal size={20} /></button>
      </form>
    </div>
  )
}
