import { useState } from 'react'
import { api } from '../api'

// Shows English text with a one-click switch to simple Urdu (Gemini-translated, cached).
export default function UrduText({ text, className = '' }) {
  const [urdu, setUrdu] = useState(null)
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    if (!show && !urdu) {
      setLoading(true)
      try { setUrdu((await api.post('/api/urdu', { text })).urdu) } finally { setLoading(false) }
    }
    setShow(!show)
  }

  return (
    <div className={className}>
      {show && urdu ? <p className="urdu text-base">{urdu}</p> : <p>{text}</p>}
      <button onClick={toggle} className="text-sm font-semibold text-indigo-700 hover:underline mt-1">
        {loading ? 'ترجمہ ہو رہا ہے…' : show ? 'Show English' : 'اردو میں سمجھائیں (Urdu)'}
      </button>
    </div>
  )
}
