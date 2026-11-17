"""
window_features.py - turn RAW professional-encoder sessions into 30-minute windows comparable to
the training data, using the SAME feature code as the live monitor (audit_monitor.extract_features).

Why: professional shifts last hours and contain long pauses, so session-level features
(Overall_KPM, Backspace_Per_Minute, Duration...) fall far outside the training range.
Cutting into 30-minute windows and keeping only windows with enough typing fixes that.

Usage (from the project root):
    python scripts/window_features.py --root "C:\\path\\to\\folder\\with\\keylogs_and_surveys"
    python scripts/window_features.py --root "..." --score    # also add Predicted_Risk_Score_%

Output: ENCODER_WINDOW_DATASET.csv  (one row per kept window; Cognitive_Risk_Label left blank)
"""
import os
import re
import sys
import json
import glob
import argparse
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..")) if os.path.basename(SCRIPT_DIR) == "scripts" else SCRIPT_DIR
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from backend import audit_monitor as am          # shares extract_features() with the live system

FEATURE_ORDER = [
    "Duration_Seconds", "IKI_Variance", "Overall_KPM", "KPM_Deviation", "Mean_Dwell_ms",
    "Std_Dwell_ms", "Mean_Flight_ms", "Std_Flight_ms", "Backspace_Per_Minute",
    "Total_Backspaces", "Total_Keystrokes", "sleep_quality", "nutritional_status",
    "stress_level", "Sleep_IKI_Interaction", "Stress_KPM_Interaction",
]


TRAIN_CANDIDATES = ["GT_MASTER_DATASET.csv", "ML_MASTER_DATASET.csv", "ML_MASTER_DATASET_1.csv"]


def find_training_csv(name):
    """Look for the labeled training CSV: the given name first, then common names, in the script
    folder and the current folder. Returns a path or None."""
    for n in [name] + [c for c in TRAIN_CANDIDATES if c != name]:
        for base in (PROJECT_ROOT, os.getcwd()):
            p = n if os.path.isabs(n) else os.path.join(base, n)
            if os.path.exists(p):
                return p
    return None


def index_surveys(root):
    out = {}
    for path in glob.glob(os.path.join(root, "**", "*_survey.json"), recursive=True):
        try:
            with open(path) as f:
                s = json.load(f)
            # THE FIX: Force extraction from filename to preserve "ParticipantNNN_" prefix
            sid = os.path.basename(path).replace("_survey.json", "")
            out[sid] = {k: s[k] for k in ("sleep_quality", "nutritional_status", "stress_level")}
        except Exception as e:
            print(f"[WARN] unreadable survey {path}: {e}")
    return out


