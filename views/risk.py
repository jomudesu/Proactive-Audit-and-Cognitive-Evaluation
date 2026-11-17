import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from backend.utils import get_df, zscores, trend_fig, style_chart, FEATS, LABEL
from ui.components import page_header, card_title, kpi_figma, risk_level, NEAR_MARGIN
from views.insights import build_summary

LEVEL_NAMES = {"high": "High Risk", "near": "Near Threshold", "low": "Low Risk"}

def render():
    page_header("Risk Analysis", "Why windows were flagged: when risk rises, and which typing behaviours drive it.")
    
    df = get_df()
    if df is None: return

    # ---- filters (session, application, risk level, date range)
    df = df.copy()
    df["Level"] = df.apply(risk_level, axis=1)
    c = st.columns([2, 2, 2, 1.2, 1.2])
    sess = c[0].multiselect("Session ID", sorted(df["Session_ID"].astype(str).unique()), key="r_sess",
                            placeholder="All sessions", label_visibility="collapsed")
    apps = c[1].multiselect("Application", sorted(df["App_Used"].dropna().astype(str).unique()), key="r_app",
                            placeholder="All applications", label_visibility="collapsed")
    lvls = c[2].multiselect("Risk level", list(LEVEL_NAMES.values()), key="r_lvl",
                            placeholder="All risk levels", label_visibility="collapsed")
    d_from = c[3].date_input("From", key="r_from", value=df["Timestamp"].min().date(),
                             format="YYYY/MM/DD", label_visibility="collapsed")
    d_to = c[4].date_input("To", key="r_to", value=max(date.today(), df["Timestamp"].max().date()),
                           format="YYYY/MM/DD", label_visibility="collapsed")
    keep = (df["Timestamp"].dt.date >= d_from) & (df["Timestamp"].dt.date <= d_to)
    if sess: keep &= df["Session_ID"].astype(str).isin(sess)
    if apps: keep &= df["App_Used"].astype(str).isin(apps)
    if lvls: keep &= df["Level"].map(LEVEL_NAMES).isin(lvls)
    df = df[keep]

    assessed = df[df["Status"].isin(["FLAGGED", "OK"])].copy()
    if assessed.empty:
        st.info("No assessed windows match the current filters.")
        return
        
    z = zscores(assessed)
    fl_mask, ok_mask = assessed["Status"] == "FLAGGED", assessed["Status"] == "OK"
    mz = z[fl_mask].mean().dropna() if not z.empty else pd.Series(dtype=float)
    
    dominant = "-"
    if not mz.empty:
        top = mz.abs().idxmax()
        dominant = f"{LABEL[top]} {'↑' if mz[top] > 0 else '↓'}"

    c1, c2, c3 = st.columns(3)
    with c1: kpi_figma("Average Risk Score", f"{assessed['Risk_Score_%'].mean():.1f}%", "warning")
    with c2: kpi_figma("Dominant Risk Factor", dominant, "hub")
    with c3: kpi_figma("High Risk Windows", int(fl_mask.sum()), "trending_up")

    r1a, r1b = st.columns([1.6, 1])
    with r1a, st.container(border=True):
        card_title("Risk Score Over Time")
        st.plotly_chart(trend_fig(assessed, 320), use_container_width=True)
    with r1b, st.container(border=True):
        card_title("Rhythm vs Fine Motor")
        if not z.empty:
            axes = [f for f in FEATS if f in z.columns]
            names = [LABEL[f] for f in axes]
            fig = go.Figure()
            for mask, name, color, dash in ((None, "Training average", "#999999", "dash"),
                                            (ok_mask, "OK windows", "#C9A25B", None),
                                            (fl_mask, "Flagged windows", "#56151F", None)):
                v = [0.0] * len(axes) if mask is None else z.loc[mask, axes].mean().clip(-3, 3).fillna(0).tolist()
                fig.add_trace(go.Scatterpolar(r=v + v[:1], theta=names + names[:1], name=name,
                              line=dict(color=color, dash=dash), fill=None if mask is None else "toself",
                              opacity=1 if mask is None else 0.55))
            fig.update_layout(polar=dict(radialaxis=dict(range=[-3, 3], tickvals=[-2, 0, 2])))
            st.plotly_chart(style_chart(fig, 320), use_container_width=True)

    r2a, r2b = st.columns([1.6, 1])
    with r2a, st.container(border=True):
        card_title("What Pushes Windows Over the Threshold")
        if not mz.empty:
            m = mz.reindex(mz.abs().sort_values().index)
            fig = go.Figure(go.Bar(x=m.values, y=[LABEL[f] for f in m.index], orientation="h",
                                   marker_color=["#56151F" if v > 0 else "#C9A25B" for v in m.values]))
            fig.update_xaxes(title="Avg deviation (SD from training average)")
            st.plotly_chart(style_chart(fig, 320), use_container_width=True)
    with r2b, st.container(border=True):
        card_title("Peak Risk by Session")
        g = assessed.groupby("Session_ID").agg(peak=("Risk_Score_%", "max"),
                                               flags=("Status", lambda s: (s == "FLAGGED").sum()))
        g = g.sort_values("peak").tail(12)
        fig = go.Figure(go.Bar(x=g["peak"], y=g.index, orientation="h",
                               marker_color=["#56151F" if n else "#C9A25B" for n in g["flags"]]))
        fig.update_xaxes(range=[0, 100], title="Peak risk %")
        st.plotly_chart(style_chart(fig, 320), use_container_width=True)

    with st.container(border=True):
        card_title("Summary & Conclusion")
        st.markdown(build_summary(assessed, z, NEAR_MARGIN), unsafe_allow_html=True)    