import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { BookOpenCheck, CalendarDays, Plane, LayoutDashboard, ListChecks, RefreshCw, ShieldCheck, UserRound, Volume2, X } from 'lucide-react'
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
import CalendarPage from './pages/CalendarPage'
import Onboarding from './pages/Onboarding'
import Notes from './pages/Notes'
import Preflight from './pages/Preflight'
import ErrorBoundary from './components/ErrorBoundary'

function Logo({ className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2.5 font-extrabold tracking-tight ${className}`}>
      <span className="grid place-items-center w-9 h-9 rounded-xl bg-white text-brand">
        <BookOpenCheck size={22} strokeWidth={2.4} />
      </span>
      StudyPilot
    </span>
  )
}

function Login() {
  const missing = new URLSearchParams(window.location.search).get('missing_scopes')
  return (
    <div className="min-h-screen flex items-center justify-center bg-indigo-950 p-6">
      <div className="bg-white rounded-3xl p-10 max-w-lg w-full shadow-2xl">
        <span className="grid place-items-center w-14 h-14 rounded-2xl bg-brand text-white mb-6">
          <BookOpenCheck size={30} strokeWidth={2.2} />
        </span>
        <h1 className="text-3xl font-extrabold text-slate-900">StudyPilot</h1>
        <p className="mt-3 text-base text-slate-600 leading-relaxed">
          Your AI study agent. It reads your Google Classroom, understands every lecture and
          plans your study time in Google Calendar, so you're never unprepared.
        </p>
        {missing && (
          <div className="mt-6 p-4 rounded-xl bg-amber-50 border border-amber-300 text-amber-950">
            <b>Almost there.</b> Google didn't give StudyPilot access to Classroom, Drive and
            Calendar. Sign in again and <b>tick every checkbox</b> (or “Select all”) on the permissions screen.
          </div>
        )}
        <a href={loginUrl} className="btn-primary w-full text-base mt-8 py-3">Sign in with Google</a>
        <p className="mt-4 text-sm text-slate-500 flex gap-2 items-start">
          <ShieldCheck size={18} className="shrink-0 mt-0.5" />
          Read-only access to Classroom. Only StudyPilot's own Calendar events are ever changed.
        </p>
      </div>
    </div>
  )
}

function Toast() {
  const { toast, setToast } = useLive()
  if (!toast) return null
  return (
    <div role="status" className="fixed top-20 left-1/2 -translate-x-1/2 z-50 slide-in max-w-3xl w-[92%]">
      <div className="bg-indigo-950 text-white rounded-2xl shadow-2xl px-6 py-5 flex gap-4 items-start ring-1 ring-white/10">
        <span className="grid place-items-center w-11 h-11 rounded-full bg-indigo-500 shrink-0">
          <Volume2 size={22} />
        </span>
        <div className="flex-1">
          <p className="text-sm font-semibold text-indigo-200">StudyPilot noticed a change</p>
          <p className="text-xl font-medium leading-snug mt-0.5">{toast}</p>
        </div>
        <button onClick={() => setToast(null)} aria-label="Dismiss" className="text-indigo-200 hover:text-white p-1">
          <X size={22} />
        </button>
      </div>
    </div>
  )
}

function Shell({ me }) {
  const { connected } = useLive()
  const [syncing, setSyncing] = useState(false)
  const location = useLocation()
  const nav =({ isActive }) =>
    `inline-flex items-center gap-2 px-3 py-2 rounded-xl font-semibold whitespace-nowrap transition ${isActive ? 'bg-white text-brand' : 'text-indigo-100 hover:bg-white/10'}`
  const wide = location.pathname === '/calendar' || location.pathname === '/onboarding' || location.pathname.startsWith('/notes') || location.pathname === '/preflight'

  const syncNow = async () => {
    setSyncing(true)
    try { await api.post('/api/sync') } finally { setSyncing(false) }
  }

  return (
    <div className="min-h-screen">
      <header className="bg-brand text-white sticky top-0 z-40 shadow-md">
        <div className="max-w-[1680px] mx-auto px-6 h-[68px] flex items-center gap-4">
          <Link to="/"><Logo className="text-2xl" /></Link>
          <nav className="flex gap-1 ml-4">
            <NavLink to="/" end className={nav}><LayoutDashboard size={19} />Dashboard</NavLink>
            <NavLink to="/calendar" className={nav}><CalendarDays size={19} />Calendar</NavLink>
            <NavLink to="/plan" className={nav}><ListChecks size={19} />Study plan</NavLink>
            <NavLink to="/onboarding" className={nav}><UserRound size={19} />About me</NavLink>
            <NavLink to="/preflight" className={nav} title="Pre-flight check before the demo"><Plane size={19} />Check</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className={`hidden 2xl:flex text-sm font-semibold items-center gap-2 whitespace-nowrap ${connected ? 'text-emerald-200' : 'text-amber-200'}`}>
              <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              {connected ? 'Agent live' : 'Reconnecting…'}
            </span>
            <button onClick={syncNow} disabled={syncing} className="btn-on-dark">
              <RefreshCw size={18} className={syncing ? 'animate-spin' : ''} />
              <span className="hidden xl:inline">{syncing ? 'Syncing…' : 'Sync now'}</span>
            </button>
            <VoiceButton />
          </div>
        </div>
      </header>
      <Toast />
      {me?.needs_upgrade && (
        <div className="bg-amber-100 border-b border-amber-300 text-amber-950">
          <div className="max-w-[1680px] mx-auto px-6 py-2.5 flex items-center gap-3 flex-wrap">
            <ShieldCheck size={20} />
            <span className="font-semibold">StudyPilot can now read class emails and organize your Drive notes. Sign in once more to allow it.</span>
            <a href={loginUrl} className="btn-primary !py-1.5 ml-auto">Sign in again</a>
          </div>
        </div>
      )}
      {!me?.needs_upgrade && !me?.profile_done && location.pathname !== '/onboarding' && (
        <div className="bg-indigo-50 border-b border-indigo-200 text-indigo-950">
          <div className="max-w-[1680px] mx-auto px-6 py-2.5 flex items-center gap-3 flex-wrap">
            <UserRound size={20} />
            <span className="font-semibold">I plan better when I know you. Take the 3-minute interview: goals, timetable, and what gets in the way.</span>
            <Link to="/onboarding" className="btn-primary !py-1.5 ml-auto">Start interview</Link>
          </div>
        </div>
      )}
      <div className={`max-w-[1680px] mx-auto px-6 py-7 grid grid-cols-1 gap-7 ${wide ? '' : 'xl:grid-cols-[minmax(0,1fr)_440px]'}`}>
        <main className="min-w-0">
          <ErrorBoundary key={location.pathname} label="This page">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/course/:id" element={<Course />} />
            <Route path="/lecture/:fileId" element={<Lecture />} />
            <Route path="/prep/:id" element={<PrepPack />} />
            <Route path="/plan" element={<Plan />} />
            <Route path="/panic/:id" element={<Panic />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/notes/:id" element={<Notes />} />
            <Route path="/preflight" element={<Preflight />} />
          </Routes>
          </ErrorBoundary>
        </main>
        <aside className={wide ? 'grid lg:grid-cols-2 gap-6' : 'space-y-6 xl:sticky xl:top-[92px] xl:self-start'}>
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
    api.get('/api/me').then(setMe).catch(() => setError(import.meta.env.DEV
      ? "Can't reach the StudyPilot backend on localhost:8000. Start it with .\\start.ps1"
      : "Can't reach the StudyPilot server. It may be waking up, so refresh in 30 seconds."))
  }, [])

  if (error) return <div className="p-10 text-xl text-red-800">{error}</div>
  if (!me) return <div className="p-10 text-xl text-slate-600">Loading StudyPilot…</div>
  if (!me.logged_in) return <Login />
  return (
    <LiveProvider>
      <Shell me={me} />
    </LiveProvider>
  )
}
