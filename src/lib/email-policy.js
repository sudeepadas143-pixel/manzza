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

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** '' when the address is an acceptable business email, otherwise the reason.
 *  `allow`: addresses accepted even on a personal domain (testing, OTP_TEST_EMAILS). */
export function businessEmailError(email, allow = []) {
  const e = String(email || '').trim().toLowerCase();
  if (!EMAIL_RE.test(e)) return 'Please enter a valid email address, for example name@company.com.';
  if (allow.includes(e)) return '';
  const domain = e.split('@')[1];
  if (FREE_EMAIL_DOMAINS.has(domain)) return 'Please use your company email address. Personal addresses (Gmail, Yahoo, Outlook and similar) are not accepted.';
  return '';
}

/** OTP_TEST_EMAILS: comma-separated addresses allowed through the business-email rule (server only). */
export const testEmails = (env) => String(env.OTP_TEST_EMAILS || '').split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
