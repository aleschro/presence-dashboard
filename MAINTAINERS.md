# Maintainer Guide — Presence Dashboard

This is the canonical doc for anyone (human or AI assistant) maintaining this
project.

## What this is

A single-file Flask app that drives a LAN-only digital signage dashboard
(Samsung QM43C, mounted in a hallway) showing which of ~200 employees are
currently onsite. Data comes from the MRI OnLocation API. It's an
at-a-glance awareness tool ("who's in the building right now?"), **not** a
safety/evacuation system — OnLocation's own mobile app handles evacuation
headcounts.

Runs on a Windows domain corporate network, LAN-only, with the only
cross-network traffic being outbound HTTPS from the server to the OnLocation
API. No authentication on the dashboard itself — it's a public-facing
display on an internal network, not sensitive data exposed externally.

## Quick start

This project uses `uv` for dependency management.

```bash
uv sync                                                              # install dependencies
uv run flask --app app run --host 0.0.0.0 --port 5000                # run locally
VERBOSE=1 uv run flask --app app run --debug --host 0.0.0.0 --port 5000  # debug + console logging + debug routes
```

Then visit `http://localhost:5000`.

There is no test suite, linter, or formatter configured in this repo.

**Required setup:** create a `.env` file in the project root containing:

```
ONLOCATION_API_KEY=your_key_here
```

The app raises on startup if this is missing
(`os.environ["ONLOCATION_API_KEY"]` in [app.py](app.py)). The key comes from
the company's MRI OnLocation account — ask whoever administers that account
for one if you don't already have it.

**Testing locally outside business hours:** `SCHEDULE` (see Architecture
below) will show the "We're Closed" screen whenever real business hours
don't apply — which is most of the time you'll be developing. Run with
`--debug` and hit `/debug/open` to force the open state, or `/debug/stale`
/ `/debug/fail-next` to exercise the other frontend states, without
waiting on the clock.

## Architecture

Everything lives in [app.py](app.py) — no blueprints, no package structure.

**Background poller → in-memory cache → Flask routes → HTMX-driven frontend.**

- A daemon thread (`_poll_loop`) hits `GET https://api.whosonlocation.com/v1/staff`
  (auth header is `Authorization: APIKEY {key}`, *not* Bearer) once per
  `POLL_INTERVAL` second (currently `1`) and writes the result into a
  module-level `_cache` dict guarded by `_cache_lock`. Routes only ever read
  this cache — they never call the API directly.
- The poller is started once via `_start_poller()`, guarded against Flask's
  reloader double-start (`WERKZEUG_RUN_MAIN` check).
- `_is_open()` gates polling against a hard-coded weekly business-hours
  `SCHEDULE` (Eastern time: Mon–Fri 5 AM–9 PM, Sat 5 AM–1 PM, Sun closed).
  Outside business hours the poller clears the cache and the frontend shows
  a "We're Closed" screen instead of stale data.
- `NAME_OVERRIDES` remaps specific API names to preferred display names —
  this is the place to add new overrides when someone's OnLocation name
  doesn't match what should show on the display.
