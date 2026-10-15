/**
 * Email verification for the quote form.
 *   POST { email }               -> emails a 6-digit code, returns { ok, token }
 *   POST { email, token, code }  -> returns { ok } when the code is right
 * Environment: RESEND_API_KEY, QUOTE_FROM_EMAIL, OTP_SECRET (any long random string).
 */
import { businessEmailError } from '../src/lib/email-policy.js';
import { issue, check } from './_otp.js';

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

export async function POST(request) {
  const { RESEND_API_KEY, QUOTE_FROM_EMAIL, OTP_SECRET } = process.env;
  if (!RESEND_API_KEY || !QUOTE_FROM_EMAIL || !OTP_SECRET) return json(500, { ok: false, error: 'Verification is not configured' });

  let body;
  try { body = await request.json(); } catch { return json(400, { ok: false, error: 'Bad request' }); }
  const email = String(body.email || '').trim().toLowerCase();
  const bad = businessEmailError(email);
  if (bad) return json(422, { ok: false, error: bad });

  if (body.token) {
    return check(OTP_SECRET, email, body.token, body.code) ? json(200, { ok: true }) : json(422, { ok: false, error: 'That code is not right or has expired.' });
  }

  const { code, token } = issue(OTP_SECRET, email);
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: QUOTE_FROM_EMAIL,
      to: [email],
      subject: `Your MANZZA verification code: ${code}`,
      html: `<p style="font-family:sans-serif;font-size:15px">Your verification code for the MANZZA quote request is:</p><p style="font-family:sans-serif;font-size:28px;font-weight:700;letter-spacing:6px">${code}</p><p style="font-family:sans-serif;font-size:13px;color:#555">It expires in 10 minutes. If you did not request it, you can ignore this email.</p>`,
    }),
  });
  if (!res.ok) return json(502, { ok: false, error: 'Could not send the code. Please try again.' });
  return json(200, { ok: true, token });
}
