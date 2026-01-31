import os
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from pathlib import Path

from flask import Flask, abort, render_template, send_from_directory

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = Path(__file__).resolve().parent / "app.log"
_log_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_root = logging.getLogger()
_root.setLevel(logging.INFO)

# Always write to file
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(_log_fmt)
_root.addHandler(_file_handler)

# Console output when VERBOSE=1 is set (for development)
if os.environ.get("VERBOSE") == "1":
    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_log_fmt)
    _root.addHandler(_console_handler)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ["ONLOCATION_API_KEY"]
API_URL = "https://api.whosonlocation.com/v1/staff"
POLL_INTERVAL = 1           # seconds between API polls
STALE_THRESHOLD = 60        # seconds before data is considered stale

# Business hours schedule (Eastern)
TIMEZONE = ZoneInfo("America/New_York")
SCHEDULE = {
    0: (5, 21),  # Mon  5 AM – 9 PM
    1: (5, 21),  # Tue
    2: (5, 21),  # Wed
    3: (5, 21),  # Thu
    4: (5, 21),  # Fri
    5: (5, 13),  # Sat  5 AM – 1 PM
    # Sun: absent = closed
}

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_cache = {
    "employees": [],         # list of dicts from the API
    "last_success": None,    # datetime (UTC) of last successful poll
    "ready": False,          # True after first successful poll
}

# Debug-only flags (used by /debug/* routes when app.debug is True)
_debug_flags = {
    "pause_poller": False,       # skip API polling when True
    "fail_next_presence": False, # return 503 on next /presence request
    "force_closed": False,       # override schedule to force closed state
    "force_open": False,         # override schedule to force open state
}


def _is_open():
    """Check if current time is within business hours."""
    if _debug_flags["force_closed"]:
        return False
    if _debug_flags["force_open"]:
        return True
    now = datetime.now(TIMEZONE)
    hours = SCHEDULE.get(now.weekday())
    if hours is None:
        return False
    open_hour, close_hour = hours
    return open_hour <= now.hour < close_hour


def _get_cache():
    """Return a snapshot of the cache (thread-safe read)."""
    with _cache_lock:
        is_stale = False
        if _cache["last_success"] is not None:
            age = (datetime.now(timezone.utc) - _cache["last_success"]).total_seconds()
            is_stale = age > STALE_THRESHOLD
        return {
            "employees": list(_cache["employees"]),
            "ready": _cache["ready"],
            "is_stale": is_stale,
            "is_open": _is_open(),
        }


# ---------------------------------------------------------------------------
# API polling
# ---------------------------------------------------------------------------
logger = logging.getLogger("poller")


def _fetch_staff():
    """Hit the OnLocation /staff endpoint and return the employee list."""
    headers = {
        "Authorization": f"APIKEY {API_KEY}",
        "Accept": "application/json",
    }
    resp = requests.get(API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # The API returns a list directly, but handle a wrapper dict just in case
    if isinstance(data, dict):
        data = data.get("data", data.get("staff", data.get("employees", [])))
    return data


def _poll_loop():
    """Background loop: fetch staff list, update cache, sleep, repeat."""
    _was_paused = False
    _was_closed = False
    while True:
        if _debug_flags["pause_poller"]:
            if not _was_paused:
                logger.info("Poller paused by debug flag – skipping polls")
                _was_paused = True
            time.sleep(POLL_INTERVAL)
            continue
        _was_paused = False

        if not _is_open():
            if not _was_closed:
                logger.info("Outside business hours – pausing API polls")
                with _cache_lock:
                    _cache["employees"] = []
                    _cache["ready"] = True
                _was_closed = True
            time.sleep(POLL_INTERVAL)
            continue
        if _was_closed:
            logger.info("Business hours started – resuming API polls")
            _was_closed = False

        try:
            employees = _fetch_staff()
            employees.sort(key=lambda e: (e.get("name") or "").upper())

            with _cache_lock:
                _cache["employees"] = employees
                _cache["last_success"] = datetime.now(timezone.utc)
                _cache["ready"] = True

            logger.info(
                "Polled OK – %d employees (%d onsite)",
                len(employees),
                sum(1 for e in employees if e.get("onsite_status") == "onsite"),
            )
        except Exception:
            logger.exception("API poll failed – serving last known data")

        time.sleep(POLL_INTERVAL)


def _start_poller():
    """Launch the polling thread (daemon so it dies with the app)."""
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

app = Flask(__name__)

# Start the poller once, avoiding the double-start that Flask's reloader causes
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _start_poller()


@app.route("/")
def index():
    cache = _get_cache()
    return render_template("index.html", **cache)


@app.route("/presence")
def presence():
    if _debug_flags["fail_next_presence"]:
        _debug_flags["fail_next_presence"] = False
        logger.warning("Returning 503 for /presence (debug flag)")
        abort(503)
    cache = _get_cache()
    return render_template("_presence.html", **cache)


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


# ---------------------------------------------------------------------------
# Debug routes (only registered when running with --debug)
# ---------------------------------------------------------------------------
if app.debug:

    @app.route("/debug/stale")
    def debug_stale():
        """Pause the poller and backdate last_success so stale state persists."""
        _debug_flags["pause_poller"] = True
        with _cache_lock:
            _cache["last_success"] = datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD + 60)
        logger.info("Debug: poller paused, data backdated to stale")
        return "Poller paused, data marked stale. Reset with /debug/unstale\n"

    @app.route("/debug/unstale")
    def debug_unstale():
        """Unpause the poller and reset last_success to now."""
        _debug_flags["pause_poller"] = False
        with _cache_lock:
            _cache["last_success"] = datetime.now(timezone.utc)
        logger.info("Debug: poller resumed, staleness cleared")
        return "Poller resumed, staleness cleared.\n"

    @app.route("/debug/fail-next")
    def debug_fail_next():
        """Make the next /presence request return 503."""
        _debug_flags["fail_next_presence"] = True
        logger.info("Debug: next /presence request will return 503")
        return "Next /presence request will return 503.\n"

    @app.route("/debug/closed")
    def debug_closed():
        """Force closed state regardless of schedule."""
        _debug_flags["force_closed"] = True
        _debug_flags["force_open"] = False
        logger.info("Debug: forced closed state")
        return "Forced closed. Reset with /debug/open\n"

    @app.route("/debug/open")
    def debug_open():
        """Clear closed override, resume normal schedule."""
        _debug_flags["force_closed"] = False
        _debug_flags["force_open"] = False
        logger.info("Debug: cleared schedule override, back to normal")
        return "Schedule override cleared.\n"
