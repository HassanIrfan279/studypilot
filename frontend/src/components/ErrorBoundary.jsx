import { Component } from 'react'
import { AlertTriangle, RotateCw } from 'lucide-react'

// If one page or panel throws while rendering, show a small recoverable card
// instead of blanking the whole app.
export default class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error, info) { console.error('StudyPilot UI error:', error, info?.componentStack) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="card !bg-amber-50 !border-amber-300 flex items-center gap-3 flex-wrap">
        <AlertTriangle size={22} className="text-amber-700 shrink-0" />
        <p className="flex-1 text-amber-950">{this.props.label || 'This section'} hit a glitch. Your data is safe.</p>
        <button className="btn-ghost" onClick={() => this.setState({ error: null })}><RotateCw size={17} /> Try again</button>
      </div>
    )
  }
}
