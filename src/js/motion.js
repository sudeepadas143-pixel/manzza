/**
 * Page motion (DESIGN.md, "Motion"). Each effect runs once, is skipped under
 * prefers-reduced-motion, and the page reads the same without it: CSS only
 * hides anything while html.motion is set, which this module sets itself.
 */
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Wrap each word of an element's text in spans, keeping inline markup. */
function splitWords(el, outer, inner) {
  let i = 0;
  const walk = (node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === 1) { walk(child); continue; }
      if (child.nodeType !== 3 || !child.textContent.trim()) continue;
      const frag = document.createDocumentFragment();
      child.textContent.split(/(\s+)/).forEach((part) => {
        if (!part) return;
        if (/^\s+$/.test(part)) { frag.append(' '); return; }
        const w = document.createElement('span');
        w.className = outer;
        if (inner) {
          const s = document.createElement('span');
          s.textContent = part;
          s.style.setProperty('--i', i);
          w.append(s);
        } else {
          w.textContent = part;
        }
        i++;
        frag.append(w);
      });
      child.replaceWith(frag);
    }
  };
  walk(el);
  return el.querySelectorAll(`.${outer}`);
}

function reveals() {
  const rise = [...document.querySelectorAll('[data-rise]')];
  rise.forEach((h) => {
    splitWords(h, 'rw', true);
    // what follows a headline in its block comes in just after it
    let n = h.nextElementSibling;
    while (n && !n.matches('[data-rise], section, ul, ol, table, figure, .table-wrap, dl')) {
      n.setAttribute('data-follow', '');
      n = n.nextElementSibling;
    }
  });
  // observing starts later, once the hidden state is in place without a transition
  return () => {
    const targets = document.querySelectorAll('[data-rise], [data-follow], [data-line]');
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add('is-in');
        io.unobserve(e.target);
      }
    }, { rootMargin: '0px 0px -10% 0px' });
    targets.forEach((t) => io.observe(t));
  };
}

/** The About statement: words light up as it scrolls through the viewport. */
function statement() {
  document.querySelectorAll('[data-words]').forEach((p) => {
    const words = [...splitWords(p, 'sw', false)];
    const n = words.length;
    let ticking = false;
    const update = () => {
      ticking = false;
      const r = p.getBoundingClientRect();
      const vh = window.innerHeight;
      if (r.bottom < -vh || r.top > vh * 2) return;
      const prog = Math.min(1, Math.max(0, (vh * 0.85 - r.top) / (r.height + vh * 0.3)));
      const lit = prog * (n + 6);
      words.forEach((w, i) => w.style.setProperty('--o', (0.6 + 0.4 * Math.min(1, Math.max(0, (lit - i) / 6))).toFixed(3)));
    };
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();
  });
}

/** A figure counts up once when it enters. */
function counters() {
  const ease = (t) => (t === 1 ? 1 : 1 - 2 ** (-10 * t));
  document.querySelectorAll('[data-count]').forEach((el) => {
    const to = Number(el.dataset.count);
    if (!Number.isFinite(to)) return;
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight) return; // already on screen: leave it be
    el.textContent = '0';
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / 1600);
        el.textContent = String(Math.round(to * ease(t)));
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, { rootMargin: '0px 0px -15% 0px' });
    io.observe(el);
  });
}

export function initMotion() {
  const root = document.documentElement;
  if (reduced || root.classList.contains('capture')) { root.classList.remove('motion-pending'); return; }
  // Arriving by link runs the cross-page fade (@view-transition). Revealing during it
  // shows the animation in the fade's snapshot, then again on the live page: the
  // "pops twice". Keep the text hidden until the fade is done, then reveal once.
  // the About globe transition (globe.js) and the cross-page fade both hold the reveal
  const wait = window.__revealAfter || window.__vtDone;
  if (wait) {
    Promise.race([wait.catch(() => {}), new Promise((r) => setTimeout(r, window.__revealAfter ? 6500 : 1200))]).then(begin);
  } else {
    begin();
  }
}

function begin() {
  const root = document.documentElement;
  // 1. split and mark everything; 2. switch to the hidden state with transitions
  // off (motion-init), so text already on screen does not animate OUT first;
  // 3. next frame, transitions back on and the reveals start. Without step 2 every
  // visible paragraph and rule faded out, then faded back in: a double animation.
  const observe = reveals();
  root.classList.add('motion-init', 'motion');
  root.classList.remove('motion-pending');
  void document.body.offsetHeight; // commit the hidden state before transitions return
  requestAnimationFrame(() => requestAnimationFrame(() => {
    root.classList.remove('motion-init');
    observe();
  }));
  statement();
  counters();
}
