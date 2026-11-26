// Live connection to the backend activity feed (WebSocket). Shares log + a refresh counter.
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, WS_BASE } from './api'
import { announce } from './voice'

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
  navRef.current = navigate

  useEffect(() => {
    api.get('/api/activity').then(setLogs).catch(() => {})
    api.get('/api/runs').then(setRuns).catch(() => {})
    let ws, retry, closed = false
    const connect = () => {
      ws = new WebSocket(`${WS_BASE}/ws/activity`)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = setTimeout(connect, 2000)
      }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
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
          setTimeout(() => setToast(null), 12000)
          announce(msg.text)
          setTick((t) => t + 1)
        }
      }
    }
    connect()
    return () => { closed = true; clearTimeout(retry); ws?.close() }
  }, [])

  return (
    <LiveContext.Provider value={{ logs, tick, connected, toast, setToast, runs }}>
      {children}
    </LiveContext.Provider>
  )
}
