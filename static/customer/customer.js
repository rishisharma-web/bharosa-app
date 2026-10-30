// Customer app (Paytm-app style). Everything comes from /api/customer/* and /api/requests/*.
document.addEventListener('alpine:init', () => {
  Alpine.data('customerApp', () => ({
    F: window.F,
    ready: false, me: null, phone: '', otp: '', otpSent: false,
    tab: 'home', home: null, threads: [], replyText: {}, busy: false, toast: null,
    sheet: null, req: null, notice: '', payMethod: 'upi', disputing: false, reason: '',
    payTo: null, payAmount: 0, autopay: { store: '', store_id: '', cap: 0, collection_day: 0 }, basket: null,
    _scanner: null, _pendingToken: null, _answering: null,

    async init() {
      const m = location.pathname.match(/^\/c\/r\/([\w-]+)/);
      if (m) this._pendingToken = m[1];
      try { this.me = await API.get('/api/me/customer'); } catch (e) { this.me = null; }
      this.ready = true;
      if (this.me) await this.start();
    },
    async start() {
      await this.load();
      API.on((s) => s === `customer:${this.me.customer_id}`, () => this.refresh());
      if (this._pendingToken) { const t = this._pendingToken; this._pendingToken = null; this.openRequest(t); }
    },
    flash(text, error = false) { this.toast = { text, error }; setTimeout(() => { this.toast = null; }, 3500); },
    async load() { this.home = await API.get('/api/customer/home'); },
    async refresh() {
      await this.load();
      if (this.tab === 'messages') await this.loadMessages();
      if (this.req && this.req.token !== this._answering && (this.sheet === 'confirm' || this.sheet === 'share')) {
        try { this.req = await API.get(`/api/requests/${this.req.token}`); if (this.req.status !== 'open') this.showRequestState(); } catch (e) { /* closed */ }
      }
    },

    // ---------------------------------------------------- login
    async startOtp() {
      try { await API.post('/api/auth/otp/start', { phone: this.phone, app: 'customer' }); this.otpSent = true; }
      catch (e) { this.flash(e.message, true); }
    },
    async verify() {
      try {
        await API.post('/api/auth/otp/verify', { phone: this.phone, otp: this.otp, app: 'customer' });
        this.me = await API.get('/api/me/customer'); await this.start();
      } catch (e) { this.flash(e.message, true); }
    },

    // ---------------------------------------------------- requests (the QR bridge)
    act(a) {
      if (a.kind === 'request') this.openRequest(a.token);
      else if (a.kind === 'basket') this.openBasket(a.basket_id);
      else { this.tab = 'messages'; this.loadMessages(); }
    },
    async openRequest(token) {
      history.replaceState(null, '', '/customer');
      try {
        this.req = await API.get(`/api/requests/${token}`);
        this.disputing = false; this.reason = ''; this.payMethod = 'upi';
        if (this.req.status !== 'open') return this.showRequestState();
        this.sheet = this.req.kind === 'share' ? 'share' : 'confirm';
      } catch (e) { this.notice = e.message; this.sheet = 'notice'; }
    },
    showRequestState() {
      this.notice = this.req.message || ({ completed: 'Done ✓', declined: 'This request was closed.', expired: 'This request has expired. Ask the shop to try again.' }[this.req.status] || 'Closed');
      this.sheet = 'notice';
    },
    async share(decision) {
      this.busy = true;
      const token = this.req.token;
      this.req = null;  // a live refresh during the call must not re-read the share request it completes
      try {
        const out = await API.post(`/api/requests/${token}/share`, { decision });
        if (out.next_token) await this.openRequest(out.next_token); else this.closeSheet();
      } catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    async confirm() {
      this.busy = true;
      const r = this.req;
      this._answering = r.token;
      try {
        await API.post(`/api/requests/${r.token}/confirm`, { pay_method: r.collect_now ? this.payMethod : null, device_id: API.deviceId() });
        this.notice = 'Confirmed ✓'; this.sheet = 'notice'; this.req = null; await this.load();
      } catch (e) { this.flash(e.message, true); } finally { this.busy = false; this._answering = null; }
    },
    async dispute() {
      this.busy = true;
      try { await API.post(`/api/requests/${this.req.token}/dispute`, { reason: this.reason }); this.notice = 'Dispute sent to the shop'; this.sheet = 'notice'; this.req = null; }
      catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },

    // ---------------------------------------------------- scanner
    async openScanner() {
      this.sheet = 'scan';
      await this.$nextTick();
      if (!window.Html5Qrcode) { this.flash('Scanner is loading, try again', true); return; }
      try {
        this._scanner = new Html5Qrcode('reader');
        await this._scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: 240 }, (text) => this.onScan(text));
      } catch (e) { this.flash('Camera needs HTTPS and permission. You can also open the link with your camera app.', true); }
    },
    async onScan(text) {
      await this.stopScanner();
      try {
        const u = new URL(text, location.origin);
        const m = u.pathname.match(/^\/c\/r\/([\w-]+)/);
        if (u.host === location.host && m) return this.openRequest(m[1]);
        if (u.host === location.host) { location.href = u.pathname + u.search; return; }
      } catch (e) { /* not a URL */ }
      this.notice = 'This QR is for payments. Use your UPI app to pay.'; this.sheet = 'notice';
    },
    async stopScanner() { try { await this._scanner?.stop(); } catch (e) { /* already stopped */ } this._scanner = null; },
    async closeSheet() { await this.stopScanner(); this.sheet = null; this.req = null; },

    // ---------------------------------------------------- money, auto-pay, basket
    payableStore() { return (this.home?.dues || []).find(d => !d.is_network); },
    openPay(d) { this.payTo = d; this.payAmount = d.amount; this.sheet = 'pay'; },
    async pay() {
      this.busy = true;
      try { await API.post('/api/customer/pay', { store_id: this.payTo.store_id, amount: Number(this.payAmount), method: 'upi' }); this.notice = 'Paid ' + F.inr(this.payAmount) + ' ✓'; this.sheet = 'notice'; await this.load(); }
      catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    openAutopay(storeId) {
      const d = (this.home?.dues || []).find(x => x.store_id === storeId) || this.payableStore();
      if (!d) return;
      this.autopay = { store: d.store, store_id: d.store_id, cap: this.home.autopay_defaults.cap, collection_day: this.home.autopay_defaults.collection_day };
      this.sheet = 'autopay';
    },
    async activateAutopay() {
      this.busy = true;
      try { await API.post('/api/customer/mandates', { store_id: this.autopay.store_id, cap: Number(this.autopay.cap), collection_day: Number(this.autopay.collection_day) }); this.notice = 'Auto-pay is active ✓'; this.sheet = 'notice'; await this.load(); }
      catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    openBasket(id) { this.basket = (this.home?.baskets || []).find(b => b.id === id); if (this.basket) this.sheet = 'basket'; },
    async basketDecision(d) {
      this.busy = true;
      try { await API.post(`/api/customer/baskets/${this.basket.id}/${d}`); this.notice = d === 'accept' ? 'Basket ordered on credit ✓' : 'OK, not this month'; this.sheet = 'notice'; await this.load(); }
      catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    async revoke(storeId) {
      try { await API.post(`/api/customer/shares/${storeId}/revoke`); await this.load(); } catch (e) { this.flash(e.message, true); }
    },

    // ---------------------------------------------------- messages
    async loadMessages() { this.threads = await API.get('/api/customer/messages'); },
    async reply(storeId) {
      const text = (this.replyText[storeId] || '').trim(); if (!text) return;
      this.busy = true;
      try { await API.post('/api/customer/messages/reply', { store_id: storeId, text }); this.replyText[storeId] = ''; await this.loadMessages(); await this.load(); }
      catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },
    msgAction(a) {
      if (a.type === 'setup_autopay') this.openAutopay(a.store_id);
      else if (a.type === 'pay') { const d = (this.home?.dues || []).find(x => x.store_id === a.store_id); if (d) this.openPay(d); }
    },
  }));
});
