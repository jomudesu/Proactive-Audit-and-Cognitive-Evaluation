import os
import time

import streamlit as st

# Standard imports (no importlib) so errors show up clearly on screen
import backend.settings_store as store
from ui.components import card_title, page_header
from ui.styles import apply_styles
from views import dashboard, flagged, risk, reports, settings

st.set_page_config(page_title="PACE System", layout="wide")
apply_styles()

MAX_FAILS, LOCKOUT_SECONDS = 5, 60


def gate():
    """Optional supervisor passcode (Settings > Supervisor Security). Locks after the idle timeout."""
    cfg = store.load()
    if not store.lock_enabled(cfg):
        st.session_state["unlocked"] = True
        return cfg
    now = time.time()
    if st.session_state.get("unlocked"):
        if now - st.session_state.get("last_active", now) <= cfg["timeout_minutes"] * 60:
            st.session_state["last_active"] = now          # any click / page change counts as activity
            return cfg
        st.session_state["unlocked"] = False
        store.log_event("Dashboard locked", f"idle for {cfg['timeout_minutes']} minutes")

    page_header("Supervisor Access", "Enter the supervisor passcode to open the audit dashboard.")
    _, mid, _ = st.columns([1, 1, 1])
    with mid, st.container(border=True):
        card_title("Unlock dashboard")
        with st.form("unlock_form"):
            pin = st.text_input("Passcode", type="password", label_visibility="collapsed", placeholder="Passcode")
            go = st.form_submit_button("Unlock", type="primary", use_container_width=True)
        if go:
            if now < st.session_state.get("lock_until", 0):
                st.error(f"Too many attempts. Try again in {int(st.session_state['lock_until'] - now) + 1} s.")
            elif store.check_passcode(pin, cfg):
                st.session_state.update(unlocked=True, last_active=now, fails=0)
                store.log_event("Dashboard unlocked")
                st.rerun()
            else:
                fails = st.session_state.get("fails", 0) + 1
                st.session_state["fails"] = fails
                store.log_event("Failed unlock attempt", f"attempt {fails}")
                if fails >= MAX_FAILS:
                    st.session_state.update(lock_until=now + LOCKOUT_SECONDS, fails=0)
                    st.error(f"Too many attempts. Locked for {LOCKOUT_SECONDS} seconds.")
                else:
                    st.error("Incorrect passcode.")
    st.stop()


cfg = gate()

pages = [
    st.Page(dashboard.render, title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
    st.Page(flagged.render, title="Flagged Sessions", icon=":material/flag:", url_path="flagged"),
    st.Page(risk.render, title="Risk Analysis", icon=":material/monitoring:", url_path="risk"),
    st.Page(reports.render, title="Reports", icon=":material/description:", url_path="reports"),
    st.Page(settings.render, title="Settings", icon=":material/settings:", url_path="settings"),
]

nav = st.navigation(pages, position="hidden")

with st.sidebar:
    LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "earist_logo.png")
    if os.path.exists(LOGO):
        st.image(LOGO, width=60)

    st.markdown('<div class="brand">PACE<small>Proactive Audit and Cognitive Evaluation</small></div>', unsafe_allow_html=True)

    st.divider()

    for p in pages:
        st.page_link(p)

    if store.lock_enabled(cfg):
        if st.button("Lock dashboard", key="lock_now", use_container_width=True):
            st.session_state["unlocked"] = False
            store.log_event("Dashboard locked", "manual")
            st.rerun()

nav.run()