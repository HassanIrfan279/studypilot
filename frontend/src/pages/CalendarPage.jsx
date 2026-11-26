import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'
import { BookOpen, CalendarPlus, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { useLive } from '../live'

const LEGEND = [
  ['session', 'Study session (agent)', '#3f51b5'],
  ['deadline', 'Deadline', '#d50000'],
  ['timetable', 'Class / commitment', '#616161'],
  ['mine', 'Your own event', '#64748b'],
]

export default function CalendarPage() {
  const { tick } = useLive()
  const cal = useRef(null)
  const navigate = useNavigate()
  const [range, setRange] = useState(null)
  const [events, setEvents] = useState([])
  const [draft, setDraft] = useState(null)      // new event being created
  const [selected, setSelected] = useState(null) // clicked event
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!range) return
    api.get(`/api/calendar?start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`)
      .then(setEvents).catch(() => {})
  }, [range])
  useEffect(() => { load() }, [load, tick])

  const fcEvents = events.map((e) => ({
    id: e.id, title: e.title.replace(/^[📘🎯🏫📌]\s*/u, ''), start: e.start, end: e.end, allDay: e.allDay,
    editable: e.editable, backgroundColor: e.kind === 'mine' ? '#ffffff' : e.color,
    borderColor: e.color, textColor: e.kind === 'mine' ? '#0f172a' : '#ffffff',
    classNames: [`ev-${e.kind}`, e.done ? 'ev-done' : ''], extendedProps: e,
  }))

  const move = async (info) => {
    const e = info.event
    try {
      await api.patch(`/api/calendar/events/${e.id}`, { start: e.start.toISOString(), end: (e.end || e.start).toISOString() })
      load()
    } catch { info.revert() }
  }

  const create = async () => {
    if (!draft.title.trim()) return
    setBusy(true)
    try {
      await api.post('/api/calendar/events', { title: draft.title, start: draft.start, end: draft.end })
      setDraft(null); load()
    } finally { setBusy(false) }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await api.del(`/api/calendar/events/${selected.id}`)
      setSelected(null); load()
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end gap-x-8 gap-y-3 flex-wrap">
        <div className="flex-1 min-w-[22rem]">
          <h1 className="text-3xl font-extrabold">Calendar</h1>
          <p className="text-slate-600">Synced both ways with Google Calendar. Drag to move, drag on empty time to add. The agent replans around anything you add.</p>
        </div>
        <ul className="flex gap-4 flex-wrap text-sm font-semibold text-slate-700">
          {LEGEND.map(([k, label, c]) => (
            <li key={k} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded" style={{ background: k === 'mine' ? '#fff' : c, border: `2px solid ${c}` }} />{label}
            </li>
          ))}
        </ul>
      </div>

      <div className="card !p-3 sp-calendar">
        <FullCalendar
          ref={cal}
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          headerToolbar={{ left: 'prev,next today', center: 'title', right: 'timeGridDay,timeGridWeek,dayGridMonth' }}
          firstDay={1}
          slotMinTime="07:00:00"
          slotMaxTime="24:00:00"
          height="auto"
          nowIndicator
          allDaySlot={false}
          selectable
          selectMirror
          eventDurationEditable
          events={fcEvents}
          datesSet={(d) => setRange({ start: d.start.toISOString(), end: d.end.toISOString() })}
          select={(s) => setDraft({ title: '', start: s.start.toISOString(), end: s.end.toISOString(), label: `${s.start.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })} – ${s.end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` })}
          eventDrop={move}
          eventResize={move}
          eventClick={(info) => setSelected(info.event.extendedProps)}
        />
      </div>

      {draft && (
        <div className="fixed inset-0 z-50 bg-slate-950/50 grid place-items-center p-6" role="dialog" aria-modal="true">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="text-xl font-bold flex items-center gap-2"><CalendarPlus size={22} /> Add to your calendar</h2>
            <p className="text-slate-600 mt-1 tabular">{draft.label}</p>
            <input autoFocus value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && create()}
              placeholder="e.g. Cricket match, Family dinner, Gym"
              className="w-full mt-4 border border-slate-300 rounded-xl px-4 py-2.5 text-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <div className="flex gap-2 justify-end mt-5">
              <button className="btn-ghost" onClick={() => setDraft(null)}>Cancel</button>
              <button className="btn-primary" onClick={create} disabled={busy || !draft.title.trim()}>{busy ? 'Adding…' : 'Add event'}</button>
            </div>
          </div>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 z-50 bg-slate-950/50 grid place-items-center p-6" role="dialog" aria-modal="true" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <span className="w-4 h-4 rounded mt-1.5" style={{ background: selected.color }} />
              <h2 className="text-xl font-bold flex-1">{selected.title}</h2>
              <button onClick={() => setSelected(null)} aria-label="Close" className="text-slate-500 hover:text-slate-900"><X size={22} /></button>
            </div>
            <p className="text-slate-600 mt-1 tabular">
              {new Date(selected.start).toLocaleString([], { weekday: 'long', hour: '2-digit', minute: '2-digit' })} – {new Date(selected.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
            <p className="text-sm text-slate-500 mt-1">
              {{ session: 'Booked by the agent', deadline: 'Deadline (managed by StudyPilot)', timetable: 'From your timetable', mine: 'Your own event' }[selected.kind]}
              {selected.done && ' · completed'}
            </p>
            <div className="flex gap-2 mt-5 flex-wrap">
              {selected.assessment_id && (
                <button className="btn-primary" onClick={() => navigate(`/prep/${selected.assessment_id}`)}><BookOpen size={18} /> Open prep pack</button>
              )}
              {(selected.kind === 'session' || selected.kind === 'mine') && !selected.recurring && (
                <button className="btn-ghost !text-red-700" onClick={remove} disabled={busy}><Trash2 size={18} /> Delete</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
