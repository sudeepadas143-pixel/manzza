/**
 * Optional Vercel serverless function for the quote form.
 *
 * Use it instead of Formspree by setting, in site.config.js:
 *   quoteForm: { endpoint: '/api/quote', ... }
 * and adding these Environment Variables in the Vercel project settings:
 *   RESEND_API_KEY    – API key from https://resend.com (free tier is enough)
 *   QUOTE_TO_EMAIL    – where enquiries go, e.g. sales@yourdomain.in
 *   QUOTE_FROM_EMAIL  – a sender on a domain verified in Resend,
 *                       e.g. "MANZZA website <website@yourdomain.in>"
 *
 * Vercel limits request bodies to about 4.5 MB, so keep quoteForm.maxFileMB at 4.
 */

const FIELDS = [
  ['company', 'Company'],
  ['contact_person', 'Contact person'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['product', 'Product'],
  ['material', 'Material'],
  ['thickness', 'Thickness (mm)'],
  ['grade', 'Grade'],
  ['rating_or_application', 'Rating / application'],
  ['quantity', 'Estimated quantity'],
  ['order_frequency', 'Order frequency'],
  ['notes', 'Additional requirements'],
  ['page', 'Sent from'],
];

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

export async function POST(request) {
  const { RESEND_API_KEY, QUOTE_TO_EMAIL, QUOTE_FROM_EMAIL } = process.env;
  if (!RESEND_API_KEY || !QUOTE_TO_EMAIL || !QUOTE_FROM_EMAIL) return json(500, { ok: false, error: 'Email is not configured' });

  let form;
  try { form = await request.formData(); } catch { return json(400, { ok: false, error: 'Bad form data' }); }

  // Honeypot: real visitors never fill this field.
  if (form.get('company_website')) return json(200, { ok: true });

  for (const k of ['company', 'contact_person', 'email', 'phone', 'product', 'material', 'quantity']) {
    if (!String(form.get(k) || '').trim()) return json(422, { ok: false, error: `Missing ${k}` });
  }
  const email = String(form.get('email'));
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json(422, { ok: false, error: 'Invalid email' });

  const rows = FIELDS.map(([k, label]) => {
    const v = String(form.get(k) || '').trim();
    return v ? `<tr><th align="left" style="padding:6px 12px 6px 0;vertical-align:top">${esc(label)}</th><td style="padding:6px 0">${esc(v).replace(/\n/g, '<br>')}</td></tr>` : '';
  }).join('');

  const attachments = [];
  const file = form.get('drawing');
  if (file && typeof file === 'object' && file.size > 0) {
    const buf = Buffer.from(await file.arrayBuffer());
    attachments.push({ filename: file.name || 'drawing', content: buf.toString('base64') });
  }

  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: QUOTE_FROM_EMAIL,
      to: QUOTE_TO_EMAIL.split(',').map((s) => s.trim()),
      reply_to: email,
      subject: `Quote request: ${form.get('product')} – ${form.get('company')}`,
      html: `<h2 style="font-family:sans-serif">New quote request</h2><table style="font-family:sans-serif;font-size:14px">${rows}</table>${attachments.length ? '<p style="font-family:sans-serif">Drawing attached.</p>' : ''}`,
      attachments,
    }),
  });
  if (!res.ok) return json(502, { ok: false, error: 'Could not send email' });
  return json(200, { ok: true });
}
