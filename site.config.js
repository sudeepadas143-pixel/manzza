/**
 * MANZZA – site configuration
 * ---------------------------------------------------------------------------
 * This is the ONE place for contact details, the quote-form endpoint and the
 * indicative capacity figure. Every page reads from here at build time.
 *
 * Anything wrapped in TODO('…') is a placeholder that still has to be filled
 * in by MANZZA. Placeholders never appear on the site as fake numbers: the
 * page shows a neutral "to be confirmed" note instead, and the build prints
 * a list of what is still missing (or run:  npm run placeholders).
 *
 * To fill one in, replace the whole TODO('…') call with the real value, e.g.
 *   phone: '+91 80 1234 5678',
 */

const TODO = (note) => ({ __todo: true, note });

export default {
  company: {
    legalName: 'MANZZA Industry Pvt. Ltd.',
    shortName: 'MANZZA',
    tagline: 'Engineered for Power.',
    subline: 'Precision. Performance. Power.',
    city: 'Bengaluru',
    state: 'Karnataka',
    country: 'IN',
    serviceRegions: ['Karnataka', 'Andhra Pradesh', 'Telangana', 'Tamil Nadu'],
  },

  // Public URL of the live site, without a trailing slash.
  // Used for canonical links, Open Graph tags, sitemap.xml and JSON-LD.
  siteUrl: 'https://manzza-website.vercel.app', // change to the custom domain when there is one

  contact: {
    // Shown in the footer and on /quote. Use international format.
    phone: '+91 81056 67729',
    // Business email that receives enquiries.
    email: 'office@manzza.in',
    // WhatsApp number: digits only, with country code, no + or spaces.
    // e.g. '919876543210'
    whatsapp: TODO('WhatsApp business number, digits only with country code'),
    // Factory / office address, one line per array item.
    address: ['Bommasandra Industrial Area', 'Bengaluru, Karnataka'],
    // Optional: office hours, e.g. 'Mon–Sat, 9:00–18:00'
    hours: TODO('Office hours (optional; delete this line to hide)'),
  },

  quoteForm: {
    // Where the quote form is POSTed (multipart/form-data, with file upload).
    // Formspree:  'https://formspree.io/f/xxxxxxxx'
    // Vercel fn:  '/api/quote'   (see api/quote.js and the README)
    endpoint: TODO('Form endpoint URL – see README "Quote form"'),
    // Largest drawing file the form will accept, in megabytes.
    // Keep at 4 with the Vercel function (Vercel caps request bodies at ~4.5 MB).
    // With Formspree, check your plan's upload limit.
    maxFileMB: 4,
  },

  // ---------------------------------------------------------------------------
  // INDICATIVE CAPACITY – please confirm before launch.
  // Shown once on the home page with the note below. Set `show: false` to hide.
  // ---------------------------------------------------------------------------
  capacity: {
    show: true,
    value: 'Production capacity 160',
    unit: 'metric tonnes per month',
    note: '',
    confirmed: true, // 160 MT/month per the client content brief
  },
};
