// Live connection to the backend activity feed (WebSocket). Shares log + a refresh counter.
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, WS_BASE } from './api'
import { speakAloud } from './voice'

const LiveContext = createContext({ logs: [], tick: 0, connected: false, toast: null })
export const useLive = () => useContext(LiveContext)

export function LiveProvider({ children }) {
  const [logs, setLogs] = useState([])
  const [tick, setTick] = useState(0)
  const [connected, setConnected] = useState(false)
  const [toast, setToast] = useState(null)
  const [runs, setRuns] = useState([])
  const navigate = useNavigate()
  const navRef = useRef(navigate)
  const toastTimer = useRef(null)
  navRef.current = navigate

  useEffect(() => {
    api.get('/api/activity').then(setLogs).catch(() => {})
    api.get('/api/runs').then(setRuns).catch(() => {})
    let ws, retry, closed = false
    const connect = () => {
      ws = new WebSocket(`${WS_BASE}/ws/activity`)
      ws.onopen = () => {
        setConnected(true)
        if (document.visibilityState === 'visible') ws.send('active')
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(connect, 2000)
      }
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'log') setLogs((l) => [...l.slice(-199), msg.entry])
        if (msg.type === 'refresh') setTick((t) => t + 1)
        if (msg.type === 'run') {
          setRuns((rs) => {
            const others = rs.filter((r) => r.id !== msg.run.id)
            return [msg.run, ...others].sort((a, b) => b.id - a.id).slice(0, 15)
          })
        }
        if (msg.type === 'run_step') {
          setRuns((rs) => rs.map((r) => (r.id === msg.run_id
            ? { ...r, steps: [...(r.steps || []).filter((s) => s.id !== msg.step.id), msg.step] }
            : r)))
        }
        if (msg.type === 'navigate') navRef.current(msg.to)
        if (msg.type === 'announce') {
          setToast(msg.text)
          clearTimeout(toastTimer.current)  // a newer announcement gets its full 12 s
          toastTimer.current = setTimeout(() => setToast(null), 12000)
          if (msg.speak) speakAloud(msg.text)  // the server picks ONE tab to talk (or Gemini voice)
          setTick((t) => t + 1)
        }
      }
    }
    connect()
    // The tab the student is looking at becomes the one that reads announcements aloud
    const markActive = () => {
      if (document.visibilityState === 'visible' && ws?.readyState === 1) ws.send('active')
    }
    window.addEventListener('focus', markActive)
    document.addEventListener('visibilitychange', markActive)
    return () => {
      closed = true; clearTimeout(retry); ws?.close()
      window.removeEventListener('focus', markActive)
      document.removeEventListener('visibilitychange', markActive)
    }
  }, [])

  return (
    <LiveContext.Provider value={{ logs, tick, connected, toast, setToast, runs }}>
      {children}
    </LiveContext.Provider>
  )
}
