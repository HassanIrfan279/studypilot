import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Mic, Square, Volume2 } from 'lucide-react'
import { start, stop, subscribe } from '../voice'

const STATES = {
  off: { icon: Mic, label: 'Talk to StudyPilot', cls: 'bg-white text-brand hover:bg-indigo-50' },
  connecting: { icon: Loader2, label: 'Connecting…', cls: 'bg-white text-brand', spin: true },
  listening: { icon: Square, label: 'Listening · tap to stop', cls: 'bg-red-600 text-white listening' },
  speaking: { icon: Volume2, label: 'Speaking…', cls: 'bg-emerald-500 text-white' },
  error: { icon: AlertTriangle, label: 'Voice error · retry', cls: 'bg-amber-300 text-amber-950' },
}

export default function VoiceButton() {
  const [s, setS] = useState({ status: 'off' })
  useEffect(() => subscribe(setS), [])
  const on = ['listening', 'speaking', 'connecting'].includes(s.status)
  const st = STATES[s.status] || STATES.off
  const Icon = st.icon
  return (
    <button title={s.error || ''} onClick={() => (on ? stop() : start())}
      className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 font-bold transition cursor-pointer ${st.cls}`}>
      <Icon size={19} className={st.spin ? 'animate-spin' : ''} strokeWidth={2.4} />
      {st.label}
    </button>
  )
}