def drop_orphan_releases(g):
    """A window can start mid-keypress. A release whose press fell in the previous window would
    shift the press/release pairing of its whole key category, so remove it."""
    g = g.sort_values("timestamp_ms")
    drop = []
    for _, sub in g.groupby("key_category"):
        first = sub.iloc[0]
        if first["event_type"] == "release":
            drop.append(sub.index[0])
    return g.drop(index=drop)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=PROJECT_ROOT, help="folder searched (recursively) for logs + surveys")
    ap.add_argument("--window-min", type=float, default=30, help="window length in minutes")
    ap.add_argument("--min-span", type=float, default=am.MIN_WINDOW_SECONDS,
                    help="min seconds between first and last keystroke in a window")
    ap.add_argument("--min-kpm", type=float, default=30,
                    help="min keystrokes/min (training data minimum was ~32)")
    ap.add_argument("--min-keystrokes", type=int, default=500)
    ap.add_argument("--train", default="GT_MASTER_DATASET.csv",
                    help="labeled training CSV, used only for the range check")
    ap.add_argument("--score", action="store_true", help="score each kept window with the trained model")
    ap.add_argument("--out", default="ENCODER_WINDOW_DATASET.csv")
    args = ap.parse_args()

    surveys = index_surveys(args.root)
    logs = sorted(glob.glob(os.path.join(args.root, "**", "*_keystrokes.csv"), recursive=True))
    print(f"[SYSTEM] {len(logs)} keystroke logs, {len(surveys)} surveys found under {args.root}")
    if not logs:
        return

    train_path = find_training_csv(args.train)
    ranges = None
    if train_path:
        tt = pd.read_csv(train_path)
        ranges = {c: (tt[c].min(), tt[c].max()) for c in FEATURE_ORDER if c in tt.columns}
        print(f"[SYSTEM] Training-range check uses: {train_path}")
    else:
        print(f"[WARN] training CSV not found (looked for {args.train} and {TRAIN_CANDIDATES} in "
              f"{PROJECT_ROOT} and {os.getcwd()}). The range check and the "
              f"Features_Outside_Training_Range column will be MISSING. Use --train <path>.")

    scorer = am.Scorer() if args.score else None
    win_ms = args.window_min * 60 * 1000
    rows, dropped = {}, {} # Initialize rows properly as list in original, wait, fixing initialization below
    rows = []

    for path in logs:
        raw_sid = os.path.basename(path).replace("_keystrokes.csv", "")
        # THE FIX: Strip the _W01 window tag if it exists so it matches the survey dictionary perfectly
        sid = re.sub(r"_W\d{2}$", "", raw_sid, flags=re.IGNORECASE)
        
        if sid not in surveys:
            print(f"[WARN] no survey for {sid}; session skipped"); dropped["no_survey"] = dropped.get("no_survey", 0) + 1
            continue
        try:
            df = pd.read_csv(path, on_bad_lines="skip")
            df = df.dropna(subset=["timestamp_ms", "event_type", "key_category"])
        except Exception as e:
            print(f"[WARN] cannot read {path}: {e}"); continue
        if df.empty:
            continue
        t0 = df["timestamp_ms"].min()
        df["_w"] = ((df["timestamp_ms"] - t0) // win_ms).astype(int)
        m = re.search(r"Participant(\d+)", sid)
        pnum = int(m.group(1)) if m else ""

        for w, g in df.groupby("_w"):
            g = drop_orphan_releases(g.drop(columns="_w"))
            presses = int((g["event_type"] == "press").sum())
            if presses < args.min_keystrokes:
                dropped["too_few_keystrokes"] = dropped.get("too_few_keystrokes", 0) + 1; continue
            span = (g["timestamp_ms"].max() - g["timestamp_ms"].min()) / 1000
            if span < args.min_span:
                dropped["short_span"] = dropped.get("short_span", 0) + 1; continue
            
            # THE FIX: Feed the properly matched survey using the clean 'sid'
            feats = am.extract_features(g, surveys[sid])
            if feats is None:
                dropped["too_few_keystrokes"] = dropped.get("too_few_keystrokes", 0) + 1; continue
            if feats["Overall_KPM"] < args.min_kpm:
                dropped["low_typing_rate"] = dropped.get("low_typing_rate", 0) + 1; continue
            bad = am.non_finite(feats)
            if bad:
                dropped["invalid_features"] = dropped.get("invalid_features", 0) + 1
                if dropped["invalid_features"] <= 10:
                    print(f"[WARN] {os.path.basename(path)} window {int(w)}: NaN/inf in {bad}; skipped")
                continue

            # Keep the raw_sid to preserve the W01 tag if it exists, or append one if it doesn't
            output_session_id = f"{raw_sid}_W{int(w):02d}" if "_W" not in raw_sid else raw_sid

            row = {
                "Session_ID": output_session_id,
                "Participant_Number": pnum,
                "timestamp": pd.Timestamp(g["timestamp_ms"].min() / 1000, unit="s").isoformat(),
                "Cognitive_Risk_Label": "",
                "Parent_Session": sid,
                "Window_Index": int(w),
            }
            row.update({k: round(float(feats[k]), 2) for k in FEATURE_ORDER})
            if ranges:
                row["Features_Outside_Training_Range"] = sum(
                    1 for c, (lo, hi) in ranges.items() if not (lo <= feats[c] <= hi))
            if scorer:
                row["Predicted_Risk_Score_%"] = round(scorer.score(feats), 2)
            rows.append(row)

    out = pd.DataFrame(rows)
    total_drop = sum(dropped.values())
    print(f"\n[RESULT] kept {len(out)} windows from {len(logs)} sessions; dropped {total_drop}: {dropped}")
    if out.empty:
        print("[WARN] nothing passed the activity filters; try lowering --min-kpm / --min-keystrokes")
        return
    out.to_csv(os.path.join(PROJECT_ROOT, args.out), index=False)
    print(f"[SUCCESS] saved {args.out}  ({out['Participant_Number'].nunique()} participants)")

    # ---- how comparable are the kept windows to the training data? ----
    if train_path:
        t = tt
        print("\nShare of kept windows OUTSIDE the training range (lower is better):")
        for c in FEATURE_ORDER:
            if c in t.columns:
                pct = ((out[c] < t[c].min()) | (out[c] > t[c].max())).mean() * 100
                flag = "  <-- check" if pct > 25 else ""
                print(f"  {c:24s} {pct:5.0f}%{flag}")
    if "Features_Outside_Training_Range" in out.columns:
        n0 = int((out["Features_Outside_Training_Range"] == 0).sum())
        print(f"\nWindows fully inside the training range: {n0} of {len(out)}  "
              f"(column Features_Outside_Training_Range in the CSV; trust scores most where it is 0)")
    if scorer:
        s = out["Predicted_Risk_Score_%"]
        print("\nPredicted risk on kept windows: " +
              ", ".join(f">{t}%: {(s > t).sum()}" for t in (50, 60, 70, 85)) + f"  (of {len(s)})")


if __name__ == "__main__":
    main()