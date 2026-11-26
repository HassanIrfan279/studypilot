import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { api, loginUrl } from './api'
import { LiveProvider, useLive } from './live'
import ActivityLog from './components/ActivityLog'
import ChatBox from './components/ChatBox'
import VoiceButton from './components/VoiceButton'
import Dashboard from './pages/Dashboard'
import Course from './pages/Course'
import Lecture from './pages/Lecture'
import PrepPack from './pages/PrepPack'
import Plan from './pages/Plan'
import Panic from './pages/Panic'

function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-900 to-slate-900 p-6">
      <div className="bg-white rounded-3xl p-10 max-w-lg w-full text-center shadow-2xl">
        <div className="text-6xl mb-3">📘</div>
        <h1 className="text-4xl font-extrabold text-slate-900">StudyPilot</h1>
        <p className="mt-3 text-lg text-slate-600">
          Your AI study agent. It reads your Google Classroom, understands every lecture and
          plans your study time in Google Calendar — so you're never unprepared.
        </p>
        {new URLSearchParams(window.location.search).get('missing_scopes') && (
          <div className="mt-6 p-4 rounded-xl bg-amber-50 border-2 border-amber-400 text-left text-amber-900">
            <b>⚠ Almost there!</b> Google didn't give StudyPilot access to Classroom, Drive and Calendar.
            Sign in again and <b>tick every checkbox</b> (or click “Select all”) on the permissions screen.
          </div>
        )}
        <a href={loginUrl} className="btn-primary text-lg mt-8 px-6 py-3">
          Sign in with Google
        </a>
        <p className="mt-4 text-sm text-slate-500">Read-only access to Classroom. Only StudyPilot's own Calendar events are ever changed.</p>
      </div>
    </div>
  )
}

function Toast() {
  const { toast, setToast } = useLive()
  if (!toast) return null
  return (
    <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 slide-in max-w-2xl w-[90%]">
      <div className="bg-indigo-700 text-white rounded-2xl shadow-2xl px-6 py-4 flex gap-4 items-start">
        <span className="text-3xl">🔊</span>
        <p className="text-lg font-medium flex-1">{toast}</p>
        <button onClick={() => setToast(null)} className="text-white/70 hover:text-white text-xl">✕</button>
      </div>
    </div>
  )
}

function Shell() {
  const { connected } = useLive()
  const [syncing, setSyncing] = useState(false)
  const nav = ({ isActive }) =>
    `px-3 py-2 rounded-lg font-semibold ${isActive ? 'bg-white text-brand' : 'text-white/90 hover:bg-white/10'}`

  const syncNow = async () => {
    setSyncing(true)
    try { await api.post('/api/sync') } finally { setSyncing(false) }
  }

  return (
    <div className="min-h-screen">
      <header className="bg-brand text-white sticky top-0 z-40 shadow">
        <div className="max-w-[1600px] mx-auto px-5 h-16 flex items-center gap-4">
          <Link to="/" className="text-2xl font-extrabold tracking-tight">📘 StudyPilot</Link>
          <nav className="flex gap-1 ml-4">
            <NavLink to="/" end className={nav}>Dashboard</NavLink>
            <NavLink to="/plan" className={nav}>Study Plan</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className={`text-sm flex items-center gap-2 ${connected ? 'text-emerald-200' : 'text-red-200'}`}>
              <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
              {connected ? 'Agent live' : 'Reconnecting…'}
            </span>
            <button onClick={syncNow} disabled={syncing} className="btn-ghost !bg-white/15 !text-white hover:!bg-white/25">
              {syncing ? '⏳ Syncing…' : '🔄 Sync now'}
            </button>
            <VoiceButton />
          </div>
        </div>
      </header>
      <Toast />
      <div className="max-w-[1600px] mx-auto px-5 py-6 grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6">
        <main className="min-w-0">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/course/:id" element={<Course />} />
            <Route path="/lecture/:fileId" element={<Lecture />} />
            <Route path="/prep/:id" element={<PrepPack />} />
            <Route path="/plan" element={<Plan />} />
            <Route path="/panic/:id" element={<Panic />} />
          </Routes>
        </main>
        <aside className="space-y-6 xl:sticky xl:top-22 xl:self-start">
          <ActivityLog />
          <ChatBox />
        </aside>
      </div>
    </div>
  )
}

export default function App() {
  const [me, setMe] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/me').then(setMe).catch(() => setError('Backend is not running on localhost:8000'))
  }, [])

  if (error) return <div className="p-10 text-xl text-red-700">⚠ {error}</div>
  if (!me) return <div className="p-10 text-xl">Loading…</div>
  if (!me.logged_in) return <Login />
  return (
    <LiveProvider>
      <Shell />
    </LiveProvider>
  )
}
