"""Reports page: filters -> live print preview -> PDF / telemetry CSV / summary CSV downloads."""
from datetime import date, time, timedelta

import streamlit as st

import backend.report_builder as rb
import backend.settings_store as store
from ui.components import card_title, kpi_figma, page_header
from backend.utils import get_df

PRESETS = ["Today", "Last 7 days", "Last 30 days", "All time", "Custom range"]


def _preset_range(preset, df):
    today = date.today()
    if preset == "Today":
        return today, today
    if preset == "Last 7 days":
        return today - timedelta(days=6), today
    if preset == "Last 30 days":
        return today - timedelta(days=29), today
    return df["Timestamp"].min().date(), max(today, df["Timestamp"].max().date())     # All time


def _log_download(kind, ref):
    store.log_event("Report downloaded", f"{kind}; {ref}")


def _kpis(slot, rep):
    s = rep["stats"] if rep else None
    pct = lambda v: "N/A" if v is None else f"{v * 100:.1f}%"
    with slot:
        c1, c2, c3 = st.columns(3)
        with c1: kpi_figma("Total Audited Sessions", s["sessions"] if s else "-", "fact_check")
        with c2: kpi_figma("Shift Compliance Rate", pct(s["compliance"]) if s else "-", "verified_user")
        with c3: kpi_figma("Flagged Window Ratio", pct(s["flag_ratio"]) if s else "-", "report")


def render():
    page_header("Reports", "Generate and export audit reports.")
    df = get_df()
    if df is None:
        return
    cfg = store.load()

    kpi_slot = st.container()          # filled below, once the filters are known
    left, right = st.columns([1.7, 1])

    with left, st.container(border=True):
        card_title("Report Generator")
        c1, c2 = st.columns(2)
        preset = c1.selectbox("Date range", PRESETS, index=2, key="rp_preset")
        t1, t2 = c2.columns(2)
        t_from = t1.time_input("From time", value=time(0, 0), key="rp_t1")
        t_to = t2.time_input("To time", value=time(23, 59), key="rp_t2")
        if preset == "Custom range":
            d1, d2 = st.columns(2)
            d_from = d1.date_input("From", value=df["Timestamp"].min().date(), key="rp_d1", format="YYYY/MM/DD")
            d_to = d2.date_input("To", value=max(date.today(), df["Timestamp"].max().date()), key="rp_d2",
                                 format="YYYY/MM/DD")
        else:
            d_from, d_to = _preset_range(preset, df)

        f1, f2 = st.columns(2)
        sessions = f1.multiselect("Session ID", sorted(df["Session_ID"].astype(str).unique()), key="rp_sess",
                                  placeholder="All sessions")
        apps = f2.multiselect("Application", sorted(df["App_Used"].dropna().astype(str).unique()), key="rp_app",
                              placeholder="All applications")
        shift = st.radio("Shift type", ["Morning", "Evening", "All"], index=2, horizontal=True, key="rp_shift",
                         help="Shift is decided by the hour a window started: Morning 00:00-11:59, Evening 12:00-23:59.")

        st.markdown("**Anonymization settings**")
        anon = st.checkbox("Anonymize user IDs", value=cfg["anonymize_default"], key="rp_anon",
                           help="Replaces each Session ID with a stable anonymous tag (SESS-XXXXXXXX).")
        mask = st.checkbox("Mask sensitive data", value=False, key="rp_mask",
                           help="Hides application names and leaves raw typing telemetry out of the exports.")

        if d_from > d_to or t_from > t_to:
            st.error("The start of the range must come before its end.")
            _kpis(kpi_slot, None)
            return
        sel = rb.apply_filters(df, d_from, d_to, t_from, t_to, shift, sessions, apps)
        if sel.empty:
            st.info("No windows match these filters.")
            _kpis(kpi_slot, None)
            return

        rep = rb.build_report(sel, d_from=d_from, d_to=d_to, t_from=t_from, t_to=t_to, shift=shift,
                              sessions=sessions, apps=apps, anonymize=anon, mask=mask, salt=store.get_salt())
        sig = (d_from, d_to, t_from, t_to, shift, tuple(sessions), tuple(apps), anon, mask, len(sel))

        if st.button("Generate Audit Report", type="primary", key="rp_gen", use_container_width=True):
            try:
                pdf = rb.build_pdf(rep)
            except ImportError as exc:
                pdf = None
                st.error(str(exc))
            st.session_state["rp_out"] = dict(
                sig=sig, ref=rep["ref"], generated=rep["generated"], pdf=pdf,
                csv=rb.csv_bytes(rep["telemetry"]), summary=rb.csv_bytes(rep["sessions"]))
            store.log_event("Report generated", f"{rep['ref']}; {len(sel)} windows; "
                            f"anonymized={anon}; masked={mask}")

        out = st.session_state.get("rp_out")
        ready = out is not None and out["sig"] == sig
        if ready:                                    # keep preview and files on the same reference number
            rep["ref"], rep["generated"] = out["ref"], out["generated"]
        ref = out["ref"] if out else ""

        b1, b2, b3 = st.columns(3)
        b1.download_button("Download PDF report", data=out["pdf"] if ready and out["pdf"] else b"",
                           file_name=f"{ref}.pdf", mime="application/pdf", key="rp_dl_pdf",
                           disabled=not (ready and out["pdf"]), use_container_width=True,
                           on_click=_log_download, args=("PDF", ref))
        b2.download_button("Export CSV telemetry", data=out["csv"] if ready else b"",
                           file_name=f"{ref}_telemetry.csv", mime="text/csv", key="rp_dl_csv",
                           disabled=not ready, use_container_width=True, on_click=_log_download,
                           args=("Telemetry CSV", ref))
        b3.download_button("Summary data (CSV)", data=out["summary"] if ready else b"",
                           file_name=f"{ref}_summary.csv", mime="text/csv", key="rp_dl_sum",
                           disabled=not ready, use_container_width=True, on_click=_log_download,
                           args=("Summary CSV", ref))
        if out is None:
            st.caption("Press Generate Audit Report, then download the files you need.")
        elif not ready:
            st.caption("Filters or data changed since the last report. Generate again to refresh the downloads.")

    _kpis(kpi_slot, rep)
    with right, st.container(border=True):
        card_title("Print Preview")
        st.markdown(rb.preview_html(rep), unsafe_allow_html=True)
        st.caption("Preview follows your filters. The PDF has the full flagged-window log.")