// Bharosa pitch deck (spec §10.8). Plain JS, no framework: slides, keys, scaling, notes, print modes.
//   ?print         print layout (used by scripts/build_pdf.py)
//   ?print&notes   each slide followed by its speaker notes (rehearsal PDF)
(() => {
  const params = new URLSearchParams(location.search);
  const slides = [...document.querySelectorAll('.slide')];
  const total = slides.length;
  // The HUD shows each section (data-group) once, in slide order.
  const GROUPS = [...new Set(slides.map(s => s.dataset.group).filter(Boolean))];

  // Footer on every content slide: product, section label (data-act), number. Title and close have none.
  slides.forEach((s, k) => {
    if (!s.dataset.act) return;
    const foot = document.createElement('div');
    foot.className = 'foot';
    foot.innerHTML = `<span><b>Bharosa <span>on Paytm</span></b> · Team MerchantMavericks</span><span>${s.dataset.act}</span><span>${k + 1} / ${total}</span>`;
    s.appendChild(foot);
  });

  if (params.has('print')) {
    document.body.classList.add('print');
    if (params.has('notes')) {
      document.body.classList.add('with-notes');
      const style = document.createElement('style');
      style.textContent = '@media print { @page { size: 1280px 1100px; margin: 0; } }';
      document.head.appendChild(style);
      slides.forEach(s => {
        const page = document.createElement('div');
        page.className = 'page';
        s.replaceWith(page);
        page.appendChild(s);
        const notes = s.querySelector('.notes');
        if (notes) page.appendChild(notes);
      });
    }
    return;
  }

  // ----- screen mode -----
  const hud = document.querySelector('.hud');
  hud.innerHTML = GROUPS.map(g => `<span data-group="${g}">${g}</span>`).join('') + '<span class="count"></span><span class="hint">← → move · F fullscreen · N notes</span>';
  const panel = document.querySelector('.notes-panel');
  let i = 0;

  function fit() {
    const notesH = document.body.classList.contains('show-notes') ? Math.round(innerHeight * 0.3) : 0;
    document.documentElement.style.setProperty('--notes-h', notesH + 'px');
    const s = Math.min((innerWidth - 16) / 1280, (innerHeight - notesH - 48) / 720);
    document.documentElement.style.setProperty('--s', Math.max(s, 0.1).toFixed(4));
  }

  function go(n) {
    i = Math.max(0, Math.min(total - 1, n));
    slides.forEach((s, k) => s.classList.toggle('active', k === i));
    const group = slides[i].dataset.group;
    hud.querySelectorAll('[data-group]').forEach(e => e.classList.toggle('on', e.dataset.group === group));
    hud.querySelector('.count').textContent = `${i + 1} / ${total}`;
    const notes = slides[i].querySelector('.notes');
    panel.innerHTML = notes ? notes.innerHTML : '';
    if (location.hash !== '#' + (i + 1)) history.replaceState(null, '', '#' + (i + 1));
  }

  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  }

  function key(k) {
    if (['ArrowRight', 'ArrowDown', ' ', 'PageDown'].includes(k)) go(i + 1);
    else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(k)) go(i - 1);
    else if (k === 'Home') go(0);
    else if (k === 'End') go(total - 1);
    else if (k === 'f' || k === 'F') fullscreen();
    else if (k === 'n' || k === 'N') { document.body.classList.toggle('show-notes'); fit(); }
    else return false;
    return true;
  }

  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (key(e.key)) e.preventDefault();
  });
  document.querySelector('.stage').addEventListener('click', e => go(e.clientX > innerWidth / 2 ? i + 1 : i - 1));
  addEventListener('resize', fit);
  addEventListener('hashchange', () => go(parseInt(location.hash.slice(1), 10) - 1 || 0));

  window.deck = { go, key, fullscreen, get index() { return i; }, total };
  fit();
  go(parseInt(location.hash.slice(1), 10) - 1 || 0);
})();
