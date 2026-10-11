/**
 * Worst-case data for the break-ui check (dev only).
 * Open any page on the dev server with ?data=worst to render it with these
 * values in place of the ones in site.config.js. Every value is something
 * MANZZA could realistically enter: long Indian industrial addresses, two
 * phone numbers in one field, a long departmental email, a long hours note.
 * Nothing here ever reaches a production build.
 */
export default {
  contact: {
    phone: '+91 80 2783 4410 / +91 98450 12345',
    email: 'enquiries.transformer-laminations@manzzaindustries-bengaluru.co.in',
    whatsapp: '919845012345',
    address: [
      'Plot No. 147/B, 3rd Cross, KIADB Industrial Area, Bommasandra–Jigani Link Road',
      'Anekal Taluk, Bengaluru Urban District',
      'Karnataka 562106, India',
    ],
    hours: 'Monday to Saturday, 9:00 am – 6:00 pm (closed on second Saturdays and public holidays)',
  },
  quoteForm: { endpoint: '/api/quote', maxFileMB: 4 },
  capacity: { value: 'Up to 1,250', confirmed: true },
};
