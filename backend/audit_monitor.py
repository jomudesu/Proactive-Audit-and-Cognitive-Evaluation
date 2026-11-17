"""
audit_monitor.py - PACE: Proactive Audit and Cognitive Evaluation for administrative clerks
Run (real):  python -m backend.audit_monitor
Run (demo):  python -m backend.audit_monitor --demo        (10 s cycle, simulated typing)
Add --log-all to any mode to also log windows below the threshold.
Run (panel): python -m backend.audit_monitor --presentation (scores each streamed window once; see scripts/run_live_presentation.py)
"""
import os
import sys
import time
import json
import glob
import argparse
import warnings
import re
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ CONFIG
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..")) if os.path.basename(SCRIPT_DIR) == "backend" else SCRIPT_DIR
AUDIT_LOG = os.path.join(PROJECT_ROOT, "MASTER_AUDIT_LOG.csv")

_MODEL_DIR = os.path.join(PROJECT_ROOT, "model")
MODEL_PATH = os.path.join(_MODEL_DIR, "cognitive_fatigue_ensemble.pkl")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join(PROJECT_ROOT, "cognitive_fatigue_ensemble.pkl")

SCALER_PATH = os.path.join(_MODEL_DIR, "feature_scaler.pkl")
if not os.path.exists(SCALER_PATH):
    SCALER_PATH = os.path.join(PROJECT_ROOT, "feature_scaler.pkl")

WINDOW_SECONDS = 1800        # analysis window = last 30 minutes
CYCLE_SECONDS = 1800         # real-mode cycle
DEMO_CYCLE_SECONDS = 10      # demo-mode cycle
RISK_THRESHOLD = 50.0        # thesis document says 85; your blueprint says 75 -> pick ONE
MIN_KEYSTROKES = 100         # skip windows with too little typing to be meaningful
MAX_GAP_MS = 5000            # pauses longer than 5 s are ignored (matches thesis Table 3.4)

# Per-window features stored in the log so the dashboard can show raw telemetry (Flagged Sessions page)
LOG_FEATURES = ["IKI_Variance", "KPM_Deviation", "Mean_Dwell_ms", "Std_Dwell_ms",
                "Mean_Flight_ms", "Std_Flight_ms", "Overall_KPM", "Backspace_Per_Minute"]
AUDIT_COLUMNS = ["Timestamp", "Session_ID", "App_Used", "Window_Start",
                 "Window_End", "Risk_Score_%", "Threshold_%", "Status"] + LOG_FEATURES


def data_root():
    home = os.path.expanduser("~")
    od = os.path.join(home, "OneDrive", "Documents", "EARIST_Thesis_Data")
    return od if os.path.exists(os.path.dirname(od)) else \
        os.path.join(home, "Documents", "EARIST_Thesis_Data")


KEYLOG_DIR = os.path.join(data_root(), "Keylogs")
SURVEY_DIR = os.path.join(data_root(), "Surveys")

# Presentation mode reads ONLY from this folder, so streamed demo files never touch your real data folders.
DEMO_ROOT = os.path.join(PROJECT_ROOT, "demo_stream")
PRESENTATION_POLL_SECONDS = 2
LOG_OK_WINDOWS = False   # False: windows below the threshold are neither printed nor logged (all modes)
MASK_PARTICIPANT_IN_PRESENTATION = True   # show SESS_... instead of Participant007_SESS_... on screen


