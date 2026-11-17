"""
run_live_presentation.py - stream pre-windowed professional-encoder logs to the live monitor.

Terminal 1:  streamlit run app.py
Terminal 2:  python -m backend.audit_monitor --presentation
Terminal 3:  python scripts/run_live_presentation.py --source "Administrative Encoders" --delay 10 --limit 24

Files are copied into ./demo_stream (NOT your real EARIST_Thesis_Data folders), together with the
matching survey JSON, so the monitor scores every window with its real survey answers.
"""
import os
import re
import glob
import time
import shutil
import random
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..")) if os.path.basename(SCRIPT_DIR) == "scripts" else SCRIPT_DIR
DEMO_ROOT = os.path.join(PROJECT_ROOT, "demo_stream")           # must match audit_monitor.DEMO_ROOT
KEYLOG_DIR = os.path.join(DEMO_ROOT, "Keylogs")
SURVEY_DIR = os.path.join(DEMO_ROOT, "Surveys")
AUDIT_LOG = os.path.join(PROJECT_ROOT, "MASTER_AUDIT_LOG.csv")


def clear_demo_folders():
    for d in (KEYLOG_DIR, SURVEY_DIR):
        os.makedirs(d, exist_ok=True)
        for f in glob.glob(os.path.join(d, "*")):
            os.remove(f)


def atomic_copy(src, dst):
    """Copy under a temp name, then rename, so the monitor never reads a half-copied file."""
    tmp = dst + ".part"
    shutil.copy(src, tmp)
    os.replace(tmp, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="Administrative Encoders",
                    help="parent folder holding the participant subfolders")
    ap.add_argument("--delay", type=float, default=10, help="seconds between windows")
    ap.add_argument("--limit", type=int, default=None, help="stream at most N windows")
    ap.add_argument("--from-csv", default=None,
                    help="ENCODER_WINDOW_DATASET*.csv: stream only windows listed in it")
    ap.add_argument("--max-out", type=int, default=1,
                    help="with --from-csv: keep windows with at most N features outside the training range")
    ap.add_argument("--shuffle", action="store_true", help="mix participants instead of file-name order")
    ap.add_argument("--keep-log", action="store_true", help="do NOT delete MASTER_AUDIT_LOG.csv first")
    args = ap.parse_args()

    print("[SYSTEM] Initializing live presentation stream...")
    files = sorted(glob.glob(os.path.join(args.source, "**", "*_W*_keystrokes.csv"), recursive=True))
    if not files:
        print(f"[ERROR] No windowed keystroke files (*_W*_keystrokes.csv) under '{args.source}'.")
        return

    surveys = {}
    for p in glob.glob(os.path.join(args.source, "**", "*_survey.json"), recursive=True):
        surveys[os.path.basename(p).replace("_survey.json", "")] = p

    if args.from_csv:
        import pandas as pd
        sel = pd.read_csv(args.from_csv)
        if "Features_Outside_Training_Range" not in sel.columns:
            print("[ERROR] that CSV has no Features_Outside_Training_Range column; "
                  "rerun scripts/window_features.py with --train <labeled CSV>."); return
        keep = set(sel.loc[sel["Features_Outside_Training_Range"] <= args.max_out, "Session_ID"])
        by_name = {os.path.basename(f).replace("_keystrokes.csv", ""): f for f in files}
        missing = sorted(keep - set(by_name))
        files = [by_name[k] for k in sorted(keep) if k in by_name]
        print(f"[SYSTEM] {len(keep)} windows selected (<= {args.max_out} features out of range); "
              f"{len(files)} matching files found")
        if missing:
            print(f"[WARN] no window file found for: {missing[:5]}{' ...' if len(missing) > 5 else ''}")
        if not files:
            return

    if args.shuffle:
        random.Random(42).shuffle(files)
    if args.limit:
        files = files[: args.limit]

    clear_demo_folders()
    if not args.keep_log and os.path.exists(AUDIT_LOG):
        os.remove(AUDIT_LOG)
        print("[SYSTEM] Old MASTER_AUDIT_LOG.csv removed (use --keep-log to keep it)")

    print(f"[STREAM] {len(files)} windows x {args.delay:g}s = about "
          f"{len(files) * args.delay / 60:.1f} minutes. Start python -m backend.audit_monitor --presentation first.")
    sent = 0
    for path in files:
        name = os.path.basename(path)
        parent = re.sub(r"_W\d{2}$", "", name.replace("_keystrokes.csv", ""), flags=re.IGNORECASE)
        if parent not in surveys:
            print(f"  [SKIP] {name}: no survey file named {parent}_survey.json under the source folder")
            continue
        survey_dst = os.path.join(SURVEY_DIR, f"{parent}_survey.json")
        if not os.path.exists(survey_dst):
            shutil.copy(surveys[parent], survey_dst)        # survey first, then the window
        atomic_copy(path, os.path.join(KEYLOG_DIR, name))
        sent += 1
        print(f"  -> [{sent}/{len(files)}] streamed {name}")
        time.sleep(args.delay)

    print(f"\n[SUCCESS] Presentation stream complete ({sent} windows sent).")


if __name__ == "__main__":
    main()