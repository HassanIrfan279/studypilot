// Tiny wrapper around the backend API
export const API_BASE = 'http://localhost:8000'
export const WS_BASE = 'ws://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body || {}) }),
}

export const loginUrl = `${API_BASE}/auth/login`

export function daysLeftLabel(days) {
  if (days === null || days === undefined) return 'No date'
  if (days < 0) return 'Overdue'
  const hours = days * 24
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min left`
  if (hours < 24) return `${Math.round(hours)}h left`
  const d = Math.round(days)
  return d === 1 ? '1 day left' : `${d} days left`
}

export function urgencyClass(days) {
  if (days === null || days === undefined) return 'bg-slate-200 text-slate-800'
  if (days < 1) return 'bg-red-600 text-white'
  if (days < 3) return 'bg-amber-500 text-black'
  return 'bg-emerald-600 text-white'
}

export function fmtDate(iso, withTime = true) {
  if (!iso) return 'No due date'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short',
    ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: true } : {}),
  })
}
