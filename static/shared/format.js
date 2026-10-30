// Pure display helpers shared by every app. No data lives here.
window.F = (() => {
  const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const parts = (iso) => {
    if (!iso) return null;
    const [d, t = '00:00'] = iso.split('T');
    const [y, m, day] = d.split('-').map(Number);
    return { y, m, day, wd: new Date(Date.UTC(y, m - 1, day, 12)).getUTCDay(), hh: t.slice(0, 2), mm: t.slice(3, 5) };
  };
  return {
    inr(n) {
      if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
      const v = Math.round(Number(n));
      return (v < 0 ? '−₹' : '₹') + Math.abs(v).toLocaleString('en-IN');
    },
    date(iso) { const p = parts(iso); return p ? `${p.day} ${MO[p.m - 1]}` : ''; },
    dayDate(iso) { const p = parts(iso); return p ? `${WD[p.wd]} ${p.day} ${MO[p.m - 1]}` : ''; },
    time(iso) { const p = parts(iso); return p ? `${p.hh}:${p.mm}` : ''; },
    ordinal(n) { const s = (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'); return n + s; },
    initials(name) { return (name || '?').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase(); },
    first(name) { return (name || '').split(' ')[0]; },
    bandPill(b) { return { green: 'pill-green', amber: 'pill-amber', red: 'pill-red', waiting: 'pill-grey' }[b] || 'pill-grey'; },
    bandWord(b) { return { green: 'Safe', amber: 'Caution', red: 'High risk', waiting: 'Waiting' }[b] || b; },
    scorePill(b) { return { Building: 'pill-red', Good: 'pill-amber', Strong: 'pill-green', Excellent: 'pill-green' }[b] || 'pill-grey'; },
    statePill(st) {
      const k = (st || '').toLowerCase().replace(' ', '_');
      return { proposed: 'pill-amber', verified: 'pill-navy', partly_paid: 'pill-violet', settled: 'pill-green', disputed: 'pill-red',
               cancelled: 'pill-grey', expired: 'pill-grey', written_off: 'pill-red', offered: 'pill-amber', repaying: 'pill-violet',
               closed: 'pill-green', declined: 'pill-grey', accepted: 'pill-navy', delivered: 'pill-green', approved: 'pill-navy',
               done: 'pill-green', proposed_action: 'pill-amber' }[k] || 'pill-grey';
    },
    stateWord(st) { return (st || '').replace('_', ' ').replace(/^./, c => c.toUpperCase()); },
    srcBadge(src) { return { ai: ['AI', 'badge-ai'], rule: ['RULE', 'badge-rule'], template: ['TEMPLATE', 'badge-template'] }[src] || ['', '']; },
    qr(text, dark = '#042E6F') {
      if (!text || !window.qrcode) return '';
      const q = window.qrcode(0, 'M'); q.addData(text); q.make();
      return q.createSvgTag({ cellSize: 6, margin: 2, scalable: true }).replace(/fill="#000000"/g, `fill="${dark}"`);
    },
    gauge(score) {
      const t = Math.max(0, Math.min(1, (score - 300) / 600)), a = Math.PI * (1 - t), r = 80, cx = 100, cy = 96;
      const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
      const col = score >= 700 ? '#1E9E5A' : score >= 550 ? '#E08A00' : '#D93025';
      return `<svg width="200" height="110" viewBox="0 0 200 110" aria-hidden="true" style="display:block;margin:0 auto">
        <path d="M20 96 A80 80 0 0 1 180 96" fill="none" stroke="#E6E8EC" stroke-width="14" stroke-linecap="round"/>
        <path d="M20 96 A80 80 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${col}" stroke-width="14" stroke-linecap="round"/>
        <text x="20" y="108" font-size="10" fill="#8A94A6" text-anchor="middle">300</text>
        <text x="180" y="108" font-size="10" fill="#8A94A6" text-anchor="middle">900</text></svg>`;
    },
  };
})();
