import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Activity, Bot, BookOpenCheck, Briefcase, CalendarDays, Menu, Plane, LayoutDashboard, ListChecks, RefreshCw, ShieldCheck, UserRound, Volume2, X } from 'lucide-react'
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
import Internships from './pages/Internships'
import Review from './pages/Review'
import Agents from './pages/Agents'
import AgentAvatar from './components/AgentAvatar'
import { AGENTS } from './agents'
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

const NAV = [
  { group: 'Study', links: [
    { to: '/', end: true, icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/calendar', icon: CalendarDays, label: 'Calendar' },
    { to: '/plan', icon: ListChecks, label: 'Study plan' },
  ] },
  { group: 'Career', links: [
    { to: '/internships', icon: Briefcase, label: 'Internships' },
  ] },
  { group: 'Your agents', links: [
    { to: '/agents', icon: Bot, label: 'Meet the agents' },
    { to: '/preflight', icon: Plane, label: 'System check' },
  ] },
  { group: 'You', links: [
    { to: '/onboarding', icon: UserRound, label: 'About me' },
  ] },
]

function pageTitle(path) {
  const map = { '/': 'Dashboard', '/calendar': 'Calendar', '/plan': 'Study plan', '/internships': 'Internships',
    '/agents': 'Meet the agents', '/preflight': 'System check', '/onboarding': 'About me' }
  if (map[path]) return map[path]
  const first = path.split('/')[1]
  return { course: 'Course', lecture: 'Lecture', prep: 'Prep pack', panic: 'Panic mode', notes: 'Study notes', review: 'Spaced review' }[first] || 'StudyPilot'
}

function Sidebar({ open, onClose }) {
  const { connected } = useLive()
  return (
    <>
      {open && <div className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden" onClick={onClose} aria-hidden="true" />}
      <aside className={`sp-sidebar fixed inset-y-0 left-0 z-50 w-[248px] flex flex-col text-white transition-transform duration-200 lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="relative z-10 px-5 pt-5 pb-4 flex items-center justify-between">
          <Link to="/" onClick={onClose}><Logo className="text-xl" /></Link>
          <button className="lg:hidden text-indigo-200 p-1" onClick={onClose} aria-label="Close menu"><X size={22} /></button>
        </div>
        <nav className="relative z-10 flex-1 overflow-y-auto px-3 space-y-5" aria-label="Main">
          {NAV.map((g) => (
            <div key={g.group}>
              <p className="px-3 mb-1.5 text-[11px] font-bold uppercase tracking-[.14em] text-indigo-300/60">{g.group}</p>
              <div className="space-y-0.5">
                {g.links.map(({ to, end, icon: Icon, label }) => (
                  <NavLink key={to} to={to} end={end} onClick={onClose} className={({ isActive }) => `sp-nav ${isActive ? 'active' : ''}`}>
                    <Icon size={19} />{label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <Link to="/agents" onClick={onClose} className="relative z-10 mx-3 mb-3 rounded-2xl bg-white/5 hover:bg-white/10 transition p-3 block">
          <div className="flex -space-x-3">
            {AGENTS.slice(0, 5).map((a) => <span key={a.id} className="rounded-full bg-[#111735] ring-2 ring-[#111735]"><AgentAvatar agent={a} size={38} /></span>)}
          </div>
          <p className="mt-2 text-sm font-semibold flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
            {connected ? '8 agents online' : 'Reconnecting…'}
          </p>
        </Link>
      </aside>
    </>
  )
}

function AgentDrawer({ open, onClose }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-label="Agent activity and chat">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="absolute right-0 inset-y-0 w-full max-w-[460px] bg-[#f4f6fb] shadow-2xl p-4 overflow-y-auto space-y-4 slide-in">
        <div className="flex items-center">
          <h2 className="text-lg font-extrabold flex-1">Your agents</h2>
          <button className="btn-ghost !p-2" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </div>
        <ActivityLog />
        <ChatBox />
      </div>
    </div>
  )
}

function Shell({ me }) {
  const [syncing, setSyncing] = useState(false)
  const [menu, setMenu] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()
  const home = location.pathname === '/'
  useEffect(() => { setDrawer(false) }, [location.pathname])

  const syncNow = async () => {
    setSyncing(true)
    try { await api.post('/api/sync') } finally { setSyncing(false) }
  }

  return (
    <div className="min-h-screen">
      <Sidebar open={menu} onClose={() => setMenu(false)} />
      <div className="lg:pl-[248px]">
        <header className="sp-topbar sticky top-0 z-30 border-b border-slate-200/70">
          <div className="max-w-[1500px] mx-auto px-4 md:px-7 h-16 flex items-center gap-3">
            <button className="lg:hidden btn-ghost !p-2" onClick={() => setMenu(true)} aria-label="Open menu"><Menu size={20} /></button>
            <p className="text-[15px] font-semibold text-slate-500 truncate">
              <span className="hidden sm:inline">StudyPilot <span className="mx-1.5 text-slate-300">/</span></span>
              <span className="text-slate-900">{pageTitle(location.pathname)}</span>
            </p>
            <div className="ml-auto flex items-center gap-2">
              {!home && (
                <button className="btn-ghost" onClick={() => setDrawer(true)} title="Agent activity and chat">
                  <Activity size={18} /><span className="hidden md:inline">Agents</span>
                </button>
              )}
              <button onClick={syncNow} disabled={syncing} className="btn-ghost" title="Check Classroom now">
                <RefreshCw size={18} className={syncing ? 'animate-spin' : ''} />
                <span className="hidden md:inline">{syncing ? 'Syncing…' : 'Sync'}</span>
              </button>
              <VoiceButton />
            </div>
          </div>
        </header>
        <Toast />
        <div className="max-w-[1500px] mx-auto px-4 md:px-7 py-6 space-y-5">
          {me?.needs_upgrade && (
            <div className="card !py-3 !border-amber-300 !bg-amber-50 flex items-center gap-3 flex-wrap">
              <ShieldCheck size={20} className="text-amber-700" />
              <span className="font-semibold flex-1 min-w-[16rem]">StudyPilot can now read class emails, organize your Drive notes and prepare internship applications as Gmail drafts (it never sends). Sign in once more to allow it.</span>
              <a href={loginUrl} className="btn-primary !py-1.5">Sign in again</a>
            </div>
          )}
          {!me?.needs_upgrade && !me?.profile_done && location.pathname !== '/onboarding' && (
            <div className="card !py-3 !border-indigo-200 !bg-indigo-50 flex items-center gap-3 flex-wrap">
              <UserRound size={20} className="text-brand" />
              <span className="font-semibold flex-1 min-w-[16rem]">I plan better when I know you. Take the 3-minute interview: goals, timetable, and what gets in the way.</span>
              <Link to="/onboarding" className="btn-primary !py-1.5">Start interview</Link>
            </div>
          )}
          <div className={`grid grid-cols-1 gap-6 ${home ? 'xl:grid-cols-[minmax(0,1fr)_400px]' : ''}`}>
            <main className={`min-w-0 ${/^\/(prep|lecture|course|panic|review)\//.test(location.pathname) ? 'max-w-[1100px] w-full mx-auto' : ''}`}>
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
                <Route path="/internships" element={<Internships />} />
                <Route path="/review/:id" element={<Review />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="*" element={
                  <div className="card text-center py-14">
                    <p className="text-2xl font-extrabold">Page not found</p>
                    <p className="text-slate-500 mt-1">That address isn't part of StudyPilot.</p>
                    <Link to="/" className="btn-primary mt-5 inline-flex">Back to the dashboard</Link>
                  </div>} />
              </Routes>
              </ErrorBoundary>
            </main>
            {home && (
              <aside className="space-y-5 xl:sticky xl:top-[88px] xl:self-start">
                <ActivityLog />
                <ChatBox />
              </aside>
            )}
          </div>
        </div>
      </div>
      <AgentDrawer open={drawer} onClose={() => setDrawer(false)} />
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
  if (!me.logged_in) return <><NotOwnerBanner /><Login /></>
  return (
    <LiveProvider>
      <NotOwnerBanner />
      <Shell me={me} />
    </LiveProvider>
  )
}

// Shown when someone other than the owner tried to sign in (owner lock on the server)
function NotOwnerBanner() {
  const [show, setShow] = useState(() => new URLSearchParams(window.location.search).get('login_error') === 'not_owner')
  if (!show) return null
  return (
    <div role="alert" className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] w-[94%] max-w-2xl slide-in">
      <div className="rounded-2xl bg-slate-900 text-white shadow-2xl p-5 flex gap-4 items-start ring-1 ring-white/10">
        <ShieldCheck size={26} className="text-indigo-300 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-extrabold text-lg">This is a personal StudyPilot</p>
          <p className="text-slate-300 mt-1">
            Each student runs their own private agent, which holds their own Google sign-in and works only for them.
            Your account was not connected, and nothing was changed. You're seeing the owner's demo.
          </p>
        </div>
        <button onClick={() => { setShow(false); window.history.replaceState(null, '', window.location.pathname) }}
          className="text-slate-400 hover:text-white p-1" aria-label="Dismiss"><X size={20} /></button>
      </div>
    </div>
  )
}
