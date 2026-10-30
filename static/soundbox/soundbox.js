// AI Soundbox simulator. Renders /api/soundbox/state; refetches on soundbox:S1 pings.
document.addEventListener('alpine:init', () => {
  Alpine.data('soundbox', () => ({
    F: window.F,
    store: '', vpa: '', top: null, front: { mode: 'idle' }, aiEnabled: false, voiceLang: 'kn-IN',
    presets: [], text: '', transcript: '', why: false, busy: false, toast: null,
    recording: false, speaking: false, _rec: null, _chunks: [],

    async init() {
      this.presets = await API.get('/api/soundbox/presets');
      await this.load();
      API.on((s) => s.startsWith('soundbox:'), (msg) => {
        if (msg.type === 'speak') this.speak(msg.text, msg.lang);
        else this.load();
      });
    },
    async load() {
      const st = await API.get('/api/soundbox/state');
      Object.assign(this, { store: st.store, vpa: st.vpa, top: st.top, front: st.front, aiEnabled: st.ai_enabled, voiceLang: st.voice_lang });
      if (!st.top) this.why = false;
    },
    flash(text, error = false) { this.toast = { text, error }; setTimeout(() => { this.toast = null; }, 3500); },
    async run(fn) {
      this.busy = true;
      try { await fn(); await this.load(); } catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    say(p) { this.why = false; return this.run(() => API.post('/api/soundbox/udhaar', { customer_id: p.customer_id, amount: p.amount })); },
    sayText() {
      const t = this.text.trim(); if (!t) return;
      this.why = false; this.text = '';
      return this.run(() => API.post('/api/soundbox/udhaar', { text: t }));
    },
    accept(override) { return this.run(() => API.post('/api/soundbox/accept', { override })); },
    clear() { this.transcript = ''; return this.run(() => API.post('/api/soundbox/clear')); },

    // Voice (AI on only): record ≤ 15 s, transcribe with Sarvam, then send as text.
    async toggleMic() {
      if (this.recording) { this._rec?.stop(); return; }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this._chunks = [];
        this._rec = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        this._rec.ondataavailable = (e) => this._chunks.push(e.data);
        this._rec.onstop = async () => {
          this.recording = false; stream.getTracks().forEach(t => t.stop());
          const fd = new FormData(); fd.append('file', new Blob(this._chunks, { type: 'audio/webm' }), 'speech.webm');
          const r = await fetch('/api/voice/transcribe', { method: 'POST', body: fd });
          const out = await r.json().catch(() => ({}));
          if (!r.ok) { this.flash(out.detail || 'Didn’t catch that', true); return; }
          this.transcript = out.transcript;
          await this.run(() => API.post('/api/soundbox/udhaar', { text: out.transcript }));
        };
        this._rec.start(); this.recording = true;
        setTimeout(() => { if (this.recording) this._rec.stop(); }, 15000);
      } catch (e) { this.flash('Microphone needs HTTPS or localhost and permission', true); }
    },
    async speak(text, lang) {
      try {
        const audio = new Audio(`/api/voice/speak?text=${encodeURIComponent(text)}&lang=${encodeURIComponent(lang)}`);
        this.speaking = true; audio.onended = audio.onerror = () => { this.speaking = false; };
        await audio.play();
      } catch (e) { this.speaking = false; }
    },
  }));
});
