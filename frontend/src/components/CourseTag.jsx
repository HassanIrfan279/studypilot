const SMALL = new Set(['and', 'of', 'the', 'in', 'on', 'for', 'to', 'a', 'an'])

// "design and analysis of algorithm" -> "Design and Analysis of Algorithm"
export function titleCase(s = '') {
  return s.split(' ').map((w, i) => {
    if (i > 0 && SMALL.has(w.toLowerCase())) return w.toLowerCase()
    if (/[A-Z].*[A-Z]|\d/.test(w)) return w // keep acronyms like BSCS, P3
    return w.charAt(0).toUpperCase() + w.slice(1)
  }).join(' ')
}

// Course identity: a colour dot (matches the Google Calendar colour) + readable dark text.
// The course colour is never used as text colour, so yellow/orange courses stay legible.
export default function CourseTag({ name, color, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold text-slate-800 ${className}`}>
      <span className="w-3 h-3 rounded-full shrink-0 ring-2 ring-white shadow-sm" style={{ background: color }} />
      {titleCase(name)}
    </span>
  )
}
