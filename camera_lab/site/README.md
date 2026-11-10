# Vision Lab website

Live object detection, a line counter and image processing that run in the browser, with optional Google AdSense
ad slots. A static site: no server, no build step. Hosted free on GitHub Pages at <https://daniel766hi.github.io/>.

| File | What it is |
|---|---|
| `index.html`, `app.js` | the lab: camera or photo; tools: detect & count (with CSV log), privacy blur, motion map, QR scanner, colour palette, colour measure, histogram, edges, filters, cartoon; record clip |
| `guide.html`, `about.html`, `privacy.html` | content pages (AdSense reviews these; a privacy policy is required) |
| `style.css` | shared styles (light and dark) |
| `config.js` | **your AdSense publisher ID goes here** |
| `ads.js` | fills the ad slots once an ID is set; hides them otherwise |
| `models/coco/` | COCO-SSD lite MobileNet v2 weights (TensorFlow.js, Apache 2.0) |
| `samples/`, `guide/`, `og.png` | sample photos, guide figures, link-preview image |

## Put it online (free)

1. Create a **public** repository named exactly `Daniel766hi.github.io` (github.com/new).
   Using that name puts the site at the root of `daniel766hi.github.io`, which is where AdSense looks for `ads.txt`.
2. Push these files to its `main` branch.
3. Repository **Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / `(root)` → Save**.
   The site is live a minute or two later at <https://daniel766hi.github.io/>.

The camera only works over HTTPS, which GitHub Pages provides.

## Turn on ads (Google AdSense)

1. Sign up at <https://adsense.google.com> with a Google account (you must be 18+). Add the site
   `daniel766hi.github.io` and fill in your payment country and address.
2. Copy your publisher ID (`ca-pub-` followed by 16 digits; it is public, not a secret) into `config.js`:
   `ADSENSE_CLIENT: "ca-pub-1234567890123456"`.
3. Create a file `ads.txt` next to `index.html` with exactly one line, using your ID's digits:
   `google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0`
4. Push. In AdSense, tick "I've placed the code" and request review. Review takes from days to a few weeks.
5. In AdSense **Privacy & messaging**, publish the free European consent message (required to show ads to
   visitors from the EEA, the UK and Switzerland).
6. Optional: turn on **Auto ads** to let Google add more placements, or create display ad units and paste their
   slot IDs into `SLOTS` in `config.js` to fill the 4 fixed slots on the lab page (`top`, `side`, `inline`, `footer`).

Until an ID is set, the slots are hidden and the site looks finished without them.

**Approval is not guaranteed on a `github.io` address.** `github.io` is GitHub's domain, not yours, and AdSense
sometimes rejects shared-domain sites or asks for a site with more original content. If that happens, the usual
fix is a custom domain (about USD 10 a year; GitHub Pages supports it for free under Settings → Pages → Custom
domain) and re-applying. More written content (more guide articles) also helps.

Do not click your own ads or ask others to: AdSense bans accounts for invalid clicks.

## Test locally

```
python -m http.server 8000      # then open http://localhost:8000
```

`localhost` counts as secure, so the camera works there too.
