"""Overview page - reference layout matching the Figma 'Supervisor Audit Dashboard'."""
import streamlit as st

from ui.components import page_header, card_title, kpi_figma, render_custom_table, toast_new, idle_expired, spacer
from backend.settings_store import load as load_settings
from backend.utils import load, flags_by_hour_fig

CARD_H = 400   # both lower cards share one height so their bottoms line up


def _body():
    if idle_expired():
        st.rerun()          # full rerun -> app.py shows the passcode screen
    df = load()
    if df is None:
        st.info("No data yet. Run python -m backend.audit_monitor.")
        return

    f = df[df["Status"] == "FLAGGED"]

    toast_new(f)

    k1, k2, k3 = st.columns(3)
    with k1:
        kpi_figma("Flagged Windows", len(f), "warning")
    with k2:
        kpi_figma("Sessions Affected", f["Session_ID"].nunique(), "alt_route")
    with k3:
        top = f["Risk_Score_%"].max() if len(f) else None
        kpi_figma("Highest Risk", f"{top:.1f}%" if top == top and top is not None else "-", "trending_up")

    spacer()   # same gap as the other pages between the KPI row and the cards

    left, right = st.columns([2, 1])
    with left:
        with st.container(border=True, height=CARD_H):
            card_title("Flagged Sessions")
            render_custom_table(df.sort_values("Timestamp", ascending=False).head(200))   # ALL windows, not only flagged
    with right:
        with st.container(border=True, height=CARD_H):
            card_title("Flags by Hour of Day")
            st.plotly_chart(flags_by_hour_fig(f, h=CARD_H - 90), config={"displayModeBar": False})


def render():
    page_header("Supervisor Audit Dashboard",
                "Read-only view of flagged encoding windows. Data is tagged, individuals are not identified.")
    cfg = load_settings()   # Settings page: live refresh on/off and interval (5 / 10 / 30 s)
    st.fragment(run_every=cfg["refresh_seconds"] if cfg["live_refresh"] else None)(_body)()