import { useEffect, useRef, useState } from 'react'
import { Camera, GraduationCap, Loader2, SendHorizontal, Sparkles } from 'lucide-react'
import { api } from '../api'

function toBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1])
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

function ProfileCard({ profile, onSave, saving }) {
  const [addToCal, setAddToCal] = useState(true)
  const row = (label, value) => value ? (
    <div className="grid grid-cols-[11rem_1fr] gap-3 py-2 border-b border-slate-100">
      <dt className="font-semibold text-slate-600">{label}</dt><dd>{value}</dd>
    </div>
  ) : null
  return (
    <section className="card">
      <h2 className="text-2xl font-extrabold flex items-center gap-2"><Sparkles size={22} className="text-amber-500" /> Here's what I learned about you</h2>
      <p className="text-lg text-slate-700 mt-2 max-w-[75ch]">{profile.summary}</p>
      <dl className="mt-4">
        {row('Goal', profile.goals)}
        {row('Target GPA', profile.target_gpa)}
        {row('Hardest courses', profile.hardest_courses?.join(', '))}
        {row('Study per day', profile.study_hours_per_day ? `${profile.study_hours_per_day} hours` : '')}
        {row('Best time', profile.best_study_time)}
        {row('Sleep', profile.sleep_time && `${profile.sleep_time} → ${profile.wake_time}`)}
        {row('Distractions', profile.distractions)}
        {row('Language', profile.language)}
        {row('Strictness', profile.strictness)}
      </dl>
      {profile.weekly_blocks?.length > 0 && (
        <>
          <h3 className="font-bold mt-5 mb-2">Your week ({profile.weekly_blocks.length} fixed blocks)</h3>
          <ul className="grid sm:grid-cols-2 gap-1.5 text-[15px]">
            {profile.weekly_blocks.map((b, i) => (
              <li key={i} className="flex gap-2 bg-slate-50 rounded-lg px-3 py-1.5">
                <span className="font-semibold w-24 shrink-0">{b.day.slice(0, 3)} {b.start}</span>
                <span className="truncate">{b.label}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <label className="flex items-center gap-2.5 mt-5 font-semibold">
        <input type="checkbox" className="w-5 h-5" checked={addToCal} onChange={(e) => setAddToCal(e.target.checked)} />
        Add my classes and commitments to Google Calendar as weekly events
      </label>
      <button className="btn-primary text-lg mt-5" onClick={() => onSave(addToCal)} disabled={saving}>
        {saving ? <><Loader2 className="animate-spin" size={20} /> Saving and re-planning…</> : 'Save and let StudyPilot re-plan around me'}
      </button>
    </section>
  )
}

export default function Onboarding() {
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [profile, setProfile] = useState(null)
  const [saving, setSaving] = useState(false)
  const box = useRef(null)
  const fileRef = useRef(null)

  const ask = async (history) => {
    setBusy(true)
    try {
      const turn = await api.post('/api/interview', { messages: history })
      setMsgs([...history, { role: 'agent', text: turn.message }])
      if (turn.done && turn.profile) setProfile(turn.profile)
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

  const uploadTimetable = async (file) => {
    if (!file) return
    setBusy(true)
    try {
      const { blocks } = await api.post('/api/interview/timetable', { data_base64: await toBase64(file), mime: file.type || 'image/jpeg' })
      const text = 'Here is my timetable (read from my photo): ' +
        blocks.map((b) => `${b.day} ${b.start}-${b.end} ${b.label}`).join('; ')
      await ask([...msgs, { role: 'student', text }])
    } catch (err) {
      setMsgs((m) => [...m, { role: 'agent', text: `I couldn't read that photo (${err.message}). Type your timetable instead?` }])
      setBusy(false)
    }
  }

  const save = async (addToCalendar) => {
    setSaving(true)
    try {
      await api.post('/api/profile', { profile, add_to_calendar: addToCalendar })
      window.location.href = '/' // reload so the app picks up the new profile
    } finally { setSaving(false) }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-4">
        <span className="grid place-items-center w-14 h-14 rounded-2xl bg-slate-900 text-white"><GraduationCap size={30} /></span>
        <div>
          <h1 className="text-3xl font-extrabold">Let's get to know you</h1>
          <p className="text-slate-600 text-lg">A short interview so I can plan around your real life. About 3 minutes.</p>
        </div>
      </div>

      <section className="card !p-0 overflow-hidden">
        <div ref={box} className="h-[460px] overflow-y-auto p-5 space-y-3">
          {msgs.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'student' ? 'justify-end' : ''}`}>
              <p className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-[17px] leading-relaxed whitespace-pre-wrap ${m.role === 'student' ? 'bg-brand text-white' : 'bg-slate-100'}`}>{m.text}</p>
            </div>
          ))}
          {busy && <p className="flex items-center gap-2 text-slate-500"><Loader2 size={18} className="animate-spin" /> Thinking…</p>}
        </div>
        {!profile && (
          <form onSubmit={send} className="p-3 border-t border-slate-200 flex gap-2">
            <button type="button" className="btn-ghost !px-3" title="Upload a photo of your timetable" onClick={() => fileRef.current?.click()} disabled={busy}>
              <Camera size={20} /> <span className="hidden sm:inline">Timetable photo</span>
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => uploadTimetable(e.target.files?.[0])} />
            <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} autoFocus
              placeholder="Type your answer…" aria-label="Your answer"
              className="flex-1 rounded-xl border border-slate-300 px-4 py-2 text-[17px] focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button className="btn-primary !px-3" disabled={busy || !input.trim()} aria-label="Send"><SendHorizontal size={20} /></button>
          </form>
        )}
      </section>

      {profile && <ProfileCard profile={profile} onSave={save} saving={saving} />}
    </div>
  )
}
