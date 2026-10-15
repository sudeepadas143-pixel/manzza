/**
 * Request-a-Quote form: validation, honeypot, file checks, submission to the
 * endpoint configured in site.config.js (quoteForm.endpoint), success state.
 */
import './main.js';
import { businessEmailError, EMAIL_RE } from '../lib/email-policy.js';

const form = document.getElementById('quote-form');
const done = document.getElementById('quote-done');

if (form) {
  const status = form.querySelector('.qform__status');
  const submitBtn = form.querySelector('button[type="submit"]');
  const fileInput = form.querySelector('#f-file');
  const fileName = form.querySelector('[data-file-name]');
  const drop = form.querySelector('.drop');
  const endpoint = form.dataset.endpoint;
  const maxBytes = (Number(form.dataset.maxMb) || 10) * 1024 * 1024;
  const otpEndpoint = form.dataset.otp;

  // Pre-select product from ?product=slug (product pages link here)
  const pre = new URLSearchParams(location.search).get('product');
  if (pre) {
    const r = form.querySelector(`input[name="product"][value="${CSS.escape(pre)}"]`);
    if (r) r.checked = true;
  }

  const messages = {
    company: 'Please enter your company name.',
    contact_person: 'Please enter the name of the person we should contact.',
    email: 'Please enter a valid email address, for example name@company.com.',
    phone: 'Please enter a phone number we can reach you on.',
    product: 'Please choose a product.',
    material: 'Please choose CRGO or CRNO.',
    quantity: 'Please give an estimated quantity.',
  };

  function fieldWrap(el) { return el.closest('.field'); }

  function setError(name, msg) {
    const els = form.querySelectorAll(`[name="${name}"]`);
    const wrap = fieldWrap(els[0]);
    if (!wrap) return;
    let err = wrap.querySelector('.err');
    if (msg) {
      if (!err) {
        err = document.createElement('p');
        err.className = 'err';
        err.id = `err-${name}`;
        wrap.appendChild(err);
      }
      err.textContent = msg;
      wrap.classList.add('has-error');
      els.forEach((el) => { el.setAttribute('aria-invalid', 'true'); el.setAttribute('aria-errormessage', err.id); });
    } else {
      if (err) err.remove();
      wrap.classList.remove('has-error');
      els.forEach((el) => { el.removeAttribute('aria-invalid'); el.removeAttribute('aria-errormessage'); });
    }
  }

  function validateField(name) {
    const els = [...form.querySelectorAll(`[name="${name}"]`)];
    if (!els.length) return true;
    if (els[0].type === 'radio') {
      const ok = els.some((e) => e.checked);
      setError(name, ok ? '' : messages[name]);
      return ok;
    }
    const el = els[0];
    if (name === 'email') {
      // with verification on, the server has the final say on personal domains (it may
      // allow test addresses); here only flag them once it has refused, via the send step
      const bad = otpEndpoint
        ? (EMAIL_RE.test(el.value.trim().toLowerCase()) ? '' : businessEmailError(el.value))
        : businessEmailError(el.value);
      setError(name, bad);
      return !bad;
    }
    let ok = el.checkValidity() && !(el.required && !el.value.trim());
    if (ok && el.type === 'tel') ok = (el.value.match(/\d/g) || []).length >= 7;
    setError(name, ok ? '' : messages[name] || 'Please check this field.');
    return ok;
  }

  function validateFile() {
    const f = fileInput.files[0];
    if (f && f.size > maxBytes) {
      setError('drawing', 'This file is too large to send through the form. Please email the drawing to us instead, or send a smaller PDF.');
      return false;
    }
    setError('drawing', '');
    return true;
  }

  const required = Object.keys(messages);
  required.forEach((name) => {
    form.querySelectorAll(`[name="${name}"]`).forEach((el) => {
      el.addEventListener(el.type === 'radio' ? 'change' : 'blur', () => validateField(name));
      el.addEventListener('input', () => { if (fieldWrap(el)?.classList.contains('has-error')) validateField(name); });
    });
  });

  // File input: show name, drag and drop
  const showFile = () => {
    const f = fileInput.files[0];
    fileName.textContent = f ? `${f.name} (${(f.size / 1024 / 1024).toFixed(1)} MB)` : '';
    drop.classList.toggle('has-file', !!f);
    validateFile();
  };
  fileInput.addEventListener('change', showFile);
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('is-drag'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('is-drag'); }));
  drop.addEventListener('drop', (e) => {
    if (e.dataTransfer?.files?.length) { fileInput.files = e.dataTransfer.files; showFile(); }
  });

  // ---- business email verification (one-time code by email)
  const emailEl = form.querySelector('#f-email');
  const sendBtn = form.querySelector('[data-otp-send]');
  const step = form.querySelector('[data-otp-step]');
  const codeEl = form.querySelector('#f-otp');
  const checkBtn = form.querySelector('[data-otp-check]');
  const okNote = form.querySelector('[data-otp-ok]');
  const tokenEl = form.querySelector('[name="otp_token"]');
  let verifiedFor = '';
  const isVerified = () => !otpEndpoint || (verifiedFor && verifiedFor === emailEl.value.trim().toLowerCase());
  const setBusy = (btn, busy, label) => { btn.disabled = busy; btn.textContent = label; };

  async function post(body) {
    const res = await fetch(otpEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const out = await res.json().catch(() => ({}));
    if (!res.ok || !out.ok) throw new Error(out.error || 'Something went wrong. Please try again.');
    return out;
  }

  if (!otpEndpoint) { sendBtn.hidden = true; }
  sendBtn.addEventListener('click', async () => {
    if (!validateField('email')) { emailEl.focus(); return; }
    setBusy(sendBtn, true, 'Sending…');
    try {
      const out = await post({ email: emailEl.value });
      tokenEl.value = out.token;
      step.hidden = false;
      codeEl.value = '';
      codeEl.focus();
      setError('email', '');
      setBusy(sendBtn, false, 'Resend code');
    } catch (err) {
      setError('email', err.message);
      setBusy(sendBtn, false, 'Send code');
    }
  });
  checkBtn.addEventListener('click', async () => {
    if (!/^\d{6}$/.test(codeEl.value.trim())) { setError('email', 'Enter the 6-digit code from the email.'); codeEl.focus(); return; }
    setBusy(checkBtn, true, 'Checking…');
    try {
      await post({ email: emailEl.value, token: tokenEl.value, code: codeEl.value });
      verifiedFor = emailEl.value.trim().toLowerCase();
      step.hidden = true;
      okNote.hidden = false;
      sendBtn.hidden = true;
      setError('email', '');
    } catch (err) {
      setError('email', err.message);
    } finally { setBusy(checkBtn, false, 'Verify'); }
  });
  codeEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); checkBtn.click(); } });
  emailEl.addEventListener('input', () => {
    if (verifiedFor && emailEl.value.trim().toLowerCase() !== verifiedFor) {
      verifiedFor = ''; okNote.hidden = true; sendBtn.hidden = !otpEndpoint; setBusy(sendBtn, false, 'Send code'); tokenEl.value = '';
    }
  });

  function say(msg, kind = 'info') {
    status.textContent = msg;
    status.dataset.kind = kind;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    say('');
    const results = required.map(validateField);
    const fileOk = validateFile();
    if (results.includes(false) || !fileOk) {
      const first = form.querySelector('[aria-invalid="true"]');
      say('Please check the highlighted fields.', 'error');
      first?.focus();
      return;
    }

    if (!isVerified()) {
      setError('email', 'Please verify your email address: press Send code and enter the code we email you.');
      say('Please verify your business email before sending.', 'error');
      emailEl.focus();
      return;
    }

    // Honeypot: bots fill every field. Pretend success, send nothing.
    if (form.querySelector('[name="company_website"]').value) { showDone(); return; }

    const data = new FormData(form);
    data.delete('company_website');
    data.append('_subject', `Quote request: ${data.get('product')} – ${data.get('company')}`);
    data.append('page', location.href);

    if (!endpoint) {
      const local = ['localhost', '127.0.0.1'].includes(location.hostname) || location.hostname.endsWith('.local');
      if (local) {
        console.info('[quote] No endpoint configured (site.config.js → quoteForm.endpoint). Simulating success locally.', Object.fromEntries(data));
        showDone();
      } else {
        say('Online submission is not connected yet. Please email us using the address on this page.', 'error');
      }
      return;
    }

    submitBtn.disabled = true;
    submitBtn.classList.add('is-busy');
    submitBtn.querySelector('.btn__label').textContent = 'Sending…';
    try {
      const res = await fetch(endpoint, { method: 'POST', body: data, headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showDone();
    } catch (err) {
      console.warn('[quote] submit failed', err);
      say('Sorry, your request could not be sent. Please try again, or email us.', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('is-busy');
      submitBtn.querySelector('.btn__label').textContent = 'Send request';
    }
  });

  function showDone() {
    form.hidden = true;
    done.hidden = false;
    done.focus();
    done.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  }

  done.querySelector('[data-again]')?.addEventListener('click', () => {
    form.reset();
    verifiedFor = ''; okNote.hidden = true; step.hidden = true; sendBtn.hidden = !otpEndpoint; setBusy(sendBtn, false, 'Send code');
    showFile();
    say('');
    done.hidden = true;
    form.hidden = false;
    form.querySelector('input:not([type=hidden])')?.focus();
  });
}
