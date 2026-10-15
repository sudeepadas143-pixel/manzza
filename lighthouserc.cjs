/**
 * Lighthouse CI: `npx lhci autorun` against the production build served by
 * `vite preview` on :4173 (start it first: `npm run build && npx vite preview --port 4173`).
 */
const base = 'http://localhost:4173';
module.exports = {
  ci: {
    collect: {
      url: ['/', '/products/mitre-core', '/products/ei-laminations', '/products/strip-laminations', '/materials', '/plant', '/about', '/quote'].map((p) => base + p),
      numberOfRuns: 1,
      settings: { chromeFlags: '--no-sandbox --headless=new' },
    },
    assert: {
      assertions: {
        'categories:seo': ['error', { minScore: 0.95 }],
        'categories:accessibility': ['warn', { minScore: 0.95 }],
        'categories:best-practices': ['warn', { minScore: 0.95 }],
        'categories:performance': ['warn', { minScore: 0.7 }],
      },
    },
    upload: { target: 'filesystem', outputDir: '.lighthouseci/reports' },
  },
};
