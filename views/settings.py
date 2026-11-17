"""Settings page: appearance, supervisor security, Data Privacy Act compliance, alerts and live refresh.
Every control saves immediately to settings.json (see settings_store.py)."""
import os
import time
from datetime import date

import streamlit as st

import backend.settings_store as store
from ui.components import card_title, page_header, play_alert_sound

ROW1_H, ROW2_H = 560, 330


def _persist(key, widget_key):
    value = st.session_state[widget_key]
    store.update(**{key: value})
    store.log_event("Setting changed", f"{key} = {value}")


def _persist_consent():
    ok = st.session_state["s_consent"]
    store.update(consent_confirmed=ok, consent_date=date.today().isoformat() if ok else "")
    store.log_event("Consent record changed", "confirmed" if ok else "cleared")


def _retention_label(days):
    return "Keep until I purge" if days == 0 else f"{days} days"


@st.dialog("Supervisor passcode")
def _passcode_dialog():
    cfg = store.load()
    enabled = store.lock_enabled(cfg)
    with st.form("pc_form"):
        cur = st.text_input("Current passcode", type="password") if enabled else ""
        new = st.text_input("New passcode (at least 4 characters)", type="password")
        conf = st.text_input("Confirm new passcode", type="password")
        ok = st.form_submit_button("Save", type="primary")
    if enabled:
        st.caption("Leave both new-passcode fields empty to turn the lock off.")
    st.caption("Forgot it? Delete the passcode_* lines from settings.json and restart the app.")
    if not ok:
        return
    if enabled and not store.check_passcode(cur, cfg):
        store.log_event("Passcode change failed", "wrong current passcode")
        st.error("The current passcode is incorrect.")
    elif not new and not conf:
        if enabled:
            store.clear_passcode()
            store.log_event("Passcode lock turned off")
            st.session_state["s_flash"] = "Passcode lock turned off."
            st.rerun()
        st.error("Enter a new passcode.")
    elif new != conf:
        st.error("The two passcodes do not match.")
    elif len(new) < 4:
        st.error("Use at least 4 characters.")
    else:
        store.set_passcode(new)
        st.session_state.update(unlocked=True, last_active=time.time())
        store.log_event("Passcode lock turned on" if not enabled else "Passcode changed")
        st.session_state["s_flash"] = "Passcode saved."
        st.rerun()


@st.dialog("Access log", width="large")
def _access_log_dialog():
    rows = store.read_log(200)
    if not rows:
        st.info("No events recorded yet.")
        return
    st.caption("Newest first. Shows the last 200 events.")
    st.dataframe(rows, hide_index=True, use_container_width=True, height=340)
    st.download_button("Download full log (CSV)", data=store.log_bytes(), file_name="PACE_access_log.csv",
                       mime="text/csv")


@st.dialog("Purge old records")
def _purge_dialog(days):
    n = store.count_older_than(days)
    st.write(f"**{n}** record(s) in MASTER_AUDIT_LOG.csv are older than {days} days.")
    st.warning("This permanently deletes those rows. Stop the audit monitor first so it is not writing to the "
               "log at the same moment.")
    if os.path.exists(store.AUDIT_LOG):
        with open(store.AUDIT_LOG, "rb") as f:
            st.download_button("Download a copy first", data=f.read(), file_name="MASTER_AUDIT_LOG_copy.csv",
                               mime="text/csv")
    sure = st.checkbox("I understand these records cannot be recovered", key="s_purge_ok")
    if st.button("Purge records", type="primary", disabled=(n == 0 or not sure)):
        removed = store.purge_older_than(days)
        store.log_event("Audit records purged", f"{removed} records older than {days} days")
        st.session_state["s_flash"] = f"{removed} record(s) purged."
        st.rerun()