- `SITE_MARKERS` tags each employee with `site_badge` by substring-matching
  the API's `cur_location` field (their current physical site, distinct from
  `location`, their fixed home site). Only the non-default site gets a
  badge — Military Rd is the default and stays unmarked, `SITE_MARKERS`
  currently only maps `"colvin woods"` → `"CW"`. A third site needs a new
  `(needle, code)` pair here, **plus** a matching count/label added to the
  per-site totals block in `_presence.html` (that part is template-only,
  computed via Jinja `selectattr` on `site_badge` — not backend-driven, so it
  won't pick up a new site automatically).
- Staleness is derived, not polled-for: `_get_cache()` computes `is_stale`
  by comparing `last_success` against `STALE_THRESHOLD` (60s) on every read.

**Color language:** red (`#F4313F`) means "Colvin Woods" and only that — the
`CW` per-row badge, and the site-total numbers turn black instead of green
under the same staleness condition as the main ONSITE number
(`'#000000' if is_stale else '#16a34a'`, repeated per-number rather than
factored out). Grey (`#b2b2b2`) is the default/inactive color (Military Rd
badge column when empty, name-row underlines, "Loading..."). Don't introduce
new colors for future sites without checking with whoever owns the physical
signage — the palette is deliberately restricted to white / black /
`#F4313F` / `#b2b2b2`. Font family is Cronos Pro (see `assets/fonts/`).

**Header layout** (`_presence.html`, top of the `is_open`/`ready` branch):
the ONSITE count, a vertical black divider bar, and the two-row per-site
totals are one flex row, centered together as a single unit — not three
independently positioned elements. The site totals use `grid-cols-[auto_auto]`
(not a fixed-width column) so the number column auto-sizes to content and
the gap around the divider bar stays visually even regardless of digit
count; don't go back to a fixed `w-*` column here, it was tried and made the
divider's spacing look lopsided.

**Routes:**
- `/` — full page (`index.html`)
- `/presence` — HTMX fragment (`_presence.html`) polled by the browser every
  second (`hx-trigger="every 1s"` in `index.html`)
- `/assets/<path>` — serves fonts/logo from `assets/`
- `/debug/*` — only registered when running with `--debug`; used to simulate
  staleness, force closed/open state, or force a 503, for testing the
  frontend's failure states without waiting on real conditions

**Frontend pagination** (`templates/index.html`) is hand-rolled vanilla JS,
not an HTMX/library feature: it measures rendered `<li>` heights against the
viewport to decide how many employees fit per page, builds page divs, and
cycles between them on a timer when there's more than one page. On HTMX
refresh, if multiple pages exist it intercepts `htmx:beforeSwap` and patches
content into the existing paginated DOM in place (`refreshPages`) instead of
letting HTMX replace it, so the visible page doesn't jump. A full rebuild
only happens when the page *count* changes or the viewport resizes.

**What's inside `#presence` vs. outside it matters.** HTMX only
re-fetches/swaps `#presence`'s innerHTML every second
(`hx-trigger="every 1s"`) — that's `_presence.html`'s content (names,
badges, ONSITE/site-total counts, staleness). Anything living outside that
div in `index.html` (the logo, `#page-indicator`, the `<script>` blocks
themselves) is only ever rendered once, on initial page load. A browser tab
that's been open since before a deploy will keep showing the *old* static
chrome indefinitely even though the live data inside `#presence` looks
perfectly current — this bit a real TV once (missing logo after a deploy)
before the nightly-reload fix below existed. When changing anything in
`index.html` itself (as opposed to `_presence.html`), remember every open
display needs an actual page reload to pick it up.

**Static corner chrome is all `position: fixed`, not `absolute`.** The logo
(top-left), `#page-indicator` (bottom-left), and the stale/connection-lost
warning (bottom-right, both the server-rendered span in `_presence.html` and
the JS-created fallback in `showConnectionLost()`) all anchor to the
*viewport* corners rather than to `#presence`'s own `max-w-screen-2xl`-capped
container. This was a deliberate fix — anchoring to the capped container
left less room than the full viewport and caused visible overlap with the
centered ONSITE/site-totals row once that row's font size grew. If you're
adding another corner element, anchor it the same way.

**Nightly reload:** the last `<script>` block in `index.html` does a single
`setTimeout` to the next occurrence of 2 AM local time, then
`location.reload()`. Since a reload re-runs the script and recomputes
"tomorrow at 2 AM," this repeats forever without a `setInterval`. It exists
specifically to self-heal the "stale static chrome" problem above without
needing someone to manually refresh every display. 2 AM was picked because
it's outside `SCHEDULE` every day of the week, including Saturday's shorter
hours and Sunday's full closure. It relies on each display's own system
clock/timezone being correct (assumed Eastern, matching `SCHEDULE`) — not
verified against the server.

## OnLocation API reference

- Docs: https://apidocs.whosonlocation.com/ (fuller reference PDFs are kept
  in `docs/`)
