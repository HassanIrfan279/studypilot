import { useEffect, useState } from 'react'
import { start, stop, subscribe } from '../voice'

const LABEL = {
  off: '🎙 Talk to StudyPilot',
  connecting: '⏳ Connecting…',
  listening: '🎙 Listening… (tap to stop)',
  speaking: '🔊 Speaking…',
  error: '⚠ Voice error — retry',
}

export default function VoiceButton() {
  const [s, setS] = useState({ status: 'off' })
  useEffect(() => subscribe(setS), [])
  const on = s.status === 'listening' || s.status === 'speaking' || s.status === 'connecting'
  return (
    <button
      title={s.error || ''}
      onClick={() => (on ? stop() : start())}
      className={`btn-primary !bg-white !text-brand hover:!bg-indigo-50 ${s.status === 'listening' ? 'listening !bg-red-50 !text-red-700' : ''}`}
    >
      {LABEL[s.status] || LABEL.off}
    </button>
  )
}
