// Root Alpine component. All server state comes from the latest snapshot (SSE /api/stream);
// the UI never computes balances. Local state here is only navigation (which screen or sheet
// is open) and form input. Every action is an event POSTed to /api/events.
document.addEventListener('alpine:init', () => {
  Alpine.data('bharosa', () => ({
    U: window.U,
    snap: null, trace: [], view: 'live', connected: false, toast: null, soundOn: false, started: false, playing: false,
    notif: { merchant: null, customer: null },
    sb: { panel: true, why: false, text: '', keypad: '', newName: '' },
    m: { screen: 'home', book: [], q: '', detail: null, thread: null, threadMsgs: [], adv: null, elig: null,
         question: '', asking: false, chat: [] },
    c: { screen: 'home', sheet: null, confirm: null, consent: true, disputing: false, reason: '', claimed: null,
         autopay: { store_id: 'S1', cap: 3000, start: 1, end: 5 }, reply: '', customers: [], busy: false },
    demo: { busy: false, script: [] },
    ctl: { vpa: '9876500000@ptyes', name: 'Kamala Kumar', amount: 500, remark: 'Ramesh ka udhaar',
           salary: 'C_RAMESH', billName: 'Gupta Agencies', billAmount: 12000, billDue: '2026-11-03' },
    compare: null, charts: {}, archLoaded: false,
    _refresh: null,

    // ------------------------------------------------------------ lifecycle
    init() {
      Alpine.store('app', this);
      this.route();
      window.addEventListener('hashchange', () => this.route());
      this.connect();
      this.api('/api/customers?store_id=S1').then(r => { this.c.customers = r || []; });
      this.api('/api/demo/script').then(r => { this.demo.script = r || []; });
    },
    route() {
      const v = (location.hash.replace('#/', '') || 'live');
      this.view = ['live', 'soundbox', 'merchant', 'customer', 'overview'].includes(v) ? v : 'live';
      if (this.view === 'overview') this.$nextTick(() => this.loadOverview());
    },
    go(v) { location.hash = '#/' + v; },
    connect() {
      const es = new EventSource('/api/stream');
      es.onopen = () => { this.connected = true; };
      es.onerror = () => { this.connected = false; };
      es.onmessage = (ev) => this.handle(JSON.parse(ev.data));
    },
    handle(msg) {
      const d = msg.data;
      if (msg.type === 'snapshot') { this.snap = d; this.scheduleRefresh(); }
      else if (msg.type === 'trace') { this.trace.push(d); if (this.trace.length > 300) this.trace.splice(0, 100); this.light(d.node); }
      else if (msg.type === 'notify') this.onNotify(d);
      else if (msg.type === 'audio') this.speak(d.text, d.lang, d.url);
      else if (msg.type === 'toast') this.flashToast(d.text, d.level);
      else if (msg.type === 'caption') { /* captions arrive inside the snapshot (demo.caption) */ }
    },

    // ------------------------------------------------------------ helpers
    async api(path, opts = {}) {
      try {
        const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) { this.flashToast(body.detail || `Request failed (${r.status})`, 'error'); return null; }
        return body;
      } catch (e) { this.flashToast('Server not reachable', 'error'); return null; }
    },
    post(type, payload = {}) {
      return this.api('/api/events', { method: 'POST', body: JSON.stringify({ type, payload }) });
    },
    flashToast(text, level = 'info') {
      this.toast = { text, level };
      clearTimeout(this._toastT);
      this._toastT = setTimeout(() => { this.toast = null; }, 4200);
    },
    onNotify(n) {
      const [kind, id] = (n.target || '').split(':');
      if (kind === 'customer' && this.snap?.customer && id !== this.snap.customer.id) return;
      if (kind === 'customer' || kind === 'merchant') {
        this.notif[kind] = n;
        clearTimeout(this['_n' + kind]);
        this['_n' + kind] = setTimeout(() => { this.notif[kind] = null; }, 5000);
      } else this.flashToast(`${n.title} — ${n.body}`, 'warn');
    },
    tapNotif(kind) {
      const n = this.notif[kind];
      this.notif[kind] = null;
      if (!n || !n.action) return;
      if (n.action.token) this.openConfirm(n.action.token);
      else if (n.action.message_id) this.c.screen = 'messages';
      else if (n.action.pending_id || n.action.entry_id) this.m.screen = 'home';
      else if (n.action.advance_id) this.openAdvance();
      else if (n.action.customer_id) this.openCustomer(n.action.customer_id);
      else if (kind === 'merchant' && n.title === 'Reminders ready') this.m.screen = 'collect';
    },
    light(node) {
      const el = document.getElementById(node);
      if (!el || !el.classList.contains('node')) return;
      el.classList.add('lit');
      clearTimeout(el._t);
      el._t = setTimeout(() => el.classList.remove('lit'), 1200);
    },
    speak(text, lang, url) {
      if (!this.soundOn || !text) return;
      if (url) {
        const a = this.$refs.audio; a.src = url; this.playing = true;
        a.onended = () => { this.playing = false; }; a.play().catch(() => { this.playing = false; });
        return;
      }
      // Until the TTS adapter returns audio, use the browser's own voice if it has one for this language.
      if (!('speechSynthesis' in window)) return;
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang || 'hi-IN'; u.rate = 1.02;
      u.onstart = () => { this.playing = true; }; u.onend = () => { this.playing = false; };
      speechSynthesis.cancel(); speechSynthesis.speak(u);
    },
    start(withSound) {
      this.started = true; this.soundOn = withSound;
      if (withSound && this.snap?.merchant?.briefing) this.speak(this.snap.merchant.briefing.text, this.snap.merchant.briefing.lang);
    },
    scheduleRefresh() {
      clearTimeout(this._refresh);
      this._refresh = setTimeout(() => this.refreshScreens(), 200);
    },
    refreshScreens() {
      if (this.m.screen === 'book') this.loadBook();
      if (this.m.screen === 'customer' && this.m.detail) this.openCustomer(this.m.detail.id, true);
      if (this.m.screen === 'thread' && this.m.thread) this.openThread(this.m.thread, true);
      if (this.m.screen === 'advance') this.openAdvance(true);
    },
    get now() { return this.snap?.now; },
    get top() { return this.snap?.soundbox?.top; },
    get front() { return this.snap?.soundbox?.front || { mode: 'idle' }; },
    get M() { return this.snap?.merchant; },
    get C() { return this.snap?.customer; },
    msLabel(t) { return !t.source && t.ms !== null && t.ms !== undefined ? t.ms + ' ms' : ''; },
    get traceTail() { return this.trace.slice(-8).reverse(); },
    get traceLong() { return this.trace.slice(-80).reverse(); },

    // ------------------------------------------------------------ top bar
    setLang(lang) { this.post('set_language', { lang }); },
    nextDay() { this.post('advance_day', { days: 1 }); },
    async reset() {
      this.demo.busy = true;
      this.trace = [];
      await this.api('/api/demo/reset', { method: 'POST' });
      this.m.screen = 'home'; this.m.chat = []; this.c.screen = 'home'; this.c.sheet = null; this.sb.why = false;
      this.demo.busy = false;
    },

    // ------------------------------------------------------------ Demo Mode
    async demoNext() {
      if (this.demo.busy) return;
      this.demo.busy = true;
      const r = await this.api('/api/demo/next', { method: 'POST' });
      this.demo.busy = false;
      if (r && r.beat === 2 && r.awaiting) { /* presenter: click the QR on the Soundbox */ }
      if (r && r.beat === 4 && !r.awaiting) this.openAdvance();
    },
    async demoPrev() {
      const b = this.snap?.demo?.beat || 0;
      if (b <= 0 || this.demo.busy) return;
      this.demo.busy = true;
      this.trace = [];
      await this.api(`/api/demo/goto/${b - 1}`, { method: 'POST' });
      this.m.screen = 'home'; this.c.screen = 'home'; this.c.sheet = null;
      this.demo.busy = false;
    },

    // ------------------------------------------------------------ Soundbox
    say(preset) { this.post(preset.cash ? 'cash_reported' : 'udhaar_spoken', { store_id: 'S1', customer_id: preset.id, amount: preset.amount }); },
    presets: [
      { label: 'Priya 340 udhaar', id: 'C_PRIYA', amount: 340 },
      { label: 'Ramesh 340 udhaar', id: 'C_RAMESH', amount: 340 },
      { label: 'Vikram 340 udhaar', id: 'C_VIKRAM', amount: 340 },
      { label: 'Anita 300 udhaar (new)', id: 'C_ANITA', amount: 300 },
      { label: 'Suresh 300 cash diye', id: 'C_SURESH', amount: 300, cash: true },
    ],
    sayText() {
      const t = this.sb.text.trim();
      if (!t) return;
      this.post('udhaar_spoken', { store_id: 'S1', text: t });
      this.sb.text = '';
    },
    pickCandidate(cid) {
      const t = this.top;
      if (!t) return;
      this.post(t.intent === 'cash_repayment' ? 'cash_reported' : 'udhaar_spoken', { store_id: 'S1', customer_id: cid, amount: t.amount });
    },
    override() {
      const t = this.top;
      if (!t) return;
      if (t.entry_id) this.post('guardrail_override', { entry_id: t.entry_id });
      else this.post('guardrail_override', { store_id: 'S1', customer_id: t.customer_id, amount: t.requested });
    },
    // "Customer scans" = clicking the confirm QR: opens the Confirm sheet on the customer's phone.
    async scanConfirm() {
      const f = this.front;
      if (!f.token) return;
      if (this.C && f.customer_id !== this.C.id) await this.post('set_focus_customer', { customer_id: f.customer_id });
      this.openConfirm(f.token);
    },
    scanPay() {
      const f = this.front;
      if (!f.pay_qr) return;
      const me = this.C && this.C.id === f.customer_id ? this.C : null;
      this.post('upi_payment', { store_id: 'S1', payer_vpa: me?.vpa || `${f.customer_id?.toLowerCase()}@ptyes`,
                                 payer_name: me?.name || null, amount: f.pay_amount, ref: f.sale_ref });
    },
    key(k) {
      if (k === '⌫') this.sb.keypad = this.sb.keypad.slice(0, -1);
      else if (this.sb.keypad.length < 10) this.sb.keypad += k;
    },
    async submitNewCustomer() {
      const f = this.front, name = (this.sb.newName || f.name || '').trim();
      if (!/^[6-9]\d{9}$/.test(this.sb.keypad)) { this.flashToast('Enter a 10-digit mobile number', 'warn'); return; }
      await this.post('new_customer', { store_id: 'S1', name, mobile: this.sb.keypad, amount: f.amount });
      this.sb.keypad = ''; this.sb.newName = '';
      this.api('/api/customers?store_id=S1').then(r => { this.c.customers = r || this.c.customers; });
    },
    minutesLeft(exp) { const m = U.minutesBetween(this.now, exp); return m === null ? null : Math.max(0, m); },

    // ------------------------------------------------------------ merchant app
    async loadBook() { this.m.book = (await this.api('/api/customers?store_id=S1')) || []; },
    get bookFiltered() {
      const q = this.m.q.trim().toLowerCase();
      return this.m.book.filter(c => !q || c.name.toLowerCase().includes(q))
        .sort((a, b) => b.outstanding - a.outstanding || a.name.localeCompare(b.name));
    },
    openBook() { this.m.screen = 'book'; this.loadBook(); },
    async openCustomer(id, quiet) {
      const d = await this.api(`/api/customers/${id}?store_id=S1`);
      if (d) { this.m.detail = d; if (!quiet) this.m.screen = 'customer'; }
    },
    async openThread(cid, quiet) {
      this.m.thread = cid;
      this.m.threadMsgs = (await this.api(`/api/messages?store_id=S1&customer_id=${cid}`)) || [];
      if (!quiet) this.m.screen = 'thread';
    },
    async openAdvance(quiet) {
      const a = this.M?.advance;
      if (a) { this.m.adv = await this.api(`/api/advances/${a.id}`); this.m.elig = null; }
      else { this.m.adv = null; this.m.elig = await this.api('/api/advances/eligibility?store_id=S1&bill_id=B1'); }
      if (!quiet) this.m.screen = 'advance';
    },
    async offerAdvance(billId = 'B1') { const r = await this.post('offer_advance', { store_id: 'S1', bill_id: billId }); if (r) this.openAdvance(); },
    acceptAdvance() { this.post('advance_accept', { advance_id: this.M.advance.id }); },
    declineAdvance() { this.post('advance_decline', { advance_id: this.M.advance.id }); },
    remind(ids) { this.post('nudges_requested', ids ? { store_id: 'S1', customer_ids: ids } : { store_id: 'S1' }); },
    approveAll() { const ids = (this.M?.drafts || []).map(d => d.message_id); if (ids.length) this.post('nudges_approved', { message_ids: ids }); },
    resolveMatch(pid, cid) { this.post('match_resolved', { pending_id: pid, customer_id: cid }); },
    correct(entryId, amount) { this.post('entry_corrected', { entry_id: entryId, amount }); },
    advStepClass(step) {
      const order = ['offered', 'accepted', 'disbursed', 'repaying', 'closed'];
      const st = this.M?.advance?.state; const i = order.indexOf(st), j = order.indexOf(step);
      return j < i ? 'on' : j === i ? 'cur' : '';
    },
    async askMunim(q) {
      const question = (q || this.m.question).trim();
      if (!question || this.m.asking) return;
      this.m.screen = 'munim'; this.m.asking = true; this.m.question = '';
      this.m.chat.push({ q: question, a: null });
      const r = await this.api('/api/agents/munim/ask', { method: 'POST', body: JSON.stringify({ store_id: 'S1', question }) });
      this.m.asking = false;
      this.m.chat[this.m.chat.length - 1].a = r || { answer: 'Sorry, I could not answer that.', actions: [], steps: [] };
      this.$nextTick(() => { const el = this.$refs.munimScroll; if (el) el.scrollTop = el.scrollHeight; });
    },
    get munimChat() {
      if (this.m.chat.length) return this.m.chat;
      const last = this.M?.munim_last;
      return last ? [{ q: last.question, a: last }] : [];
    },
    async munimAction(a) {
      const p = a.params || {};
      if (a.type === 'send_nudges') { await this.post('nudges_requested', { store_id: 'S1', customer_ids: p.customer_ids }); this.m.screen = 'collect'; }
      else if (a.type === 'offer_advance') this.offerAdvance(p.bill_id);
      else if (a.type === 'open_customer') this.openCustomer(p.customer_id);
    },
    playBriefing() { const b = this.M?.briefing; if (b) { const was = this.soundOn; this.soundOn = true; this.speak(b.text, b.lang, b.audio_url); this.soundOn = was; } },
    get escalations() { return (this.M?.threads || []).filter(t => t.escalated); },

    // ------------------------------------------------------------ customer app
    focus(id) { this.c.screen = 'home'; this.c.sheet = null; this.post('set_focus_customer', { customer_id: id }); },
    async openConfirm(token) {
      const d = await this.api(`/api/confirm/${token}`);
      if (!d) return;
      this.c.confirm = d; this.c.consent = true; this.c.disputing = false; this.c.reason = ''; this.c.claimed = null;
      this.c.sheet = 'confirm';
    },
    async doConfirm() {
      const d = this.c.confirm; this.c.busy = true;
      const payload = { token: d.token, device_id: 'dev-' + d.customer_id.replace(/^C_/, '').toLowerCase() };
      if (d.first_time) payload.consents = { data_share: this.c.consent };
      const r = await this.post('customer_confirm', payload);
      this.c.busy = false;
      if (r) this.c.sheet = null;
    },
    async doDispute() {
      const d = this.c.confirm;
      const r = await this.post('customer_dispute', { token: d.token, reason: this.c.reason || 'Amount is wrong',
                                                      claimed_amount: this.c.claimed ? Number(this.c.claimed) : null });
      if (r) this.c.sheet = null;
    },
    payerVpa() { return this.C?.vpa || `${this.C?.mobile}@ptyes`; },
    pay(storeId, amount) {
      this.post('upi_payment', { store_id: storeId, payer_vpa: this.payerVpa(), payer_name: this.C.name, amount });
    },
    openAutopay(params = {}) {
      this.c.autopay = { store_id: params.store_id || 'S1', cap: params.cap || 3000, start: params.window_start_day || 1, end: params.window_end_day || 5 };
      this.c.sheet = 'autopay';
    },
    async activateAutopay() {
      const a = this.c.autopay;
      const r = await this.post('mandate_created', { customer_id: this.C.id, store_id: a.store_id, cap: Number(a.cap),
                                                     window_start_day: Number(a.start), window_end_day: Number(a.end) });
      if (r) this.c.sheet = null;
    },
    msgAction(a) {
      if (a.type === 'setup_autopay') this.openAutopay(a);
      else if (a.type === 'pay') this.pay(a.store_id, a.amount);
    },
    async sendReply() {
      const t = this.c.reply.trim();
      if (!t || this.c.busy) return;
      this.c.busy = true; this.c.reply = '';
      await this.post('customer_reply', { customer_id: this.C.id, store_id: 'S1', text: t });
      this.c.busy = false;
      this.$nextTick(() => { const el = this.$refs.chatScroll; if (el) el.scrollTop = el.scrollHeight; });
    },
    get hasActiveMandate() { return (this.C?.mandates || []).some(m => m.status === 'active'); },
    get totalDues() { return (this.C?.dues || []).reduce((s, d) => s + d.amount, 0); },

    // ------------------------------------------------------------ controls
    ctlPayment() {
      const c = this.ctl;
      this.post('upi_payment', { store_id: 'S1', payer_vpa: c.vpa, payer_name: c.name || null, amount: Number(c.amount), remark: c.remark || null });
    },
    ctlSalary() { this.post('salary_credited', { customer_id: this.ctl.salary }); },
    ctlBill() { this.post('bill_added', { store_id: 'S1', distributor: this.ctl.billName, amount: Number(this.ctl.billAmount), due_date: this.ctl.billDue }); },
    fraud() { this.post('inject_fraud_ring', { store_id: 'S2' }); },

    // ------------------------------------------------------------ overview
    async loadOverview() {
      if (!this.archLoaded) {
        const r = await fetch('/static/img/architecture.svg');
        if (r.ok) { this.$refs.arch.innerHTML = await r.text(); this.archLoaded = true; }
      }
      if (!this.compare) this.compare = await this.api('/api/overview/compare');
      this.$nextTick(() => this.drawCharts());
    },
    drawCharts() {
      if (!this.compare || !window.Chart) return;
      const days = this.compare.days.map(d => U.date(d));
      const mk = (ref, key, title) => {
        const el = this.$refs[ref]; if (!el) return;
        this.charts[ref]?.destroy();
        const s = this.compare.series[key];
        this.charts[ref] = new Chart(el, {
          type: 'line',
          data: { labels: days, datasets: [
            { label: 'Notebook', data: s.notebook, borderColor: '#D93025', backgroundColor: 'rgba(217,48,37,.08)', fill: true, tension: .3, pointRadius: 0, borderWidth: 2.5 },
            { label: 'Bharosa', data: s.bharosa, borderColor: '#042E6F', backgroundColor: 'rgba(0,186,242,.12)', fill: true, tension: .3, pointRadius: 0, borderWidth: 2.5 },
          ] },
          options: { responsive: true, maintainAspectRatio: false, animation: { duration: 600 },
                     plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${U.inr(c.parsed.y)}` } } },
                     scales: { y: { ticks: { callback: (v) => U.inr(v) } }, x: { ticks: { maxTicksLimit: 8 } } } },
        });
      };
      mk('chartStuck', 'money_stuck');
      mk('chartBad', 'bad_udhaar');
    },
  }));
});
