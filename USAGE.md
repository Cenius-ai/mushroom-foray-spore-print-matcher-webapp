# Using the app

Start it with `python3 app.py` and open <http://localhost:7860>. Everything below describes the
running product, top to bottom.

## 1. Sign in

The front door is a centred sign-in card served at `/` (and at `/login`) for anyone who is not
signed in; signed-in visitors land straight on the Matcher tab.

- Sign in with the demo account: **cenius@cenius.ai / cenius** (username `cenius` works too), or the
  second seeded account **demo / demo1234**. Both are printed on the card, each owns the same seeded
  foray history, and the **Fill demo credentials** button types the first pair for you.
- **Show / Hide** toggles the password field between masked and readable text.
- **Create account** switches the same card into registration mode: usernames are 3–30 characters
  (letters, numbers, dot, dash, underscore) and passwords need at least 8 characters.
- A failed sign-in always says **“Username or password is incorrect”** — never whether the username
  exists.
- The session is a signed HttpOnly cookie, so a page reload keeps you signed in. **Sign out** lives
  in the top-right of the app header.

## 2. Matcher tab

**Step 1 — the spore print photo.** A reference print is already loaded so the tab is useful on the
first paint: the result card shows the matched swatch, its hex chip, delta-E, the measured print
colour and a confidence percentage. Upload your own JPEG or PNG (up to 5 MB) to replace it — the
card re-renders with the new match. A non-image or oversized file shows a red banner and **keeps the
previous result on screen**. **Clear photo** empties the card and disables Save until you upload
again.

**Step 2 — measurements.** Drag **Cap diameter (mm)** (5–300) and **Gill spacing (mm)** (0.5–30).
The score card updates inside the same interaction, with no submit button:

- a 0–100 warning score and a risk band pill (low / moderate / high),
- two factor sentences: the cap contribution (`0.55` weight) and the gill-crowding contribution
  (`0.45` weight), each with the factor value, weight and points,
- the permanent **“Heuristic only — never eat based on this tool”** disclaimer.

**Step 3 — save to foray.** Pick the target session, write a habitat note (for example
“Pine duff under Scots pine”) and press **Save find to foray**. A toast confirms the write and the
banner names the session, swatch, confidence and risk band. The find is persisted to SQLite, so it
survives a reload, and it appears immediately on the Foray tab and in the Dashboard charts.

## 3. Foray tab

- The rail on the left lists every session you own with its finding count. Click one to load its
  finds.
- **New foray session**: type a name and press **Create foray session** (or Enter). Duplicate names
  are refused with a message; a brand-new account sees “Create your first foray session to start
  logging finds”.
- The table on the right lists each find: swatch name + hex chip + thumbnail, confidence, habitat,
  cap ⌀, gill spacing, risk band and when it was logged (humanised: “2 days ago”, then a date).
- A session with no finds yet shows an invitation to save one from the Matcher tab.

## 4. Dashboard tab

- The **session filter** (top right) scopes every panel to one foray, or “All sessions”.
- The KPI strip counts finds, mean confidence, high-risk finds and how many of the six swatch
  classes the selection covers.
- Four charts, all fed by `GET /api/dashboard`: finds per swatch class, a confidence histogram,
  risk-band counts and a cap-diameter vs gill-spacing scatter coloured by risk band. A colour key
  under the KPIs shows the six swatch hexes.
- Choosing a session with no finds hides the charts and shows “No finds in this session yet”
  instead of empty axes.

## Ownership and privacy

Foray sessions and findings belong to the account that created them. Every read and write is scoped
to the signed-in user: requesting someone else's session id returns **404**, exactly as if it did not
exist, and nothing is written. Stored spore-print images are served through `/media/{file}`, which
answers only to the owner of a find that references that file.

## Data and reset

Everything lives in `foray.db` next to the app plus the photos in `uploads/`. To start over:

```bash
rm -f foray.db && python3 seed.py
```
