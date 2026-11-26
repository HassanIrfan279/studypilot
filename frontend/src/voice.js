// Voice client: mic (16 kHz PCM16) -> backend /ws/voice -> Gemini Live -> speaker (24 kHz PCM16)
import { WS_BASE } from './api'

const MIC_WORKLET = `
class MicProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.buf = []; }
  process(inputs) {
    const ch = inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) this.buf.push(ch[i]);
      if (this.buf.length >= 2048) {
        const pcm = new Int16Array(this.buf.length);
        for (let i = 0; i < this.buf.length; i++) {
          const s = Math.max(-1, Math.min(1, this.buf[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.buf = [];
      }
    }
    return true;
  }
}
registerProcessor('mic-processor', MicProcessor);
`

const listeners = new Set()
let state = { status: 'off', transcript: [] } // off | connecting | listening | speaking | error
let ws, micCtx, micStream, playCtx, playHead = 0, sources = []

function set(patch) {
  state = { ...state, ...patch }
  listeners.forEach((fn) => fn(state))
}

export function subscribe(fn) {
  listeners.add(fn)
  fn(state)
  return () => listeners.delete(fn)
}

export const isOn = () => state.status !== 'off' && state.status !== 'error'

function playPcm(arrayBuffer) {
  if (!playCtx) return
  const pcm = new Int16Array(arrayBuffer)
  const f32 = new Float32Array(pcm.length)
  for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / 0x8000
  const buf = playCtx.createBuffer(1, f32.length, 24000)
  buf.copyToChannel(f32, 0)
  const src = playCtx.createBufferSource()
  src.buffer = buf
  src.connect(playCtx.destination)
  playHead = Math.max(playHead, playCtx.currentTime)
  src.start(playHead)
  playHead += buf.duration
  sources.push(src)
  src.onended = () => {
    sources = sources.filter((s) => s !== src)
    if (!sources.length && state.status === 'speaking') set({ status: 'listening' })
  }
  set({ status: 'speaking' })
}

function stopPlayback() {
  sources.forEach((s) => { try { s.stop() } catch { /* already stopped */ } })
  sources = []
  playHead = 0
}

function addTranscript(role, text) {
  const t = [...state.transcript]
  const last = t[t.length - 1]
  if (last && last.role === role && !last.done) last.text += text
  else t.push({ role, text, done: false })
  set({ transcript: t.slice(-30) })
}

export async function start() {
  if (isOn()) return
  set({ status: 'connecting', error: null })
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    micCtx = new AudioContext({ sampleRate: 16000 })
    playCtx = new AudioContext({ sampleRate: 24000 })
    const url = URL.createObjectURL(new Blob([MIC_WORKLET], { type: 'application/javascript' }))
    await micCtx.audioWorklet.addModule(url)
    const node = new AudioWorkletNode(micCtx, 'mic-processor')
    micCtx.createMediaStreamSource(micStream).connect(node)

    ws = new WebSocket(`${WS_BASE}/ws/voice`)
    ws.binaryType = 'arraybuffer'
    node.port.onmessage = (e) => { if (ws?.readyState === 1) ws.send(e.data) }
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return playPcm(e.data)
      const msg = JSON.parse(e.data)
      if (msg.type === 'ready') set({ status: 'listening' })
      else if (msg.type === 'transcript') addTranscript(msg.role, msg.text)
      else if (msg.type === 'interrupted') stopPlayback()
      else if (msg.type === 'turn_complete') {
        set({ transcript: state.transcript.map((t) => ({ ...t, done: true })) })
      } else if (msg.type === 'error') set({ status: 'error', error: msg.text })
    }
    ws.onclose = () => { if (state.status !== 'error') stop() }
  } catch (err) {
    set({ status: 'error', error: err.message })
    stop(true)
  }
}

export function stop(keepError = false) {
  try { ws?.close() } catch { /* ignore */ }
  micStream?.getTracks().forEach((t) => t.stop())
  micCtx?.close().catch(() => {})
  stopPlayback()
  playCtx?.close().catch(() => {})
  ws = micCtx = micStream = playCtx = null
  if (!keepError) set({ status: 'off' })
}

export function sendText(text, type = 'text') {
  if (ws?.readyState === 1) {
    ws.send(JSON.stringify({ type, text }))
    return true
  }
  return false
}

// "Agent speaks first": use Gemini Live voice if connected, else the browser's built-in voice.
export function announce(text) {
  if (sendText(text, 'announce')) return
  if ('speechSynthesis' in window) {
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1.02
    window.speechSynthesis.speak(u)
  }
}
