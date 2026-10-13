/**
 * Shared behaviour for every page: navigation, mobile menu, product visuals,
 * mobile sticky quote bar.
 */
import { initMinis } from './minis.js';
import { initMotion } from './motion.js';

function initNav() {
  const header = document.querySelector('[data-header]');
  if (!header) return;

  // Products dropdown: click / Enter toggles, hover opens on mouse devices, Esc closes.
  header.querySelectorAll('[data-dd]').forEach((item) => {
    const btn = item.querySelector('.dd-toggle');
    const set = (open) => {
      btn.setAttribute('aria-expanded', String(open));
      item.classList.toggle('is-open', open);
    };
    // a click right after hover opened the menu keeps it open (it would otherwise toggle shut)
    let hoverOpenedAt = 0;
    btn.addEventListener('click', () => {
      if (performance.now() - hoverOpenedAt < 600) { set(true); hoverOpenedAt = 0; return; }
      set(btn.getAttribute('aria-expanded') !== 'true');
    });
    const hover = window.matchMedia('(hover: hover) and (pointer: fine)');
    let t;
    item.addEventListener('mouseenter', () => { if (hover.matches) { clearTimeout(t); if (btn.getAttribute('aria-expanded') !== 'true') hoverOpenedAt = performance.now(); set(true); } });
    item.addEventListener('mouseleave', () => { if (hover.matches) t = setTimeout(() => set(false), 160); });
    item.addEventListener('keydown', (e) => { if (e.key === 'Escape') { set(false); btn.focus(); } });
    item.addEventListener('focusout', (e) => { if (!item.contains(e.relatedTarget)) set(false); });
    document.addEventListener('click', (e) => { if (!item.contains(e.target)) set(false); });
  });

  // Mobile menu
  const toggle = header.querySelector('.menu-toggle');
  const menu = document.getElementById('mobile-menu'); // sibling of the header (see render.js)
  if (toggle && menu) {
    const set = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.querySelector('.menu-toggle__label').textContent = open ? 'Close' : 'Menu';
      menu.hidden = !open;
      document.documentElement.classList.toggle('menu-open', open);
      // the full-screen menu is the only thing that can be reached while it is open
      document.querySelectorAll('main, footer').forEach((el) => { el.inert = open; });
    };
    toggle.addEventListener('click', () => set(toggle.getAttribute('aria-expanded') !== 'true'));
    menu.addEventListener('click', (e) => { if (e.target.closest('a')) set(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !menu.hidden) { set(false); toggle.focus(); } });
    window.matchMedia('(min-width: 961px)').addEventListener('change', (m) => { if (m.matches) set(false); });
  }

  // Overlay nav: transparent over the film, solid black after it; hides while
  // scrolling down, comes back as soon as the visitor scrolls up.
  const intro = document.querySelector('#intro');
  let lastY = window.scrollY;
  let ticking = false;
  const update = () => {
    ticking = false;
    const y = window.scrollY;
    const solidFrom = intro ? intro.offsetTop + intro.offsetHeight - header.offsetHeight : 8;
    header.classList.toggle('is-solid', y > solidFrom);
    if (Math.abs(y - lastY) > 6) {
      header.classList.toggle('is-hidden', y > lastY && y > header.offsetHeight * 3);
      lastY = y;
    }
  };
  update();
  window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
}

function initStickyBar() {
  const bar = document.querySelector('[data-stickybar]');
  if (!bar) return;
  // hide the mobile quote bar while another quote button is already on screen
  const targets = [...document.querySelectorAll('.band--phero .btn, .cta .btn')];
  const seen = new Set();
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => (e.isIntersecting ? seen.add(e.target) : seen.delete(e.target)));
    bar.classList.toggle('is-visible', seen.size === 0 && window.scrollY > 200);
  });
  targets.forEach((t) => io.observe(t));
  window.addEventListener('scroll', () => bar.classList.toggle('is-visible', seen.size === 0 && window.scrollY > 200), { passive: true });
}

export function initCommon() {
  document.documentElement.classList.add('js');
  initNav();
  initMotion();
  initMinis();
  initStickyBar();
  document.querySelectorAll('[data-year]').forEach((el) => { el.textContent = new Date().getFullYear(); });
}

if (!window.__manzzaCommon) {
  window.__manzzaCommon = true;
  initCommon();
}
