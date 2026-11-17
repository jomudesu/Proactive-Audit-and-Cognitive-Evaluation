# PACE: Proactive Audit and Cognitive Evaluation

PACE watches how administrative clerks type, estimates a **cognitive-fatigue risk score** for each 30-minute window, and shows supervisors which windows deserve a second look at the data entries. It was built as a thesis project at EARIST (Eulogio "Amang" Rodriguez Institute of Science and Technology).

PACE does not read what is typed. It uses typing *timing* only (how long keys are held, pauses between keys, correction rate) plus three short self-reported survey answers. Sessions are tagged, and individuals are not identified on screen.

> **Research prototype.** The model was trained on a small pilot dataset (see [Model](#model)). Scores are a prompt to double-check entries, not an assessment of any person, and should not be used for employment decisions.

## What is in this repository

| Part | Files | What it does |
|---|---|---|
| Monitor | `audit_monitor.py` | Scores typing windows and writes `MASTER_AUDIT_LOG.csv` |
| Feature extraction | `extract_features.py` | Computes the typing features used for training and live scoring |
| Demo streamer | `run_live_presentation.py` | Feeds pre-windowed recordings to the monitor for presentations |
| Dashboard | `app.py`, `views/`, `components.py`, `styles.py`, `utils.py` | Streamlit supervisor dashboard |
| Reports and settings | `report_builder.py`, `settings_store.py`, `views/insights.py` | PDF/CSV reports, saved settings, plain-language risk summaries |
| Model | `cognitive_fatigue_ensemble.pkl`, `feature_scaler.pkl` | Trained ensemble and its scaler |
| Training data | `ML_MASTER_DATASET.csv` | One row per labeled session window |

```
.
├── app.py                  # dashboard entry point
├── audit_monitor.py
├── extract_features.py
├── run_live_presentation.py
├── report_builder.py
├── settings_store.py
├── components.py  styles.py  utils.py
├── views/
│   ├── dashboard.py  flagged.py  risk.py  reports.py  settings.py
│   └── insights.py
├── assets/earist_logo.png  # optional logo shown in the sidebar
├── cognitive_fatigue_ensemble.pkl
├── feature_scaler.pkl
└── ML_MASTER_DATASET.csv
```

## How it works

1. **Collect.** A data-collection tool records key events (`timestamp_ms`, `event_type` press/release, `key_category`, `active_app`) as `*_keystrokes.csv`. Each participant also has a `*_survey.json` with `sleep_quality`, `nutritional_status` and `stress_level`.
2. **Window.** In live mode the monitor takes the last 30 minutes of the newest log every cycle.
3. **Extract features.** Dwell time, flight time, inter-key-interval variance, keys per minute and its variation, backspace rate and totals, and two survey interaction terms (`Sleep_IKI_Interaction`, `Stress_KPM_Interaction`). The 16 model inputs are listed in the scaler's `feature_names_in_`.
4. **Score.** Features are min-max scaled with the training ranges and passed to a soft-voting ensemble. The **Risk Score** is the average predicted probability of "at risk" across the models, times 100.
5. **Flag.** A score above the threshold (`RISK_THRESHOLD` in `audit_monitor.py`, currently 50%) is logged as `FLAGGED`. Windows with fewer than 100 keystrokes are skipped. In live and presentation modes, windows shorter than 20 minutes are skipped, and windows typed below 30 keys per minute are logged as `NOT_ASSESSED`.
6. **Review.** The dashboard reads `MASTER_AUDIT_LOG.csv` and refreshes automatically.

## Model

- **Ensemble:** scikit-learn `VotingClassifier` (soft voting, equal weights) of a random forest (50 trees), gradient boosting (learning rate 0.05, 100 stages) and an RBF support vector machine.
- **Training data:** 31 labeled windows from 13 participants (16 not at risk, 15 at risk).
- **Estimated performance:** about 0.83 AUC and 74% accuracy in cross-validation, including leave-one-participant-out. With 31 windows these estimates are rough.
- **Known limits:** window length is the single most informative feature in the training data, the SVM adds little, and live windows are capped at 30 minutes. Treat results as a prototype, not a validated detector.

## Setup

Requires Python 3.10 or newer.

```bash
pip install streamlit pandas numpy plotly scikit-learn joblib reportlab
```

Use the same scikit-learn version that was used to train the `.pkl` files, or loading may warn or fail.

The monitor reads recordings from `~/OneDrive/Documents/EARIST_Thesis_Data/` (or `~/Documents/EARIST_Thesis_Data/` if OneDrive is not used), with two subfolders:

```
EARIST_Thesis_Data/
├── Keylogs/   # *_keystrokes.csv
└── Surveys/   # *_survey.json, named to match the session
```

## Running it

**Dashboard**

```bash
streamlit run app.py
```

**Live monitoring** (scores the newest recording every 30 minutes)

```bash
python audit_monitor.py
```

**Demos**

```bash
python audit_monitor.py --demo            # synthetic typing, 15 s cycle
python audit_monitor.py --demo-replay     # replays real pilot-session profiles, 15 s cycle
```

**Live presentation** (three terminals)

```bash
streamlit run app.py                                                    # 1: dashboard
python audit_monitor.py --presentation                                  # 2: scores each streamed window once
python run_live_presentation.py --source "Administrative Encoders" --delay 10 --limit 24   # 3: streams windows
```

The streamer copies files into `./demo_stream` and never touches your real data folders. Useful flags: `--from-csv`, `--shuffle`, `--keep-log`.

**Monitor options**

| Flag | Effect |
|---|---|
| `--log-all` | Also log windows below the threshold (`OK`). Needed for compliance-rate figures on the Reports page. |
| `--threshold N` | Override the risk threshold (testing only) |

## Dashboard pages

- **Overview:** flagged-window count, sessions affected, highest risk, a live table, and flags by hour of day.
- **Flagged Sessions:** search and date filters, plus an inspection panel with raw telemetry for one window.
- **Risk Analysis:** risk over time, typing-pattern radar, which measures push windows over the threshold (compared with the training data), and a plain-language summary.
- **Reports:** filter by date, time, shift, session and application. A live print preview, then PDF, telemetry CSV and summary CSV downloads, with optional anonymized session IDs and masked application names.
- **Settings:** live-refresh interval, toast and sound alerts, anonymization default, consent record, retention and manual purge, optional supervisor passcode with idle timeout, and an access log.

## Data and privacy

Keystroke logs, surveys, the audit log and the training dataset describe real participants. Check consent and your institution's rules before publishing any of them. Under the Data Privacy Act (RA 10173), keep them out of a public repository.

Files created while the system runs, which you should **not** commit:

```gitignore
MASTER_AUDIT_LOG.csv
MASTER_AUDIT_LOG.csv.bak
ACCESS_LOG.csv
settings.json        # contains the passcode hash and anonymization salt
demo_stream/
EXTRACTED_FEATURES.csv
```

## Troubleshooting

- **"No data yet. Run audit_monitor.py."** The audit log does not exist yet. Start the monitor (or a demo mode).
- **Only flagged windows appear, and compliance shows N/A.** Run the monitor with `--log-all`.
- **`ModuleNotFoundError`.** Run commands from the project folder, and keep `views/` next to `app.py`.
- **Passcode forgotten.** Delete the `passcode_*` lines from `settings.json` and restart.
- **No alert sound.** Browsers block autoplay until you have clicked on the page. Use "Play test sound" in Settings.