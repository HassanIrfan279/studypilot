import { useEffect, useState } from 'react'
import { api } from '../api'
import { announce } from '../voice'

export default function DailyBrief({ tick }) {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = (refresh = false) => {
    setLoading(true)
    api.get(`/api/brief${refresh ? '?refresh=true' : ''}`).then(setBrief).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => load(), [tick])

  return (
    <div className="card bg-gradient-to-br from-indigo-700 to-indigo-900 !border-0 text-white">
      <div className="flex items-center gap-3 mb-2">
        <h2 className="text-xl font-extrabold">☀️ Your daily brief</h2>
        <div className="ml-auto flex gap-2">
          {brief && (
            <button className="btn-ghost !bg-white/15 !text-white !py-1" onClick={() => announce(brief.text.replace(/[*#]/g, ''))}>🔊 Read</button>
          )}
          <button className="btn-ghost !bg-white/15 !text-white !py-1" onClick={() => load(true)} disabled={loading}>
            {loading ? '…' : '↻'}
          </button>
        </div>
      </div>
      <p className="whitespace-pre-wrap text-[17px] leading-relaxed text-indigo-50">
        {brief ? brief.text.replace(/\*\*/g, '') : loading ? 'Gemini is writing your brief…' : 'Sync to get your brief.'}
      </p>
    </div>
  )
}
