// Merchant app (Paytm for Business style). All data from /api/merchant/*; refetches on merchant:<store> pings.
document.addEventListener('alpine:init', () => {
  Alpine.data('merchantApp', () => ({
    F: window.F,
    ready: false, me: null, phone: '', otp: '', otpSent: false,
    tab: 'home', home: null, book: [], q: '', detail: null, collect: { promises: [], schedules: [], threads: [] },
    orders: [], chat: [], question: '', activity: [], activityOpen: false, busy: false, toast: null,

    async init() {
      try { this.me = await API.get('/api/me/merchant'); } catch (e) { this.me = null; }
      this.ready = true;
      if (this.me) await this.start();
    },
    async start() {
      await this.load();
      API.on((s) => s === `merchant:${this.me.store_id}`, () => this.refresh());
    },
    get stock() { return this.home?.stock || {}; },
    planSource() { return (this.home?.growth_plan.actions || []).some(a => a.source === 'ai') ? 'ai' : 'template'; },
    flash(text, error = false) { this.toast = { text, error }; setTimeout(() => { this.toast = null; }, 3500); },
    async load() { this.home = await API.get('/api/merchant/home'); },
    async refresh() {
      await this.load();
      if (this.tab === 'book') { await this.loadBook(); if (this.detail) await this.openCustomer(this.detail.id); }
      if (this.tab === 'collect') await this.loadCollect();
      if (this.tab === 'orders') await this.loadOrders();
      if (this.activityOpen) await this.openActivity();
    },
    async go(t) {
      this.tab = t; this.detail = null;
      if (t === 'book') await this.loadBook();
      if (t === 'collect') await this.loadCollect();
      if (t === 'orders') await this.loadOrders();
    },
    async act(fn, ok) {
      this.busy = true;
      try { await fn(); if (ok) this.flash(ok); await this.refresh(); } catch (e) { this.flash(e.message, true); } finally { this.busy = false; }
    },

    async startOtp() {
      try { await API.post('/api/auth/otp/start', { phone: this.phone, app: 'merchant' }); this.otpSent = true; } catch (e) { this.flash(e.message, true); }
    },
    async verify() {
      try { await API.post('/api/auth/otp/verify', { phone: this.phone, otp: this.otp, app: 'merchant' }); this.me = await API.get('/api/me/merchant'); await this.start(); }
      catch (e) { this.flash(e.message, true); }
    },

    approve(id) { return this.act(() => API.post(`/api/merchant/growth/${id}/approve`)); },
    advance(d) { return this.act(() => API.post(`/api/merchant/advance/${this.stock.advance.id}/${d}`)); },
    async loadBook() { this.book = await API.get('/api/merchant/udhaar-book'); },
    bookFiltered() { const q = this.q.trim().toLowerCase(); return this.book.filter(c => !q || c.name.toLowerCase().includes(q)); },
    async openCustomer(id) { this.detail = await API.get(`/api/merchant/customers/${id}`); },
    cancelEntry(id) { return this.act(() => API.post(`/api/merchant/entries/${id}/cancel`), 'Entry cancelled'); },
    async loadCollect() { this.collect = await API.get('/api/merchant/collect'); },
    async loadOrders() { this.orders = await API.get('/api/merchant/orders'); },
    delivered(id) { return this.act(() => API.post(`/api/merchant/baskets/${id}/delivered`), 'Marked delivered'); },
    async openActivity() { this.activity = await API.get('/api/activity?limit=20'); this.activityOpen = true; },
    async ask() {
      const q = this.question.trim(); if (!q) return;
      this.question = ''; this.chat.push({ q, a: null }); this.busy = true;
      try { this.chat[this.chat.length - 1].a = await API.post('/api/merchant/ask', { question: q }); }
      catch (e) { this.chat[this.chat.length - 1].a = { answer: e.message, source: 'template' }; } finally { this.busy = false; }
    },
  }));
});
