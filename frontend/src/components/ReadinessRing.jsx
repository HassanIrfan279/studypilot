export default function ReadinessRing({ score = 0, size = 72 }) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const color = score >= 70 ? '#059669' : score >= 40 ? '#d97706' : '#dc2626'
  return (
    <div className="flex flex-col items-center" title="Readiness = 50% study sessions done + 50% best practice quiz">
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e2e8f0" strokeWidth="8" fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth="8" fill="none"
          strokeDasharray={c} strokeDashoffset={c * (1 - score / 100)} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dashoffset .8s' }} />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fontWeight="800"
          fontSize={size / 4} fill="#0f172a">{score}%</text>
      </svg>
      <span className="text-xs text-slate-500 font-semibold mt-1">ready</span>
    </div>
  )
}
