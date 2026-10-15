/**
 * Business-email policy for the quote form, shared by the browser (src/js/quote.js)
 * and the server (api/). Personal mailbox providers are refused so enquiries come
 * from a company domain. Add domains here if new free providers turn up.
 */
export const FREE_EMAIL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.in', 'yahoo.in', 'ymail.com', 'rocketmail.com',
  'outlook.com', 'outlook.in', 'hotmail.com', 'hotmail.co.in', 'live.com', 'live.in', 'msn.com',
  'icloud.com', 'me.com', 'mac.com', 'aol.com', 'proton.me', 'protonmail.com', 'pm.me',
  'rediffmail.com', 'rediff.com', 'yandex.com', 'yandex.ru', 'gmx.com', 'gmx.net', 'mail.com',
  'zohomail.com', 'zohomail.in', 'tutanota.com', 'tuta.io', 'hey.com', 'fastmail.com',
  'mail.ru', 'inbox.com', 'qq.com', '163.com', '126.com', 'sify.com', 'indiatimes.com',
]);

/** Throwaway inbox services: an address that disappears in minutes is not a buyer. */
export const DISPOSABLE_DOMAINS = new Set([
  'mailinator.com', 'mailinator.net', 'guerrillamail.com', 'guerrillamail.net', 'guerrillamailblock.com', 'sharklasers.com',
  'grr.la', 'pokemail.net', 'spam4.me', '10minutemail.com', '10minutemail.net', '20minutemail.com', 'tempmail.com',
  'temp-mail.org', 'temp-mail.io', 'tempmail.net', 'tempmailo.com', 'tempail.com', 'tempr.email', 'throwawaymail.com',
  'yopmail.com', 'yopmail.net', 'yopmail.fr', 'getnada.com', 'nada.email', 'dispostable.com', 'maildrop.cc',
  'mailnesia.com', 'trashmail.com', 'trashmail.de', 'trash-mail.com', 'fakeinbox.com', 'mintemail.com', 'mohmal.com',
  'emailondeck.com', 'spamgourmet.com', 'mytemp.email', 'moakt.com', 'burnermail.io', 'inboxkitten.com', 'mailpoof.com',
  'discard.email', 'emailfake.com', 'fakemail.net', 'luxusmail.org', 'tmpmail.org', 'tmpmail.net', 'minuteinbox.com',
  'harakirimail.com', 'getairmail.com', 'mailcatch.com', 'spambox.us', 'incognitomail.org', 'anonaddy.me', 'duck.com',
]);

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** '' when the address is an acceptable business email, otherwise the reason.
 *  `allow`: addresses accepted even on a personal domain (testing, OTP_TEST_EMAILS). */
export function businessEmailError(email, allow = []) {
  const e = String(email || '').trim().toLowerCase();
  if (!EMAIL_RE.test(e)) return 'Please enter a valid email address, for example name@company.com.';
  if (allow.includes(e)) return '';
  const domain = e.split('@')[1];
  if (FREE_EMAIL_DOMAINS.has(domain)) return 'Please use your company email address. Personal addresses (Gmail, Yahoo, Outlook and similar) are not accepted.';
  if (DISPOSABLE_DOMAINS.has(domain) || [...DISPOSABLE_DOMAINS].some((d) => domain.endsWith(`.${d}`))) return 'Please use your company email address. Temporary inboxes are not accepted.';
  return '';
}

/** Bots fill a form in a second or two; nobody reads, picks a product and types a quantity that fast. */
export const MIN_FILL_MS = { code: 2500, submit: 8000 };

/** '' when the free-text fields read like an enquiry, otherwise the reason. Spam is mostly links. */
export function spamTextError(form) {
  const links = (v) => (String(v || '').match(/https?:\/\/|www\.|\[url|<a\s/gi) || []).length;
  for (const k of ['company', 'contact_person', 'phone', 'quantity', 'order_frequency', 'grade', 'thickness', 'rating_or_application']) {
    if (links(form.get(k))) return 'Please remove web links from the form fields.';
  }
  if (links(form.get('notes')) > 2) return 'Please keep links in your notes to two at most, or attach a drawing instead.';
  return '';
}

/** OTP_TEST_EMAILS: comma-separated addresses allowed through the business-email rule (server only). */
export const testEmails = (env) => String(env.OTP_TEST_EMAILS || '').split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
