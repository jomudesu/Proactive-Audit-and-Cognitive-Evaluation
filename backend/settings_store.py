"""settings_store.py - persistent dashboard settings, supervisor passcode and the access log.

No Streamlit imports, so any page (or a test script) can use it.
  settings.json   user choices (refresh interval, alerts, privacy, passcode hash ...)
  ACCESS_LOG.csv  audit trail of who changed / exported what (Timestamp, Event, Detail)
Both files live next to app.py.
"""
import csv
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..")) if os.path.basename(HERE) == "backend" else HERE
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")
CONFIG_DEFAULT = os.path.join(PROJECT_ROOT, "config", "settings.default.json")
ACCESS_LOG = os.path.join(PROJECT_ROOT, "ACCESS_LOG.csv")
AUDIT_LOG = os.path.join(PROJECT_ROOT, "MASTER_AUDIT_LOG.csv")

REFRESH_CHOICES = (5, 10, 30)               # seconds
TIMEOUT_CHOICES = (15, 20, 30, 60)          # minutes of inactivity before the passcode lock
RETENTION_CHOICES = (0, 30, 90, 180, 365)   # days; 0 = keep until purged by hand

DEFAULTS = {
    "live_refresh": True,
    "refresh_seconds": 5,
    "toast_alerts": True,
    "sound_effects": False,
    "anonymize_default": True,      # default state of "Anonymize user IDs" on the Reports page
    "anon_salt": "",                # generated once; makes anonymous tags stable but not guessable
    "consent_confirmed": False,
    "consent_date": "",
    "retention_days": 0,
    "passcode_enabled": False,
    "passcode_salt": "",
    "passcode_hash": "",
    "timeout_minutes": 30,
}
_CHOICES = {"refresh_seconds": REFRESH_CHOICES, "timeout_minutes": TIMEOUT_CHOICES,
            "retention_days": RETENTION_CHOICES}


# ---------------------------------------------------------------- settings
def load():
    """Settings merged over the defaults; a missing/corrupt/invalid file never raises."""
    cfg = dict(DEFAULTS)
    target_file = SETTINGS_FILE if os.path.exists(SETTINGS_FILE) else CONFIG_DEFAULT
    try:
        with open(target_file, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, default in DEFAULTS.items():
                if k in raw and type(raw[k]) is type(default):
                    cfg[k] = raw[k]
    except (OSError, ValueError):
        pass
    for k, choices in _CHOICES.items():
        if cfg[k] not in choices:
            cfg[k] = DEFAULTS[k]
    return cfg


def save(cfg):
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)          # never leaves a half-written file


def update(**changes):
    cfg = load()
    cfg.update({k: v for k, v in changes.items() if k in DEFAULTS})
    save(cfg)
    return cfg


def get_salt():
    salt = load()["anon_salt"]
    if not salt:
        salt = secrets.token_hex(16)
        update(anon_salt=salt)
    return salt


# ---------------------------------------------------------------- passcode
_ITERATIONS = 200_000


def _hash(pin, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONS).hex()


def set_passcode(pin):
    salt = secrets.token_hex(16)
    update(passcode_enabled=True, passcode_salt=salt, passcode_hash=_hash(pin, salt))


def clear_passcode():
    update(passcode_enabled=False, passcode_salt="", passcode_hash="")


def check_passcode(pin, cfg=None):
    cfg = cfg or load()
    if not cfg["passcode_hash"]:
        return False
    try:
        return hmac.compare_digest(_hash(pin, cfg["passcode_salt"]), cfg["passcode_hash"])
    except ValueError:
        return False


def lock_enabled(cfg=None):
    cfg = cfg or load()
    return bool(cfg["passcode_enabled"] and cfg["passcode_hash"])


# ---------------------------------------------------------------- access log
def log_event(event, detail=""):
    try:
        new = not os.path.exists(ACCESS_LOG)
        with open(ACCESS_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["Timestamp", "Event", "Detail"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), event, detail])
    except OSError:
        pass                                 # logging must never break the dashboard


def read_log(limit=200):
    """Newest events first."""
    try:
        with open(ACCESS_LOG, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    return rows[::-1][:limit]


def log_bytes():
    try:
        with open(ACCESS_LOG, "rb") as f:
            return f.read()
    except OSError:
        return b""


# ---------------------------------------------------------------- retention
def _expired(df, days):
    ts = __import__("pandas").to_datetime(df["Timestamp"], errors="coerce")
    return ts < (datetime.now() - timedelta(days=days))     # unparsable timestamps are kept


def count_older_than(days):
    if days <= 0 or not os.path.exists(AUDIT_LOG):
        return 0
    import pandas as pd
    try:
        return int(_expired(pd.read_csv(AUDIT_LOG), days).sum())
    except Exception:
        return 0


def purge_older_than(days):
    """Permanently delete audit rows older than `days`. Returns how many were removed."""
    import pandas as pd
    df = pd.read_csv(AUDIT_LOG)
    gone = _expired(df, days)
    tmp = AUDIT_LOG + ".tmp"
    df[~gone].to_csv(tmp, index=False)
    os.replace(tmp, AUDIT_LOG)
    return int(gone.sum())