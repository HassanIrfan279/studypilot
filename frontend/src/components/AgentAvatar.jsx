// Illustrated robot avatar for each agent: floats, blinks, and its gear animates (radar spins,
// clock ticks, sound waves pulse...). Pure SVG + CSS; motion stops under prefers-reduced-motion.
function Gear({ kind, c, a }) {
  switch (kind) {
    case 'brain':
      return (
        <g>
          <circle cx="60" cy="14" r="6" fill={a} className="sp-pulse" />
          <path d="M60 20v8" stroke={a} strokeWidth="3" strokeLinecap="round" />
          <path d="M44 86c4-6 10-6 16 0s12 6 16 0" stroke={a} strokeWidth="3" fill="none" strokeLinecap="round" />
          <circle cx="60" cy="92" r="3" fill="#fff" className="sp-pulse" />
        </g>
      )
    case 'radar':
      return (
        <g>
          <path d="M60 28v-8" stroke={a} strokeWidth="3" strokeLinecap="round" />
          <g className="sp-spin" style={{ transformOrigin: '60px 16px' }}>
            <path d="M48 16a12 12 0 0 1 24 0z" fill={a} />
            <circle cx="60" cy="16" r="2.5" fill={c} />
          </g>
          <circle cx="60" cy="92" r="9" fill="none" stroke={a} strokeWidth="2" className="sp-ping" />
          <circle cx="60" cy="92" r="3" fill="#fff" />
        </g>
      )
    case 'clock':
      return (
        <g>
          <circle cx="60" cy="16" r="5" fill={a} />
          <path d="M60 21v7" stroke={a} strokeWidth="3" strokeLinecap="round" />
          <circle cx="60" cy="92" r="10" fill="#fff" />
          <path d="M60 92v-6" stroke={c} strokeWidth="2.5" strokeLinecap="round" />
          <path d="M60 92l5 0" stroke={c} strokeWidth="2.5" strokeLinecap="round" className="sp-tick" style={{ transformOrigin: '60px 92px' }} />
        </g>
      )
    case 'cap':
      return (
        <g>
          <path d="M34 30l26-12 26 12-26 12z" fill="#1e1b4b" />
          <path d="M46 35v8c8 5 20 5 28 0v-8" fill="#312e81" />
          <path d="M84 31v12" stroke={a} strokeWidth="2.5" />
          <circle cx="84" cy="45" r="3" fill={a} className="sp-pulse" />
          <rect x="50" y="86" width="20" height="13" rx="2" fill="#fff" />
          <path d="M60 86v13" stroke={c} strokeWidth="1.5" />
        </g>
      )
    case 'shield':
      return (
        <g>
          <circle cx="60" cy="15" r="5" fill={a} className="sp-pulse" />
          <path d="M60 20v8" stroke={a} strokeWidth="3" strokeLinecap="round" />
          <path d="M60 80l12 4v8c0 7-5 11-12 14-7-3-12-7-12-14v-8z" fill="#fff" />
          <path d="M55 92l4 4 7-8" stroke={c} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      )
    case 'moon':
      return (
        <g>
          <path d="M68 8a10 10 0 1 0 8 15 8 8 0 1 1-8-15z" fill="#fde68a" className="sp-pulse" />
          <circle cx="46" cy="14" r="1.6" fill="#fff" className="sp-twinkle" />
          <circle cx="82" cy="30" r="1.4" fill="#fff" className="sp-twinkle" style={{ animationDelay: '.8s' }} />
          <circle cx="60" cy="92" r="8" fill="none" stroke={a} strokeWidth="2.5" />
          <path d="M60 87v5l3 3" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
        </g>
      )
    case 'briefcase':
      return (
        <g>
          <path d="M60 28v-8" stroke={a} strokeWidth="3" strokeLinecap="round" />
          <path d="M53 16l7-6 7 6-7 6z" fill={a} className="sp-pulse" />
          <rect x="47" y="85" width="26" height="17" rx="3" fill="#fff" />
          <path d="M55 85v-3h10v3" stroke="#fff" strokeWidth="2.5" fill="none" />
          <path d="M47 92h26" stroke={c} strokeWidth="1.5" />
        </g>
      )
    case 'headset':
      return (
        <g>
          <path d="M32 50a28 28 0 0 1 56 0" stroke="#1f2937" strokeWidth="5" fill="none" />
          <rect x="26" y="46" width="10" height="18" rx="4" fill="#1f2937" />
          <rect x="84" y="46" width="10" height="18" rx="4" fill="#1f2937" />
          <path d="M31 64c0 8 6 12 16 12" stroke="#1f2937" strokeWidth="3" fill="none" />
          <path d="M98 48c3 4 3 10 0 14" stroke={a} strokeWidth="2.5" fill="none" strokeLinecap="round" className="sp-wave" />
          <path d="M103 44c5 6 5 16 0 22" stroke={a} strokeWidth="2.5" fill="none" strokeLinecap="round" className="sp-wave" style={{ animationDelay: '.3s' }} />
          <path d="M52 93h4M58 89v8M64 91v4M68 93h2" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
        </g>
      )
    default:
      return null
  }
}

export default function AgentAvatar({ agent, size = 96, active = false }) {
  const { color: c, accent: a, gear, id } = agent
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} role="img" aria-label={`${agent.name}, ${agent.role}`}
      className={`shrink-0 ${active ? 'sp-active' : ''}`}>
      <defs>
        <radialGradient id={`glow-${id}`} cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor={a} stopOpacity=".55" />
          <stop offset="100%" stopColor={c} stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`body-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} />
          <stop offset="100%" stopColor={a} />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="58" fill={`url(#glow-${id})`} />
      <circle cx="60" cy="60" r="54" fill="none" stroke={c} strokeOpacity=".35" strokeWidth="1.5" strokeDasharray="4 7" className="sp-orbit" />
      <g className="sp-float">
        {/* body */}
        <path d="M36 112c0-20 10-30 24-30s24 10 24 30z" fill={`url(#body-${id})`} />
        {/* neck */}
        <rect x="54" y="72" width="12" height="10" rx="3" fill="#cbd5e1" />
        {/* head */}
        <rect x="34" y="28" width="52" height="46" rx="16" fill="#f8fafc" stroke={c} strokeWidth="2.5" />
        {/* visor */}
        <rect x="40" y="38" width="40" height="22" rx="10" fill="#0f172a" />
        <g className="sp-blink">
          <circle cx="51" cy="49" r="4.2" fill={a} />
          <circle cx="69" cy="49" r="4.2" fill={a} />
        </g>
        <path d="M54 66q6 4 12 0" stroke={c} strokeWidth="2.5" fill="none" strokeLinecap="round" />
        {/* ears */}
        <rect x="29" y="44" width="6" height="14" rx="3" fill={c} />
        <rect x="85" y="44" width="6" height="14" rx="3" fill={c} />
        <Gear kind={gear} c={c} a={a} />
      </g>
    </svg>
  )
}