def render():
    page_header("Settings", "System configurations and privacy settings.")
    flash = st.session_state.pop("s_flash", None)
    if flash:
        st.toast(flash)
    cfg = store.load()
    lock_on = store.lock_enabled(cfg)

    a, b, c = st.columns(3)

    # ---------------------------------------------------------- appearance
    with a, st.container(border=True, height=ROW1_H):
        card_title("Appearance and Theme")
        st.toggle("Light mode", value=True, disabled=True, key="s_light")
        st.caption("Choose your preferred interface appearance. The dashboard is light-only for now; "
                   "a dark theme has not been built yet.")

    # ---------------------------------------------------------- security
    with b, st.container(border=True, height=ROW1_H):
        card_title("Supervisor Security Settings")
        st.markdown(f"**Supervisor passcode:** {'On' if lock_on else 'Off'}")
        if st.button("Change or turn off passcode" if lock_on else "Set a passcode", key="s_pc_btn",
                     use_container_width=True):
            _passcode_dialog()
        st.selectbox("Session timeout", store.TIMEOUT_CHOICES, index=store.TIMEOUT_CHOICES.index(cfg["timeout_minutes"]),
                     format_func=lambda m: f"{m} mins", key="s_timeout", disabled=not lock_on,
                     on_change=_persist, args=("timeout_minutes", "s_timeout"))
        st.caption("The dashboard asks for the passcode again after this much inactivity.")
        st.markdown("**Access log review**")
        if st.button("Open access log", key="s_log_btn", use_container_width=True):
            _access_log_dialog()
        st.caption("Two-factor authentication needs a sign-in system, which this dashboard does not have yet. "
                   "The passcode lock is the supervisor protection available now.")

    # ---------------------------------------------------------- privacy
    with c, st.container(border=True, height=ROW1_H):
        card_title("Data Privacy Act Compliance")
        st.toggle("Anonymization", value=cfg["anonymize_default"], key="s_anon",
                  on_change=_persist, args=("anonymize_default", "s_anon"))
        st.caption("Anonymize session IDs in generated reports by default.")
        st.markdown("**User consent management**")
        st.checkbox("Participants consented to anonymized monitoring", value=cfg["consent_confirmed"],
                    key="s_consent", on_change=_persist_consent)
        if cfg["consent_confirmed"] and cfg["consent_date"]:
            st.caption(f"Consent recorded on {cfg['consent_date']}.")
        st.markdown("**Data retention policy**")
        st.selectbox("Keep audit records for", store.RETENTION_CHOICES,
                     index=store.RETENTION_CHOICES.index(cfg["retention_days"]), format_func=_retention_label,
                     key="s_retention", on_change=_persist, args=("retention_days", "s_retention"))
        days = cfg["retention_days"]
        n_old = store.count_older_than(days)
        if days:
            st.caption(f"{n_old} record(s) are older than {days} days. Purging is manual so nothing is deleted by surprise.")
        else:
            st.caption("Records are kept until you purge them.")
        if st.button("Review and purge old records", key="s_purge_btn", disabled=(not days or n_old == 0),
                     use_container_width=True):
            _purge_dialog(days)

    d, e = st.columns([1.7, 1])

    # ---------------------------------------------------------- alerts
    with d, st.container(border=True, height=ROW2_H):
        card_title("Alerts and Notifications")
        st.toggle("Proactive Toast Alert", value=cfg["toast_alerts"], key="s_toast",
                  on_change=_persist, args=("toast_alerts", "s_toast"))
        st.caption("Receive real-time on-screen notifications for critical audit activities.")
        st.toggle("Sound Effects", value=cfg["sound_effects"], key="s_sound",
                  on_change=_persist, args=("sound_effects", "s_sound"))
        st.caption("Enable audio cues for notifications and system events.")
        if st.button("Play test sound", key="s_test"):
            play_alert_sound()

    # ---------------------------------------------------------- refresh
    with e, st.container(border=True, height=ROW2_H):
        card_title("Live Auto-Refresh Controls")
        st.toggle("Live refresh", value=cfg["live_refresh"], key="s_live",
                  on_change=_persist, args=("live_refresh", "s_live"))
        st.radio("Refresh every", store.REFRESH_CHOICES, index=store.REFRESH_CHOICES.index(cfg["refresh_seconds"]),
                 format_func=lambda s: f"{s}s", horizontal=True, key="s_refresh", disabled=not cfg["live_refresh"],
                 on_change=_persist, args=("refresh_seconds", "s_refresh"))
        st.caption("Applies to the Overview page the next time you open it.")