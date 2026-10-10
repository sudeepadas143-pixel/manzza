/**
 * Shared behaviour for every page: navigation, mobile menu, product visuals,
 * mobile sticky quote bar.
 */
import { initMinis } from './minis.js';

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
    btn.addEventListener('click', () => set(btn.getAttribute('aria-expanded') !== 'true'));
    const hover = window.matchMedia('(hover: hover) and (pointer: fine)');
    let t;
    item.addEventListener('mouseenter', () => { if (hover.matches) { clearTimeout(t); set(true); } });
    item.addEventListener('mouseleave', () => { if (hover.matches) t = setTimeout(() => set(false), 160); });
    item.addEventListener('keydown', (e) => { if (e.key === 'Escape') { set(false); btn.focus(); } });
    item.addEventListener('focusout', (e) => { if (!item.contains(e.relatedTarget)) set(false); });
    document.addEventListener('click', (e) => { if (!item.contains(e.target)) set(false); });
  });

  // Mobile menu
  const toggle = header.querySelector('.menu-toggle');
  const menu = header.querySelector('#mobile-menu');
  if (toggle && menu) {
    const set = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.querySelector('.menu-toggle__label').textContent = open ? 'Close' : 'Menu';
      menu.hidden = !open;
      document.documentElement.classList.toggle('menu-open', open);
    };
    toggle.addEventListener('click', () => set(toggle.getAttribute('aria-expanded') !== 'true'));
    menu.addEventListener('click', (e) => { if (e.target.closest('a')) set(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !menu.hidden) { set(false); toggle.focus(); } });
    window.matchMedia('(min-width: 961px)').addEventListener('change', (m) => { if (m.matches) set(false); });
  }

  // Header gets a solid edge once the page scrolls
  const onScroll = () => header.classList.toggle('is-scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

function initStickyBar() {
  const bar = document.querySelector('[data-stickybar]');
  if (!bar) return;
  // hide the mobile quote bar while another quote button is already on screen
  const targets = [...document.querySelectorAll('.phero .btn--primary, .cta .btn--primary, .send .btn--primary')];
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
  initMinis();
  initStickyBar();
  document.querySelectorAll('[data-year]').forEach((el) => { el.textContent = new Date().getFullYear(); });
}

if (!window.__manzzaCommon) {
  window.__manzzaCommon = true;
  initCommon();
}
