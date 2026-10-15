/**
 * Server-side spam checks shared by api/otp.js and api/quote.js.
 */
import { resolveMx } from 'node:dns/promises';

const NO_MAIL = 'This email domain does not receive email. Please check the address.';
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(Object.assign(new Error('timeout'), { code: 'ETIMEOUT' })), ms))]);

/** MX lookup over DNS-over-HTTPS (Cloudflare): 'yes' | 'no' | 'unknown'. */
async function mxOverHttps(domain) {
  try {
    const res = await withTimeout(fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=MX`, { headers: { accept: 'application/dns-json' } }), 2500);
    if (!res.ok) return 'unknown';
    const j = await res.json();
    if (j.Status === 3) return 'no'; // NXDOMAIN: the domain does not exist
    if (j.Status !== 0) return 'unknown';
    const mx = (j.Answer || []).filter((a) => a.type === 15).map((a) => String(a.data).split(' ').pop());
    return mx.length && mx.some((h) => h && h !== '.') ? 'yes' : 'no';
  } catch { return 'unknown'; }
}

/** The same lookup through the server's own resolver: 'yes' | 'no' | 'unknown'. */
async function mxOverDns(domain) {
  try {
    const mx = await withTimeout(resolveMx(domain), 2500);
    return mx.some((r) => r.exchange && r.exchange !== '.') ? 'yes' : 'no';
  } catch (err) {
    return err.code === 'ENOTFOUND' ? 'no' : 'unknown'; // ENODATA can be a resolver that skips MX
  }
}

/**
 * '' when the email's domain can receive mail (it publishes MX records), otherwise
 * the reason: catches made-up and mistyped company domains before a code is sent.
 * Two independent lookups; a domain is refused only when neither finds a mail
 * server and at least one is sure. If DNS itself is unreachable, it fails open:
 * the visitor is never blamed for our lookup failing.
 */
export async function mailDomainError(email) {
  const domain = String(email).split('@')[1] || '';
  const [a, b] = await Promise.all([mxOverHttps(domain), mxOverDns(domain)]);
  if (a === 'yes' || b === 'yes') return '';
  if (a === 'no' || b === 'no') return NO_MAIL;
  return '';
}

/** Milliseconds the visitor spent on the page before this request (sent by the form). */
export const elapsedOf = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
