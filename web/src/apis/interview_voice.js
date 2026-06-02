import { apiPost } from './base'

export const interviewVoiceApi = {
  startVoiceSession: (payload) => apiPost('/api/interview/voice/session/start', payload),
  buildVoiceWsUrl: ({ voiceSessionId, token }) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // Route through the Vite dev server (same host/port as the page) so the
    // proxy forwards the WebSocket upgrade inside Docker's network, where the
    // TCP-level upgrade handshake works correctly.  Docker Desktop on Windows
    // does not reliably forward WebSocket upgrades through its port-mapping.
    const host = window.location.host
    const params = new URLSearchParams({
      voice_session_id: voiceSessionId,
      token
    })
    return `${protocol}//${host}/api/interview/voice/ws?${params.toString()}`
  }
}
