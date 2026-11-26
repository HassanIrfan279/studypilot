import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { marked } from 'marked'
import { AlertTriangle, ArrowLeft, Download, FolderOpen, Loader2, NotebookPen, Pencil, RotateCcw, RotateCw, Save, Sparkles, Wand2 } from 'lucide-react'
import { api, API_BASE } from '../api'
import { useLive } from '../live'
import CourseTag from '../components/CourseTag'

const CHIPS = [
  'Make it simpler',
  'Add another worked example to each topic',
  'Add 5 more practice questions with answers',
  'Make the exam cheat sheet shorter and sharper',
  'Explain the hardest topic in Roman Urdu',
]

export default function Notes() {
  const { id } = useParams()
  const { tick } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)   // 'generate' | 'ai' | 'save' | 'pdf' | 'undo'
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [instruction, setInstruction] = useState('')
  const body = useRef(null)

  const load = (q = '') => api.get(`/api/notes/${id}${q}`).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  useEffect(() => { setData(null); load() }, [id])
  // The agent may rewrite the notes on its own (e.g. after a weak quiz): pick that up live
  useEffect(() => { if (data && !editing && !busy) load() }, [tick])

  const notes = data?.notes
  // Notes come from Gemini reading lecture files: strip anything executable before rendering
  const html = useMemo(() => (notes ? marked.parse(notes.md)
    .replace(/<(script|iframe|object|embed|style)[\s\S]*?<\/\1>/gi, '')
    .replace(/<(script|iframe|object|embed)[^>]*>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2/gi, '$1="#"') : ''), [notes?.md])
  const toc = useMemo(() => (notes?.md.match(/^## .+$/gm) || []).map((h, i) => [i, h.slice(3).replace(/\*\*/g, '')])
    .filter(([, t]) => t.trim().toLowerCase() !== 'contents'), [notes?.md])
  useEffect(() => {
    body.current?.querySelectorAll('h2').forEach((h, i) => { h.id = `sec-${i}` })
  }, [html])

  const act = async (kind, fn) => {
    setBusy(kind); setError(null)
    try { await fn() } catch (e) { setError(e.message) } finally { setBusy(null) }
  }
  const generate = (refresh) => act('generate', () => load(refresh ? '?refresh=true' : '?generate=true'))
  const aiEdit = (text) => act('ai', async () => {
    const n = await api.post(`/api/notes/${id}/ai-edit`, { instruction: text })
    setData((d) => ({ ...d, notes: n })); setInstruction('')
  })
  const save = () => act('save', async () => {
    const n = await api.put(`/api/notes/${id}`, { md: draft })
    setData((d) => ({ ...d, notes: n })); setEditing(false)
  })
  const undo = () => act('undo', async () => {
    const n = await api.post(`/api/notes/${id}/undo`)
    setData((d) => ({ ...d, notes: n }))
  })
  const pdf = () => act('pdf', async () => {
    const res = await fetch(`${API_BASE}/api/notes/${id}/pdf`)
    if (!res.ok) { window.print(); return }   // offline? the browser's own "Save as PDF"
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${data.item.title} - StudyPilot notes.pdf`
    a.click()
    URL.revokeObjectURL(a.href)
  })

  if (error && !data) return <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={22} /> {error}</div>
  if (!data) return <div className="card text-lg flex items-center gap-3"><Loader2 size={24} className="animate-spin text-brand" /> Loading notes…</div>

  const item = data.item
  return (
    <div className="space-y-5">
      <div className="card flex items-start gap-5 flex-wrap">
        <div className="flex-1 min-w-[20rem]">
          <Link to={`/prep/${id}`} className="text-brand font-semibold inline-flex items-center gap-1 mb-1"><ArrowLeft size={17} /> Prep pack</Link>
          <h1 className="text-3xl font-extrabold flex items-center gap-3"><NotebookPen size={30} className="text-brand" /> {item?.title} <span className="text-slate-400">notes</span></h1>
          <div className="flex items-center gap-3 flex-wrap mt-2">
            <CourseTag name={data.course_name} color={data.color} />
            {notes && (
              <span className={`text-sm font-semibold px-2.5 py-1 rounded-full ${notes.reason?.includes('quiz') || notes.reason?.includes('agent') ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'}`}>
                Version {notes.version} · {notes.reason}
              </span>
            )}
          </div>
        </div>
        {notes && (
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary" onClick={pdf} disabled={!!busy}>
              {busy === 'pdf' ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />} Download PDF
            </button>
            {notes.doc_link && <a className="btn-ghost" href={notes.doc_link} target="_blank" rel="noreferrer"><FolderOpen size={18} /> Open in Drive</a>}
            {editing
              ? <button className="btn-primary" onClick={save} disabled={!!busy}><Save size={18} /> {busy === 'save' ? 'Saving…' : 'Save'}</button>
              : <button className="btn-ghost" onClick={() => { setDraft(notes.md); setEditing(true) }}><Pencil size={18} /> Edit</button>}
            {editing && <button className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>}
            {!editing && notes.versions > 0 && <button className="btn-ghost" onClick={undo} disabled={!!busy}><RotateCcw size={18} /> Undo</button>}
            {!editing && <button className="btn-ghost" onClick={() => generate(true)} disabled={!!busy}><RotateCw size={18} /> Rewrite</button>}
          </div>
        )}
      </div>

      {error && <div className="card !bg-red-50 text-red-900 flex gap-3 items-center"><AlertTriangle size={20} /> {error}</div>}

      {!notes && (
        <div className="card text-center py-12">
          <NotebookPen size={44} className="mx-auto text-brand mb-3" />
          <h2 className="text-2xl font-bold">No notes yet for this deadline</h2>
          <p className="text-slate-600 mt-1 mb-5">I'll read the actual lecture files and write step-by-step notes: big idea, intuition, worked example, common mistakes, quick check.</p>
          <button className="btn-primary !text-lg" onClick={() => generate(false)} disabled={!!busy}>
            {busy === 'generate' ? <><Loader2 size={20} className="animate-spin" /> Reading lectures and writing… (~30s)</> : <><Sparkles size={20} /> Write my notes</>}
          </button>
        </div>
      )}

      {notes && (
        <div className="grid lg:grid-cols-[260px_minmax(0,1fr)] gap-5 items-start">
          <aside className="card !p-4 lg:sticky lg:top-[92px] space-y-1">
            <p className="font-bold text-slate-500 text-sm uppercase tracking-wide mb-2">Contents</p>
            {toc.map(([i, t]) => (
              <button key={i} onClick={() => document.getElementById(`sec-${i}`)?.scrollIntoView({ behavior: 'smooth' })}
                className={`block w-full text-left px-2 py-1.5 rounded-lg hover:bg-indigo-50 font-medium ${t.includes('weak') ? 'text-amber-800' : 'text-slate-700'}`}>{t}</button>
            ))}
          </aside>

          <div className="space-y-5 min-w-0">
            {!editing && (
              <div className="card !p-4 !bg-indigo-50 !border-indigo-200">
                <p className="font-bold text-indigo-950 flex items-center gap-2 mb-2"><Wand2 size={19} /> Ask the AI to change these notes</p>
                <div className="flex gap-2">
                  <input value={instruction} onChange={(e) => setInstruction(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && instruction.trim() && aiEdit(instruction)}
                    placeholder="e.g. explain Dijkstra with a smaller graph" disabled={!!busy}
                    className="flex-1 border border-indigo-300 rounded-xl px-4 py-2.5 text-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  <button className="btn-primary" disabled={!!busy || !instruction.trim()} onClick={() => aiEdit(instruction)}>
                    {busy === 'ai' ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />} Apply
                  </button>
                </div>
                <div className="flex gap-2 flex-wrap mt-3">
                  {CHIPS.map((c) => <button key={c} className="text-sm font-semibold px-3 py-1.5 rounded-full bg-white border border-indigo-200 text-indigo-900 hover:bg-indigo-100 disabled:opacity-50" disabled={!!busy} onClick={() => aiEdit(c)}>{c}</button>)}
                </div>
                {busy === 'ai' && <p className="text-indigo-900 mt-3 flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Rewriting your notes… (~20s)</p>}
              </div>
            )}

            {editing ? (
              <div className="card">
                <p className="text-slate-600 mb-2">Edit freely. <b>## Heading</b>, <b>**bold**</b>, <b>- bullet</b>. Your edits sync to the Google Doc.</p>
                <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck
                  className="w-full min-h-[70vh] font-mono text-[15px] leading-relaxed border border-slate-300 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            ) : (
              <article className={`card notes-print ${busy === 'ai' || busy === 'generate' ? 'opacity-50' : ''}`}>
                <div ref={body} className="notes-body" dangerouslySetInnerHTML={{ __html: html }} />
              </article>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
