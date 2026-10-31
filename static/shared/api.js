// Fetch wrapper + "changed" pings (v2 spec §8). Each app refetches its own view when a scope it cares about changes.
window.API = (() => {
  let adminKey = null;
  try { adminKey = localStorage.getItem('bh_admin_key'); } catch (e) { /* storage blocked */ }

  async function call(path, { method = 'GET', body, admin = false } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (admin && adminKey) headers['X-Admin-Key'] = adminKey;
    const r = await fetch(path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const err = new Error(data.detail || `Request failed (${r.status})`); err.status = r.status; throw err; }
    return data;
  }

  // One EventSource per page. on(scopeTest, fn) runs fn when a ping lists a matching scope.
  // Some proxies (a Cloudflare quick tunnel) buffer SSE, so nothing arrives, not even the
  // server's "hello". If the stream is silent for 4 s, switch to long-polling /api/changes.
  const handlers = [];
  let es, live = false, polling = false;
  function dispatch(msg) {
    if (!msg || !msg.scopes) return;
    for (const h of handlers) if (msg.scopes.some(h.test)) h.fn(msg);
  }
  function resync() { for (const h of handlers) h.fn({ type: 'reconnect', scopes: [] }); }
  function listen() {
    if (es) return;
    es = new EventSource('/api/stream');
    es.onmessage = (ev) => {
      live = true;
      let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
      dispatch(msg);
    };
    es.onopen = resync;
    setTimeout(() => { if (!live) { es.close(); poll(); } }, 4000);
  }
  async function poll() {
    if (polling) return;
    polling = true;
    let after = -1;
    for (;;) {
      try {
        const r = await fetch(`/api/changes?after=${after}`, { cache: 'no-store', credentials: 'same-origin' });
        if (!r.ok) throw new Error(`changes ${r.status}`);
        const out = await r.json();
        after = out.seq;
        if (out.reset) resync();
        for (const m of out.events) dispatch(m);
      } catch (e) {
        await new Promise((res) => setTimeout(res, 2000));
      }
    }
  }
  function on(test, fn) { handlers.push({ test: typeof test === 'string' ? (s) => s === test : test, fn }); listen(); }

  function deviceId() {
    try {
      let id = localStorage.getItem('bh_device_id');
      if (!id) { id = 'dev-' + Math.random().toString(36).slice(2, 10); localStorage.setItem('bh_device_id', id); }
      return id;
    } catch (e) { return 'dev-unknown'; }
  }

  return {
    get: (p, o) => call(p, o), post: (p, body, o = {}) => call(p, { ...o, method: 'POST', body: body ?? {} }), on, deviceId,
    setAdminKey(k) { adminKey = k; try { localStorage.setItem('bh_admin_key', k); } catch (e) { /* ignore */ } },
    hasAdminKey: () => !!adminKey,
  };
})();
