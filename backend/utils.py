import os
import importlib
import numpy as np
import pandas as pd
import streamlit as st

try:
    go = importlib.import_module("plotly.graph_objects")
except ModuleNotFoundError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..")) if os.path.basename(HERE) == "backend" else HERE
LOG = os.path.join(PROJECT_ROOT, "MASTER_AUDIT_LOG.csv")
SCALER = os.path.join(PROJECT_ROOT, "model", "feature_scaler.pkl")
SCALER_FALLBACK = os.path.join(PROJECT_ROOT, "feature_scaler.pkl")
TRAIN_DATA = os.path.join(PROJECT_ROOT, "ML_MASTER_DATASET.csv")   # the data the model was trained on

MAROON, GOLD, INK, ALERT = "#56151F", "#C9A25B", "#3B0F16", "#D62828"

RHYTHM = ["IKI_Variance", "KPM_Deviation", "Std_Flight_ms", "Mean_Flight_ms"]
FINE_MOTOR = ["Mean_Dwell_ms", "Std_Dwell_ms", "Backspace_Per_Minute", "Overall_KPM"]
FEATS = RHYTHM + FINE_MOTOR
LABEL = {
    "IKI_Variance": "IKI Variance", "KPM_Deviation": "KPM Deviation",
    "Std_Flight_ms": "Flight Variability", "Mean_Flight_ms": "Mean Flight Time",
    "Mean_Dwell_ms": "Mean Dwell Time", "Std_Dwell_ms": "Dwell Variability",
    "Backspace_Per_Minute": "Backspace Rate", "Overall_KPM": "Typing Pace (KPM)",
}

def load():
    if not os.path.exists(LOG):
        return None
    df = pd.read_csv(LOG)
    if df.empty:
        return None
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df["Window_Start"] = pd.to_datetime(df["Window_Start"], errors="coerce")
    df["Window_End"] = pd.to_datetime(df["Window_End"], errors="coerce")
    df["Hour"] = df["Window_Start"].dt.hour.fillna(df["Timestamp"].dt.hour).astype(int)
    for c in ["Risk_Score_%", "Threshold_%"] + FEATS:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else np.nan
    return df

def get_df():
    df = load()
    if df is None:
        st.info("No data yet. Run python -m backend.audit_monitor.")
        return None
    return df

@st.cache_resource
def baseline():
    """feature -> (mean, SD) of the TRAINING data, used for every "SD from training average" figure.
    feature_scaler.pkl is a MinMaxScaler (it stores min/max, not mean/SD), so the mean and SD are
    computed from ML_MASTER_DATASET.csv. A StandardScaler is still accepted as a fallback."""
    try:
        d = pd.read_csv(TRAIN_DATA)
        out = {f: (float(d[f].mean()), float(d[f].std())) for f in FEATS if f in d.columns}
        if out:
            return out
    except Exception:
        pass
    try:
        import joblib
        scaler_file = SCALER if os.path.exists(SCALER) else SCALER_FALLBACK
        sc = joblib.load(scaler_file)
        return dict(zip(sc.feature_names_in_, zip(sc.mean_, sc.scale_)))
    except Exception:
        return {}      # zscores() then falls back to the selection's own mean/SD

def zscores(d):
    base, out = baseline(), pd.DataFrame(index=d.index)
    for f in FEATS:
        if d[f].notna().sum() == 0:
            continue
        m, s = base.get(f, (d[f].mean(), d[f].std()))
        out[f] = (d[f] - m) / (s if s else 1)
    return out

def style_chart(fig, h, dark=False):
    bg = "#1E1E1E" if dark else "rgba(0,0,0,0)"
    font_color = "#FFFFFF" if dark else INK
    
    fig.update_layout(
        height=h, margin=dict(l=10, r=10, t=30, b=10), 
        paper_bgcolor=bg, plot_bgcolor=bg, 
        font=dict(color=font_color, family="Inter"),
        legend=dict(orientation="h", y=-0.2, font=dict(color=font_color)),
        # Force axis lines and grid lines to match the theme
        xaxis=dict(
            tickfont=dict(color=font_color),
            title_font=dict(color=font_color),
            gridcolor="#E6E0D4" if not dark else "#444",
        ),
        yaxis=dict(
            tickfont=dict(color=font_color),
            title_font=dict(color=font_color),
            gridcolor="#E6E0D4" if not dark else "#444",
        )
    )
    return fig

def trend_fig(d, h=300, dark=False):
    d = d.sort_values("Timestamp")
    fig = go.Figure()
    line_color = GOLD if dark else MAROON
    fig.add_scatter(x=d["Timestamp"], y=d["Risk_Score_%"], mode="lines+markers",
                    line=dict(color=line_color, width=2), name="Risk score")
    
    f = d[d["Status"] == "FLAGGED"]
    if len(f):
        fig.add_scatter(x=f["Timestamp"], y=f["Risk_Score_%"], mode="markers",
                        marker=dict(color=ALERT, size=10, symbol="diamond"), name="Flagged")
    
    thr = d["Threshold_%"].dropna()
    if len(thr):
        fig.add_hline(y=thr.iloc[-1], line_dash="dash", line_color=GOLD, annotation_text="Threshold")
    
    # Force axes text and lines to the INK color so they don't default to white
    axis_color = "#FFFFFF" if dark else INK
    grid_color = "#444" if dark else "#eee"
    
    fig.update_yaxes(range=[0, 100], title="Risk %", gridcolor=grid_color, 
                     tickfont=dict(color=axis_color), title_font=dict(color=axis_color))
    fig.update_xaxes(gridcolor=grid_color, tickfont=dict(color=axis_color), title_font=dict(color=axis_color))
    
    return style_chart(fig, h, dark)

def flags_by_hour_fig(d, h=300):
    """Bar chart of FLAGGED windows per hour of day (0-23), styled like the mockup."""
    f = d[d["Status"] == "FLAGGED"] if len(d) else d
    counts = f.groupby("Hour").size().reindex(range(24), fill_value=0)
    fig = go.Figure(go.Bar(
        x=list(counts.index), y=list(counts.values),
        marker=dict(color=MAROON, line=dict(color=GOLD, width=1.5)),
        hovertemplate="Hour %{x}:00<br>%{y} flag(s)<extra></extra>"))
    style_chart(fig, h)
    fig.update_layout(showlegend=False, bargap=0.25, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(dtick=1, range=[-0.6, 23.6], showgrid=False, tickfont=dict(size=11, color=INK))
    fig.update_yaxes(rangemode="tozero", tickformat="d", gridcolor="#E6E0D4", tickfont=dict(size=11, color=INK))
    return fig