import { useEffect, useRef, useState } from 'react'
import { Download, ExternalLink, FileText, Loader2, MessageSquareText, RefreshCw, Send, Sparkles, Wand2, X } from 'lucide-react'
import { api, API_BASE } from '../api'

// The career agent interviews the student, then writes the CV itself (Google Doc + PDF).
function Interview({ onDrafted, onCancel }) {
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const box = useRef(null)

  const ask = async (history, finish = false) => {
    setBusy(finish ? 'draft' : 'ask'); setError(null)
    try {
      const turn = await api.post('/api/cv/interview', { messages: history, finish })
      setMsgs([...history, { role: 'agent', text: turn.message }])
      if (turn.done && turn.draft) onDrafted(turn.draft)
      else if (turn.done) setError("I couldn't save the CV to Drive. Try “Draft my CV now” again.")
    } catch (e) {
      setMsgs(history)
      setError(`Couldn't reach the agent (${e.message}). Try again.`)
    } finally { setBusy(false) }
  }
  useEffect(() => { ask([]) }, [])
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' }) }, [msgs, busy])

  const send = (e) => {
    e?.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    ask([...msgs, { role: 'student', text }])
  }
  const answered = msgs.filter((m) => m.role === 'student').length

  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <MessageSquareText size={24} className="text-brand" />
        <div className="flex-1 min-w-[14rem]">
          <h2 className="text-xl font-extrabold">Let's build your CV</h2>
          <p className="text-sm text-slate-600">Answer in your own words; type “skip” for anything you don't have. It never makes things up.</p>
        </div>
        <button className="btn-primary" onClick={() => ask(msgs, true)} disabled={!!busy || answered < 2}
          title={answered < 2 ? 'Answer a couple of questions first' : 'Write the CV from what you have told me'}>
          {busy === 'draft' ? <Loader2 size={18} className="animate-spin" /> : <Wand2 size={18} />}
          {busy === 'draft' ? 'Writing your CV…' : 'Draft my CV now'}
        </button>
        {onCancel && <button className="btn-ghost" onClick={onCancel} aria-label="Close"><X size={18} /></button>}
      </div>
      <div ref={box} className="h-[380px] overflow-y-auto space-y-3 rounded-xl bg-slate-50 border border-slate-200 p-4">
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'student' ? 'justify-end' : ''}`}>
            <p className={`max-w-[80%] rounded-2xl px-4 py-2.5 whitespace-pre-wrap ${m.role === 'student' ? 'bg-brand text-white rounded-br-md' : 'bg-white border border-slate-200 rounded-bl-md'}`}>{m.text}</p>
          </div>
        ))}
        {busy && (
          <p className="text-slate-500 flex items-center gap-2"><Loader2 size={16} className="animate-spin" />
            {busy === 'draft' ? 'Writing your CV and saving it to Google Docs…' : 'Thinking…'}</p>
        )}
      </div>
      {error && <p className="text-red-700 text-sm">{error}</p>}
      <form onSubmit={send} className="flex gap-2">
        <input className="flex-1 border border-slate-300 rounded-xl px-4 py-2.5" value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={busy ? 'One moment…' : 'Type your answer'} disabled={!!busy} autoFocus />
        <button className="btn-primary" disabled={!!busy || !input.trim()}><Send size={18} /> Send</button>
      </form>
      <p className="text-sm text-slate-500">{answered} answered · about 10–14 questions. You can click “Draft my CV now” at any point.</p>
    </div>
  )
}

function Viewer({ draft, pdfVersion, onRestart, reload }) {
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)
  const act = async (name, fn, okText) => {
    setBusy(name); setNote(null)
    try { await fn(); setNote({ ok: true, text: okText }); reload() }
    catch (e) { setNote({ ok: false, text: e.message }) } finally { setBusy(null) }
  }
  const pdf = `${API_BASE}/api/cv/pdf?v=${pdfVersion}`
  const chips = ['Make it fit on one page', 'More focus on backend', 'Stronger project bullets', 'Shorter summary']

  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <FileText size={24} className="text-brand" />
        <div className="flex-1 min-w-[14rem]">
          <h2 className="text-xl font-extrabold">Your CV {draft ? <span className="text-slate-400 font-semibold text-base">v{draft.version}</span> : null}</h2>
          <p className="text-sm text-slate-600">This is the CV the internship agent attaches to your applications.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {draft?.doc_link && <a className="btn-ghost" href={draft.doc_link} target="_blank" rel="noopener noreferrer"><ExternalLink size={17} /> Edit in Google Docs</a>}
          <a className="btn-ghost" href={pdf} target="_blank" rel="noopener noreferrer" download><Download size={17} /> PDF</a>
          {draft && (
            <button className="btn-ghost" disabled={busy === 'sync'} onClick={() => act('sync', () => api.post('/api/cv/sync'), 'Got your Google Docs edits. Applications will use them.')}>
              {busy === 'sync' ? <Loader2 size={17} className="animate-spin" /> : <RefreshCw size={17} />} I edited it in Docs
            </button>
          )}
          <button className="btn-ghost" onClick={onRestart}><MessageSquareText size={17} /> {draft ? 'Improve with the agent' : 'Build a new CV with the agent'}</button>
        </div>
      </div>

      {draft && (
        <div className="space-y-2">
          <div className="flex gap-2 flex-wrap">
            {chips.map((c) => <button key={c} className="text-sm px-3 py-1 rounded-full bg-indigo-50 text-indigo-900 hover:bg-indigo-100 font-semibold" disabled={!!busy} onClick={() => setInstruction(c)}>{c}</button>)}
          </div>
          <form className="flex gap-2 flex-wrap" onSubmit={(e) => {
            e.preventDefault()
            if (!instruction.trim()) return
            act('edit', () => api.post('/api/cv/edit', { instruction: instruction.trim() }), 'CV updated in Google Docs and PDF.').then(() => setInstruction(''))
          }}>
            <input className="flex-1 min-w-[16rem] border border-slate-300 rounded-xl px-3 py-2" value={instruction} onChange={(e) => setInstruction(e.target.value)}
              placeholder="Ask for a change, e.g. “add my new React Native app”" />
            <button className="btn-primary" disabled={busy === 'edit' || !instruction.trim()}>
              {busy === 'edit' ? <Loader2 size={17} className="animate-spin" /> : <Sparkles size={17} />} {busy === 'edit' ? 'Updating…' : 'Update CV'}
            </button>
          </form>
        </div>
      )}
      {note && <p className={`text-sm font-semibold ${note.ok ? 'text-emerald-800' : 'text-red-800'}`}>{note.text}</p>}

      <iframe key={pdfVersion} title="CV preview" src={pdf} className="w-full h-[760px] rounded-xl border border-slate-200 bg-slate-100" />
    </div>
  )
}

export default function CvBuilder({ start = false, onClose, onChanged }) {
  const [state, setState] = useState(null)
  const [mode, setMode] = useState(start ? 'chat' : 'view')
  const load = () => api.get('/api/cv').then(setState).catch(() => setState({ draft: null, has_pdf: false }))
  useEffect(() => { load() }, [])

  if (!state) return <div className="card flex gap-3 items-center"><Loader2 className="animate-spin text-brand" /> Loading your CV…</div>
  if (mode === 'chat' || (!state.has_pdf && !state.draft)) {
    return <Interview onCancel={state.has_pdf ? () => setMode('view') : onClose}
      onDrafted={() => { load().then(() => setMode('view')); onChanged?.() }} />
  }
  return <Viewer draft={state.draft} pdfVersion={state.pdf_version} onRestart={() => setMode('chat')} reload={() => { load(); onChanged?.() }} />
}
