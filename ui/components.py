import html
import io
import math
import struct
import time
import wave

import pandas as pd
import streamlit as st

from backend.settings_store import load as load_settings, lock_enabled

# A window within +/- NEAR_MARGIN percentage points of the threshold is shown as "Near Threshold",
# whether it is just below the limit (approaching) or just above it (barely flagged).
# The alert/FLAGGED logic in audit_monitor.py is NOT affected: this only changes the badge.
NEAR_MARGIN = 10.0

# level -> (label shown, CSS class defined in styles.py)
LEVELS = {
    "high": ("High Risk",      "high"),
    "near": ("Near Threshold", "near"),
    "low":  ("Low Risk",       "low"),
    "na":   ("Not Assessed",   "other"),
}


def risk_level(row, status_col="Status"):
    status = str(row[status_col]).upper()
    score, thr = row.get("Risk_Score_%"), row.get("Threshold_%")
    if status == "NOT_ASSESSED" or pd.isna(score):
        return "na"
    if pd.isna(thr):                                   # no threshold stored: fall back to the log status
        return "high" if status == "FLAGGED" else "low"
    if abs(score - thr) <= NEAR_MARGIN:
        return "near"
    return "high" if score > thr else "low"


def page_header(title, subtitle=""):
    st.markdown(
        f'<div class="page-title">{html.escape(title)}</div>'
        f'<div class="page-sub">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True)


def spacer(rem=1.25):
    """Vertical gap that matches the page spacing. The auto-refreshing Overview body (st.fragment) sits in a
    nested block that does not get the global gap from styles.py, so it adds its own."""
    st.markdown(f'<div style="height:{rem}rem"></div>', unsafe_allow_html=True)


def card_title(text):
    st.markdown(f'<div class="card-title">{html.escape(text)}</div>', unsafe_allow_html=True)


def kpi_figma(label, value, icon="warning"):
    v = str(value)
    size = " sm" if len(v) > 9 else ""
    st.markdown(
        '<div class="kpi">'
        f'<div><div class="kpi-label">{html.escape(str(label))}</div>'
        f'<div class="kpi-value{size}" title="{html.escape(v)}">{html.escape(v)}</div></div>'
        f'<div class="kpi-icon"><span class="material-symbols-outlined">{icon}</span></div>'
        '</div>', unsafe_allow_html=True)


def _badge(level):
    label, cls = LEVELS[level]
    return f'<span class="pace-badge {cls}">{html.escape(label)}</span>'


def render_custom_table(df, status_col="Status"):
    if df is None or df.empty:
        st.markdown('<div class="empty">No windows logged yet.</div>', unsafe_allow_html=True)
        return

    cols = [("Date", "12%", ""), ("Session ID", "20%", ""), ("App Used", "12%", ""),
            ("Window Start", "13%", ""), ("Window End", "13%", ""),
            ("Risk Score", "12%", "c"), ("Status", "18%", "c")]
    head = "".join(f'<th class="{c}" style="width:{w}">{n}</th>' for n, w, c in cols)

    body = []
    for _, row in df.iterrows():
        ts = row["Timestamp"].strftime("%Y-%m-%d") if pd.notna(row["Timestamp"]) else "-"   # time is in Window Start/End
        ws = row["Window_Start"].strftime("%H:%M:%S") if pd.notna(row["Window_Start"]) else "-"
        we = row["Window_End"].strftime("%H:%M:%S") if pd.notna(row["Window_End"]) else "-"
        risk = f"{row['Risk_Score_%']:.1f}%" if pd.notna(row["Risk_Score_%"]) else "-"
        level = risk_level(row, status_col)
        body.append(
            "<tr>"
            f"<td>{ts}</td>"
            f"<td title=\"{html.escape(str(row['Session_ID']), quote=True)}\">{html.escape(str(row['Session_ID']))}</td>"
            f"<td>{html.escape(str(row['App_Used']))}</td><td>{ws}</td><td>{we}</td>"
            f'<td class="c">{risk}</td><td class="c">{_badge(level)}</td>'
            "</tr>")

    st.markdown(
        '<div class="pace-wrap"><table class="pace-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True)


def _fmt(v, unit, nd=1):
    return f"{v:.{nd}f} {unit}" if pd.notna(v) else "—"


def telemetry_panel(row):
    items = [("Dwell Time:", _fmt(row.get("Mean_Dwell_ms"), "ms")),
             ("Flight Time:", _fmt(row.get("Mean_Flight_ms"), "ms")),
             ("Keypress Rate:", _fmt(row.get("Overall_KPM"), "k/min")),
             ("Backspace Freq:", _fmt(row.get("Backspace_Per_Minute"), "/min"))]
    st.markdown("<div>" + "".join(
        f'<div class="tele-row"><span>{k}</span><span>{v}</span></div>' for k, v in items) + "</div>",
        unsafe_allow_html=True)


def toast_new(flagged):
    cfg = load_settings()
    n, prev = len(flagged), st.session_state.get("n_flagged")
    st.session_state["n_flagged"] = n
    if prev is not None and n > prev:
        r = flagged.sort_values("Timestamp").iloc[-1]
        if cfg["toast_alerts"]:
            st.toast(f"**Proactive Error Verification** - Cognitive fatigue detected "
                     f"(risk {r['Risk_Score_%']:.0f}%) in {r['Session_ID']}.", icon="⚠️")
        if cfg["sound_effects"]:
            play_alert_sound()


_BEEP = None


def _beep_wav():
    """A short two-tone chime, generated once (no audio file needed)."""
    global _BEEP
    if _BEEP is None:
        rate, frames = 22050, bytearray()
        for freq, dur in ((880, 0.14), (660, 0.2)):
            n = int(rate * dur)
            for i in range(n):
                env = min(1.0, i / (rate * 0.01), (n - i) / (rate * 0.04))
                frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * freq * i / rate)))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        _BEEP = buf.getvalue()
    return _BEEP


def play_alert_sound():
    """Hidden audio element that autoplays once (the player is hidden in styles.py).
    Browsers may block autoplay until the page has been clicked at least once."""
    try:
        st.audio(_beep_wav(), format="audio/wav", autoplay=True)
    except TypeError:          # older Streamlit without autoplay
        pass


def idle_expired():
    """True when the passcode lock is on and the supervisor has been idle past the timeout.
    Used by the auto-refreshing Overview fragment to trigger the lock without a click."""
    cfg = load_settings()
    last = st.session_state.get("last_active")
    return lock_enabled(cfg) and last is not None and time.time() - last > cfg["timeout_minutes"] * 60