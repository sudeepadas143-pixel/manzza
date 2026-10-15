/**
 * Stateless email one-time codes. The code itself is never stored: the server
 * returns a token = email|expiry|HMAC(email|expiry|code), signed with OTP_SECRET.
 * To verify, the client sends the token back with the code it received by email
 * and the HMAC is recomputed. Codes expire after 10 minutes.
 */
import crypto from 'node:crypto';

const TTL_MS = 10 * 60 * 1000;

const sign = (secret, s) => crypto.createHmac('sha256', secret).update(s).digest('base64url');

export function issue(secret, email) {
  const code = String(crypto.randomInt(0, 1_000_000)).padStart(6, '0');
  const exp = Date.now() + TTL_MS;
  const e = email.trim().toLowerCase();
  const token = Buffer.from(`${e}|${exp}|${sign(secret, `${e}|${exp}|${code}`)}`).toString('base64url');
  return { code, token };
}

/** true when token+code prove control of `email` and have not expired. */
export function check(secret, email, token, code) {
  try {
    const [e, exp, mac] = Buffer.from(String(token), 'base64url').toString().split('|');
    if (e !== String(email).trim().toLowerCase()) return false;
    if (!(Number(exp) > Date.now())) return false;
    const want = sign(secret, `${e}|${exp}|${String(code).trim()}`);
    return mac.length === want.length && crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(want));
  } catch { return false; }
}