# ------------------------------------------------------------ FEATURES
# Reuse the EXACT training-time feature code
for p in (PROJECT_ROOT, SCRIPT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import extract_features as ef

# Every feature the live monitor can compute. If the trained model expects anything else
# (e.g. you add a new column to the master dataset), startup STOPS instead of guessing a value.
PRODUCIBLE_FEATURES = {
    "Session_Hour_of_Day", "Duration_Seconds", "IKI_Variance", "Overall_KPM", "KPM_Deviation",
    "Mean_Dwell_ms", "Std_Dwell_ms", "Mean_Flight_ms", "Std_Flight_ms", "Backspace_Per_Minute",
    "Total_Backspaces", "Total_Keystrokes", "sleep_quality", "nutritional_status", "stress_level",
    "Sleep_IKI_Interaction", "Stress_KPM_Interaction",
}
MIN_KPM = 30                 # live mode: below this the model is outside its training range -> no score
MIN_WINDOW_SECONDS = 1200    # live mode: wait for >=20 min of typing (training sessions were ~30 min)


def extract_features(df, survey):
    df = df.sort_values("timestamp_ms").reset_index(drop=True)
    presses = df[df["event_type"] == "press"]
    total = len(presses)
    if total < MIN_KEYSTROKES:
        return None
    duration = (df["timestamp_ms"].max() - df["timestamp_ms"].min()) / 1000
    dwell = ef.compute_dwell_time(df)
    flight = ef.compute_flight_time(df)
    n_bs = int((presses["key_category"] == "BACKSPACE").sum())

    feats = {
        "Duration_Seconds": round(duration, 2),
        "IKI_Variance": ef.compute_iki_variance(df),
        "Overall_KPM": ef.compute_overall_kpm(total, duration),
        "KPM_Deviation": ef.compute_kpm_deviation(df),
        "Mean_Dwell_ms": dwell.mean() if len(dwell) else 0,
        "Std_Dwell_ms": dwell.std() if len(dwell) else 0,
        "Mean_Flight_ms": flight.mean() if len(flight) else 0,
        "Std_Flight_ms": flight.std() if len(flight) else 0,
        "Backspace_Per_Minute": ef.compute_backspace_frequency(df, duration),
        "Total_Backspaces": n_bs,
        "Total_Keystrokes": total,
        # training used the session START hour
        "Session_Hour_of_Day": datetime.fromtimestamp(df["timestamp_ms"].min() / 1000).hour,
    }
    feats.update({k: _num(v) for k, v in survey.items()})   # empty/invalid answers become NaN, caught later
    # interaction features, same formulas as the master dataset
    feats["Sleep_IKI_Interaction"] = feats["sleep_quality"] * feats["IKI_Variance"]
    feats["Stress_KPM_Interaction"] = feats["stress_level"] * feats["KPM_Deviation"]
    return feats


def drop_orphan_releases(g):
    """A window can start mid-keypress; drop a release whose press fell in the previous window."""
    g = g.sort_values("timestamp_ms")
    drop = [sub.index[0] for _, sub in g.groupby("key_category") if sub.iloc[0]["event_type"] == "release"]
    return g.drop(index=drop)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def non_finite(feats):
    """Names of features that are NaN/inf (e.g. empty survey answer, too few key events)."""
    return [k for k, v in feats.items() if k in PRODUCIBLE_FEATURES and not np.isfinite(_num(v))]


def load_survey(session_id):
    clean_id = re.sub(r"_W\d{2}$", "", session_id, flags=re.IGNORECASE)
    path = os.path.join(SURVEY_DIR, f"{clean_id}_survey.json")
    try:
        with open(path) as f:
            s = json.load(f)
        return {k: s[k] for k in ("sleep_quality", "nutritional_status", "stress_level")}
    except Exception:
        print(f"[WARN] survey for {clean_id} not found in {SURVEY_DIR}; window not scored")
        return None


# ------------------------------------------------------------- SCORING
class Scorer:
    def __init__(self):
        self.model = joblib.load(MODEL_PATH)
        self.scaler = joblib.load(SCALER_PATH)
        # The scaler remembers the EXACT columns/order used in training
        self.cols = list(getattr(self.scaler, "feature_names_in_", []))
        if not self.cols:
            sys.exit("[ERROR] scaler has no feature_names_in_. Retrain with a DataFrame.")
        unknown = [c for c in self.cols if c not in PRODUCIBLE_FEATURES]
        if unknown:
            sys.exit(f"[ERROR] The model was trained on features this monitor cannot compute: {unknown}\n"
                     f"        Add them to extract_features()/PRODUCIBLE_FEATURES, or retrain without them.")
        print(f"[SYSTEM] Model expects {len(self.cols)} features: {self.cols}")

    def score(self, feats):
        X = pd.DataFrame([{c: feats[c] for c in self.cols}], columns=self.cols)
        Xs = pd.DataFrame(self.scaler.transform(X), columns=self.cols)
        return float(self.model.predict_proba(Xs.values)[0, 1] * 100.0)


# ----------------------------------------------------- ALERT + AUDIT LOG
def notify(score):
    """Console message only. The on-screen alert is the themed toast in the PACE dashboard
    (it fires when a new FLAGGED row appears in the audit log), so no OS/device popup is sent."""
    print(f"[ALERT] Cognitive Fatigue Detected (Risk: {score:.0f}%). "
          f"Please double-check your data entries for the last 30 minutes.")


def _migrate_log():
    """If MASTER_AUDIT_LOG.csv was written by an older version (fewer columns), add the new columns
    in place (old rows keep blank telemetry) and keep a .bak copy. Prevents a corrupt, mixed-width CSV."""
    if not os.path.exists(AUDIT_LOG):
        return
    with open(AUDIT_LOG, newline="") as f:
        header = f.readline().strip().split(",")
    if header == AUDIT_COLUMNS:
        return
    shutil.copy(AUDIT_LOG, AUDIT_LOG + ".bak")
    pd.read_csv(AUDIT_LOG).reindex(columns=AUDIT_COLUMNS).to_csv(AUDIT_LOG, index=False)
    print(f"[SYSTEM] audit log upgraded to include telemetry columns (backup: {os.path.basename(AUDIT_LOG)}.bak)")


def log_window(session_id, app, score, w_start, w_end, status, feats=None):
    """Every analysed window is logged; Status is FLAGGED, OK or NOT_ASSESSED.
    feats (optional) adds the per-window feature values used by the dashboard."""
    _migrate_log()
    new = not os.path.exists(AUDIT_LOG)
    rec = {
        "Timestamp": datetime.now().isoformat(timespec="seconds"),
        "Session_ID": session_id,
        "App_Used": app,
        "Window_Start": w_start,
        "Window_End": w_end,
        "Risk_Score_%": round(score, 2) if score is not None else "",
        "Threshold_%": RISK_THRESHOLD,
        "Status": status,
    }
    for c in LOG_FEATURES:
        v = _num(feats.get(c)) if feats else float("nan")
        rec[c] = round(v, 2) if np.isfinite(v) else ""
    pd.DataFrame([rec], columns=AUDIT_COLUMNS).to_csv(AUDIT_LOG, mode="a", header=new, index=False)


# ------------------------------------------------------------ DATA SOURCES
def latest_real_window():
    files = glob.glob(os.path.join(KEYLOG_DIR, "*_keystrokes.csv"))
    if not files:
        return None
    path = max(files, key=os.path.getmtime)
    session_id = os.path.basename(path).replace("_keystrokes.csv", "")
    df = pd.read_csv(path, on_bad_lines="skip")      # tolerate a half-written last line
    if df.empty:
        return None
    cutoff = df["timestamp_ms"].max() - WINDOW_SECONDS * 1000
    df = df[df["timestamp_ms"] >= cutoff]
    return session_id, df, load_survey(session_id)


_seen_windows = set()


def next_presentation_window():
    """Oldest streamed window file that has not been scored yet (each file is scored exactly once)."""
    files = sorted(glob.glob(os.path.join(KEYLOG_DIR, "*_keystrokes.csv")), key=os.path.getmtime)
    for path in files:
        if path in _seen_windows:
            continue
        _seen_windows.add(path)
        sid = os.path.basename(path).replace("_keystrokes.csv", "")
        df = pd.read_csv(path, on_bad_lines="skip")
        if df.empty:
            continue
        df = drop_orphan_releases(df.dropna(subset=["timestamp_ms", "event_type", "key_category"]))
        return sid, df, load_survey(sid)
    return None


def simulated_window(fatigued):
    """DEMO ONLY: synthetic keystrokes. Fatigued = erratic rhythm, long dwell, more backspaces."""
    rng = np.random.default_rng()
    n = 900
    if fatigued:
        iki = rng.lognormal(mean=5.6, sigma=0.9, size=n)
        dwell = rng.normal(150, 55, size=n).clip(30)
        bs_p = 0.12
        survey = {"sleep_quality": 6, "nutritional_status": 6, "stress_level": 6}
    else:
        iki = rng.lognormal(mean=5.1, sigma=0.35, size=n)
        dwell = rng.normal(95, 15, size=n).clip(30)
        bs_p = 0.03
        survey = {"sleep_quality": 2, "nutritional_status": 3, "stress_level": 2}
    t = time.time() * 1000 - np.cumsum(iki)[::-1]
    cats = np.where(rng.random(n) < bs_p, "BACKSPACE", "ALPHANUMERIC")
    rows = []
    for ts, d, c in zip(t, dwell, cats):
        rows.append((ts, "press", c, "excel.exe"))
        rows.append((ts + d, "release", c, "excel.exe"))
    df = pd.DataFrame(rows, columns=["timestamp_ms", "event_type", "key_category", "active_app"])
    return "SESS_DEMO", df, survey


# ----------------------------------------------------------------- DEMO REPLAY
DATASET_PATH = os.path.join(PROJECT_ROOT, "ML_MASTER_DATASET.csv")
# 0 = replay a "not fatigued" session, 1 = replay a "fatigued" session (mix for the demo)
REPLAY_PATTERN = [0, 0, 1, 0, 1, 0, 0, 1]


def load_replay_pool():
    df = pd.read_csv(DATASET_PATH).dropna(subset=["Cognitive_Risk_Label"])
    if df["Cognitive_Risk_Label"].nunique() < 2:
        sys.exit("[ERROR] replay demo needs labeled sessions of BOTH classes in " + os.path.basename(DATASET_PATH))
    return df


def replay_features(pool, cycle_no, cols):
    """DEMO: replay the feature profile of a REAL labeled pilot session (+/-3% jitter).
    Whether it gets flagged is decided entirely by the trained model."""
    rng = np.random.default_rng(cycle_no)
    label = REPLAY_PATTERN[cycle_no % len(REPLAY_PATTERN)]
    row = pool[pool["Cognitive_Risk_Label"] == label].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
    feats = {}
    for c in cols:
        v = row.get(c, 0)
        keep = c in ("sleep_quality", "nutritional_status", "stress_level", "Session_Hour_of_Day")
        feats[c] = float(v) if keep else float(v) * float(rng.normal(1.0, 0.03))
    return feats


# ----------------------------------------------------------------- CYCLE
def shown_id(sid, demo):
    if demo == "presentation" and MASK_PARTICIPANT_IN_PRESENTATION:
        return re.sub(r"^Participant\d+_", "", sid)
    return sid


def run_cycle(scorer, demo, cycle_no, pool=None):
    """demo: None (live) | 'sim' (simulated keystrokes) | 'replay' (real pilot profiles)."""
    if demo is True:
        demo = "sim"
    now = datetime.now()
    if demo == "replay":
        sid = f"SESS_DEMO_{cycle_no:03d}"
        feats = replay_features(pool, cycle_no, scorer.cols)
        w_start = (now - pd.Timedelta(seconds=WINDOW_SECONDS)).isoformat(timespec="seconds")
        w_end = now.isoformat(timespec="seconds")
        app = "excel.exe"
    else:
        if demo == "sim":
            sid, df, survey = simulated_window(fatigued=(cycle_no % 2 == 1))
        elif demo == "presentation":
            res = next_presentation_window()
            if res is None:
                return                                   # nothing new streamed yet
            sid, df, survey = res
        else:
            res = latest_real_window()
            if res is None:
                print("[INFO] no keystroke log yet"); return
            sid, df, survey = res
        if survey is None:
            return                                       # never guess survey values
        feats = extract_features(df, survey)
        if feats is None:
            print(f"[INFO] <{MIN_KEYSTROKES} keystrokes in window; skipping"); return
        bad = non_finite(feats)
        if bad:
            print(f"[WARN] {sid}: invalid values in {bad}; window not scored"); return
        if demo in (None, "presentation") and feats["Duration_Seconds"] < MIN_WINDOW_SECONDS:
            print(f"[INFO] {sid}: only {feats['Duration_Seconds']:.0f}s of typing "
                  f"(need {MIN_WINDOW_SECONDS}s); " + ("skipped" if demo else "waiting")); return
        if demo in (None, "presentation") and feats["Overall_KPM"] < MIN_KPM:
            w0 = datetime.fromtimestamp(df["timestamp_ms"].min() / 1000).isoformat(timespec="seconds")
            w1 = datetime.fromtimestamp(df["timestamp_ms"].max() / 1000).isoformat(timespec="seconds")
            ap_ = df["active_app"].mode().iat[0] if "active_app" in df and not df["active_app"].empty else "unknown"
            shown = shown_id(sid, demo)
            print(f"[{now:%H:%M:%S}] {shown}  typing rate {feats['Overall_KPM']:.0f}/min < {MIN_KPM}: not assessed")
            log_window(shown, ap_, None, w0, w1, "NOT_ASSESSED", feats=feats); return
        w_start = datetime.fromtimestamp(df["timestamp_ms"].min() / 1000).isoformat(timespec="seconds")
        w_end = datetime.fromtimestamp(df["timestamp_ms"].max() / 1000).isoformat(timespec="seconds")
        app = df["active_app"].mode().iat[0] if "active_app" in df and not df["active_app"].empty else "unknown"

    sid = shown_id(sid, demo)
    score = scorer.score(feats)
    if score > RISK_THRESHOLD:
        print(f"[{now:%H:%M:%S}] {sid}  risk={score:.1f}%  threshold={RISK_THRESHOLD}")
        notify(score)                      # console alert only; the dashboard shows the toast
        log_window(sid, app, score, w_start, w_end, "FLAGGED", feats=feats)
        print("   -> FLAGGED + alert shown")
    elif LOG_OK_WINDOWS:                   # --log-all: keep below-threshold windows for comparison
        print(f"[{now:%H:%M:%S}] {sid}  risk={score:.1f}%  threshold={RISK_THRESHOLD}")
        log_window(sid, app, score, w_start, w_end, "OK", feats=feats)
        print("   -> below threshold, logged as OK")
    # else: below threshold -> nothing is printed or written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="15 s cycle, simulated keystrokes")
    ap.add_argument("--demo-replay", action="store_true",
                    help="15 s cycle, replays real pilot-session profiles (mix of flagged/unflagged)")
    ap.add_argument("--presentation", action="store_true", help="score each window file streamed by run_live_presentation.py, exactly once")
    ap.add_argument("--log-all", action="store_true",
                    help="also print/log windows BELOW the threshold (Status=OK); default is flagged-only")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override risk threshold (TESTING ONLY, e.g. --threshold 20)")
    args = ap.parse_args()
    global RISK_THRESHOLD, KEYLOG_DIR, SURVEY_DIR, LOG_OK_WINDOWS
    # Demo modes (--demo / --demo-replay) always log every window so something shows up right away
    LOG_OK_WINDOWS = args.log_all or args.demo or args.demo_replay
    if args.threshold is not None:
        RISK_THRESHOLD = args.threshold
        print(f"[WARN] threshold overridden to {RISK_THRESHOLD}% (testing only)")

    mode = "replay" if args.demo_replay else ("sim" if args.demo else ("presentation" if args.presentation else None))
    if mode == "presentation":
        KEYLOG_DIR = os.path.join(DEMO_ROOT, "Keylogs")
        SURVEY_DIR = os.path.join(DEMO_ROOT, "Surveys")
        os.makedirs(KEYLOG_DIR, exist_ok=True); os.makedirs(SURVEY_DIR, exist_ok=True)
        print(f"[SYSTEM] Presentation mode: watching {KEYLOG_DIR}")
    scorer = Scorer()
    pool = load_replay_pool() if mode == "replay" else None
    if pool is not None:
        miss = [c for c in scorer.cols if c not in pool.columns]
        if miss:
            sys.exit(f"[ERROR] {os.path.basename(DATASET_PATH)} is missing model columns: {miss}")
    cycle = PRESENTATION_POLL_SECONDS if mode == "presentation" else (DEMO_CYCLE_SECONDS if mode else CYCLE_SECONDS)
    print("[SYSTEM] Logging: " + ("ALL windows (FLAGGED + OK)" if LOG_OK_WINDOWS else "FLAGGED windows only (use --log-all for everything)"))
    print(f"[SYSTEM] Monitor started ({mode.upper() if mode else 'LIVE'}), cycle={cycle}s")
    n = 0
    while True:
        try:
            run_cycle(scorer, mode, n, pool)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")   # never let one bad cycle kill the monitor
        n += 1
        time.sleep(cycle)


if __name__ == "__main__":
    main()