- Base URL: `https://api.whosonlocation.com/v1`
- Auth header: `Authorization: APIKEY {key}` — **not** `Bearer`. This is the
  single most common new-mistake source; OnLocation returns a 400 if you
  send Bearer.
- Endpoint used: `GET /v1/staff` — returns a list of employee dicts directly
  (app.py defensively unwraps `{data: [...]}`/`{staff: [...]}`/
  `{employees: [...]}` shapes too, in case that ever changes).
- Rate limit: 100 requests/minute per API key. At `POLL_INTERVAL = 1`, this
  app is already polling every second — don't lower it further without
  checking this limit.
- Fields actually used by this app: `name`, `onsite_status`
  (`"onsite"`/`"offsite"`), `cur_location` (current physical site — used for
  `site_badge`), `location` (fixed home site, not currently displayed).
  Other fields exist (email, department, employee_id, mobile) but aren't
  used.
- `docs/mri-openapi-spec.json` has the full schema if you need to check a
  field shape that isn't covered above — the `/staff` endpoint definition
  starts at line 7570, and the `StaffListResponse` schema (every field
  you'll actually get back) is at line 13443.

## Deployment

Production runs on a Windows Server VM behind **IIS** acting as a reverse
proxy via **HttpPlatformHandler v1.2**, forwarding port **5001** to a local
Flask process on `127.0.0.1`. HttpPlatformHandler owns the Python process
lifecycle — it spawns and monitors it, not a Windows service.

**Environment specifics:**
- Application root: `C:\OnLocation\presence-dashboard\`
- Python path: `C:\Program Files\Python314\python.exe`
- IIS site: `PresenceDashboard`, app pool: `PresenceDashboardPool`, identity
  `ApplicationPoolIdentity` (needs "Modify" permission on the app root to
  write log files)
- App pool settings: Start Mode `AlwaysRunning`, Preload `True`, Idle
  Timeout `0` — together these make the app start on boot and never spin
  down from inactivity.
- `web.config` injects env vars into the Python process: `FLASK_APP=app.py`,
  `ONLOCATION_API_KEY={key}`, `VERBOSE=1` (streams app logic to
  stdout/`flask.log` for debugging).

**Two log files, different purposes:**
- `flask.log` — stdout, captures the IIS↔Python handshake and startup
  tracebacks. Check here first if the app won't start after a deploy.
- `app.log` — the app's own logging (poller activity, API success/failure).
  Check here for runtime behavior once the app is confirmed running.

**`git pull` on the VM is not enough on its own.** The app pool needs an
explicit recycle before code changes take effect (IIS Manager →
Application Pools → `PresenceDashboardPool` → Recycle, or
`Restart-WebAppPool -Name "PresenceDashboardPool"`). Because
`AlwaysRunning`/Preload are set, the process respawns immediately rather
than waiting for the next request.

## Architecture decisions (why, not just what)

- **Flask + HTMX over anything heavier**, and specifically over the
  ASP.NET stack already running on the same IIS box, because the original
  author could read Python and had zero C# experience — not a technical
  requirement, a team-capability one. If the next maintainer is
  C#-comfortable and Python-averse, a rewrite isn't sacred, but note the IIS
  deployment pattern above would need to change too.
- **Polling over webhooks**, deliberately: polling needs zero inbound
  firewall rules (everything is outbound HTTPS from the server to
  OnLocation), works fine on a standard corporate network, and OnLocation's
  webhook setup would have required a publicly reachable HTTPS endpoint.
  See `docs/` for vendor webhook docs if this is ever revisited.
- **In-memory cache, no database.** Scale is ~200 employees and the data is
  fully disposable/re-fetchable every second — persistence would add
  complexity with no benefit. If this ever needs historical tracking
  ("who was here last Tuesday"), that's a real architecture change, not a
  tweak.

## Reference material

`docs/` holds vendor/API reference material: `test_onlocation_api.py` (a
standalone script for manually testing API key/auth against the OnLocation
endpoint), `mri-openapi-spec.json` (full API schema), vendor PDFs on
OnLocation's dashboard product and webhooks, and a sample report export.
