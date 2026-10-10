# What MANZZA still needs to supply

Generated from `site.config.js` and the photo slots. Run `npm run placeholders` for the live list.

## Contact and configuration (`site.config.js`)

| Key | What's needed |
|---|---|
| `siteUrl` | Live domain, e.g. `https://www.manzza.in` (canonical links, sitemap, Open Graph) |
| `contact.phone` | Sales phone number |
| `contact.email` | Sales email address that receives enquiries |
| `contact.whatsapp` | WhatsApp business number, digits only with country code |
| `contact.address` | Full postal address of the Bengaluru unit |
| `contact.hours` | Office hours (optional; delete the line to hide) |
| `quoteForm.endpoint` | Form endpoint: Formspree URL or `/api/quote` (see README, "Quote form") |
| `capacity.confirmed` | Confirm the indicative **160 MT/month** figure before launch, or set `capacity.show: false` |

## Photographs (`public/images/`)

| File | Where |
|---|---|
| `factory-cnc-line.jpg` | Home page, "How we work" (CNC cutting line) |
| `product-mitre-core.jpg` | Mitre core page |
| `product-ei-laminations.jpg` | E&I page |
| `product-strip-laminations.jpg` | Strip page |

## Please review or confirm

- **Logo source file.** The logo was cut from a screenshot. Please send the original vector or a high-resolution PNG.
- **Materials per product.** The site lists CRGO for mitre core laminations and CRGO or CRNO for E&I and strip laminations (`content/products.json` → `materials`). Please confirm.
- **Application lists** for E&I and strip laminations (`content/products.json` → `applications`). The brief did not specify these, so they are worded generally. Please check they match what you actually supply.
- **Mitre core rating range** "approx. 16 kVA to 16 MVA, subject to design and customer requirements" is shown as given in the brief.
