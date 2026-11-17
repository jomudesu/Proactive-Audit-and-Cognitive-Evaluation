"""report_builder.py - everything the Reports page needs, with no Streamlit calls.

    apply_filters -> build_report -> build_pdf / preview_html / csv_bytes

One report dict feeds the on-screen print preview AND the downloadable files, so they always agree.
"""
import hashlib
import html
import io
from datetime import datetime

import numpy as np
import pandas as pd

from views import insights
from ui.components import LEVELS, risk_level
from backend.utils import FEATS, zscores

INSTITUTION = 'EULOGIO "AMANG" RODRIGUEZ INSTITUTE OF SCIENCE AND TECHNOLOGY'
FOOTER = "CONFIDENTIAL - FOR SUPERVISORY & COMPLIANCE USE ONLY (RA 10173)"
SYSTEM = "PACE - Proactive Audit and Cognitive Evaluation"
TITLE = "Supervisor Encoding Audit & Cognitive Risk Report"

# Shift = hour the window STARTED, [from, to). Edit here if your office uses other shift hours.
SHIFTS = {"Morning": (0, 12), "Evening": (12, 24)}

LOG_COLS = ["Timestamp", "Session_ID", "App_Used", "Window_Start", "Window_End",
            "Risk_Score_%", "Threshold_%", "Status"]
MASKED = "[masked]"


# ------------------------------------------------------------------ filtering
def apply_filters(df, d_from, d_to, t_from, t_to, shift="All", sessions=(), apps=()):
    """Rows whose log date is in [d_from, d_to] and whose window STARTED between t_from and t_to."""
    w = df["Window_Start"].fillna(df["Timestamp"])
    mins = w.dt.hour * 60 + w.dt.minute
    dates = df["Timestamp"].dt.date
    keep = (dates >= d_from) & (dates <= d_to)
    keep &= (mins >= t_from.hour * 60 + t_from.minute) & (mins <= t_to.hour * 60 + t_to.minute)
    if shift in SHIFTS:
        lo, hi = SHIFTS[shift]
        keep &= (w.dt.hour >= lo) & (w.dt.hour < hi)
    if sessions:
        keep &= df["Session_ID"].astype(str).isin(list(sessions))
    if apps:
        keep &= df["App_Used"].astype(str).isin(list(apps))
    return df[keep].copy()


# ------------------------------------------------------------------ privacy
def _tag(value, salt):
    return "SESS-" + hashlib.sha256((salt + str(value)).encode("utf-8")).hexdigest()[:8].upper()


def protect(df, anonymize_ids, mask_sensitive, salt):
    """Anonymize = replace Session_ID with a salted tag. Mask = hide application names."""
    out = df.copy()
    if anonymize_ids and "Session_ID" in out:
        out["Session_ID"] = out["Session_ID"].astype(str).map(lambda s: _tag(s, salt))
    if mask_sensitive and "App_Used" in out:
        out["App_Used"] = MASKED
    return out


def _csv_safe(df):
    """Stop spreadsheet formula injection: text starting with = + - @ gets a leading apostrophe."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):     # pandas 2 and 3
            out[c] = out[c].map(lambda v: "'" + v if isinstance(v, str) and v[:1] in "=+-@" and v else v)
    return out


def csv_bytes(df):
    return _csv_safe(df).to_csv(index=False).encode("utf-8-sig")      # BOM so Excel opens it cleanly


# ------------------------------------------------------------------ report data
def _pct(x, nd=1):
    return "N/A" if x is None else f"{x * 100:.{nd}f}%"


def _summary_text(s, range_text, drivers):
    if s["assessed"] == 0:
        return ("No assessed windows were found for this selection, so there is nothing to score. "
                f"{s['not_assessed']} window(s) were logged as not assessed." if s["not_assessed"]
                else "No windows were logged for this selection.")
    parts = [f"This report covers {s['assessed']} assessed typing window(s) from {s['sessions']} session(s) "
             f"between {range_text}."]
    if s["flagged"]:
        share = f" ({_pct(s['flag_ratio'])})" if s["flag_ratio"] is not None else ""
        parts.append(f"{s['flagged']} window(s){share} scored above the {s['threshold']:.0f}% risk threshold, "
                     f"affecting {s['sessions_affected']} session(s); the highest score was {s['peak_risk']:.1f}%.")
        if drivers:
            parts.append(f"Flagged windows were mainly characterized by {drivers}.")
    else:
        parts.append(f"No window crossed the {s['threshold']:.0f}% threshold; the highest score was "
                     f"{s['peak_risk']:.1f}%.")
    if not s["has_ok"]:
        parts.append("Only flagged windows were found in the log, so compliance and flag-ratio figures are not "
                     "available (run python -m backend.audit_monitor with --log-all to record every window).")
    parts.append("These figures describe typing-pattern risk. They are a prompt to double-check entries, "
                 "not an assessment of any individual.")
    return " ".join(parts)


def build_report(sel, *, d_from, d_to, t_from, t_to, shift, sessions, apps,
                 anonymize, mask, salt, generated=None, max_rows=500):
    generated = generated or datetime.now()
    sel = sel.sort_values("Timestamp")
    assessed = sel[sel["Status"].isin(["FLAGGED", "OK"])]
    fl = assessed[assessed["Status"] == "FLAGGED"]
    n_a, n_fl = len(assessed), len(fl)
    has_ok = bool((assessed["Status"] == "OK").any())
    thr_s = sel["Threshold_%"].dropna()
    thr = float(thr_s.iloc[-1]) if len(thr_s) else 50.0

    stats = dict(
        logged=len(sel), assessed=n_a, flagged=n_fl, has_ok=has_ok, threshold=thr,
        not_assessed=int((sel["Status"] == "NOT_ASSESSED").sum()),
        sessions=int(assessed["Session_ID"].nunique()),
        sessions_affected=int(fl["Session_ID"].nunique()),
        avg_risk=float(assessed["Risk_Score_%"].mean()) if n_a else None,
        peak_risk=float(assessed["Risk_Score_%"].max()) if n_a else None,
        # only meaningful when OK windows were logged too (by default the monitor logs flagged ones only)
        flag_ratio=(n_fl / n_a) if (n_a and has_ok) else None,
        compliance=(1 - n_fl / n_a) if (n_a and has_ok) else None,
    )

    drivers = ""
    if n_fl:
        try:
            z = zscores(assessed)
            if not z.empty:
                mz = z[(assessed["Status"] == "FLAGGED").reindex(z.index, fill_value=False)].mean()
                drivers = insights._join(insights._phrase(f, v) for f, v in insights._top(mz, 3).items())
        except Exception:
            drivers = ""        # a missing scaler file must not stop the report

    range_text = f"{d_from:%b %d, %Y} to {d_to:%b %d, %Y}"
    prot = protect(sel, anonymize, mask, salt)

    # --- flagged log (most recent first)
    def _t(x, fmt):
        return x.strftime(fmt) if pd.notna(x) else "-"
    rows = []
    for idx in fl.sort_values("Timestamp", ascending=False).index[:max_rows]:
        r, p = sel.loc[idx], prot.loc[idx]
        rows.append((_t(r["Timestamp"], "%Y-%m-%d %H:%M"), str(p["Session_ID"]), str(p["App_Used"]),
                     _t(r["Window_Start"], "%H:%M:%S"), _t(r["Window_End"], "%H:%M:%S"),
                     f"{r['Risk_Score_%']:.1f}%", LEVELS[risk_level(r)][0]))

    hours = (fl["Hour"].value_counts().reindex(range(24), fill_value=0).astype(int).tolist()
             if n_fl and "Hour" in fl else [0] * 24)

    # --- per-session summary
    if n_a:
        g = assessed.groupby("Session_ID").agg(
            App_Used=("App_Used", lambda s: s.mode().iat[0] if not s.mode().empty else ""),
            Windows=("Status", "size"),
            Flagged=("Status", lambda s: int((s == "FLAGGED").sum())),
            Avg_Risk=("Risk_Score_%", "mean"), Peak_Risk=("Risk_Score_%", "max"),
            First_Window=("Window_Start", "min"), Last_Window=("Window_End", "max")).reset_index()
        g["Flag_Rate_%"] = (g["Flagged"] / g["Windows"] * 100).round(1) if has_ok else np.nan
        g[["Avg_Risk", "Peak_Risk"]] = g[["Avg_Risk", "Peak_Risk"]].round(1)
        g = protect(g.sort_values("Peak_Risk", ascending=False), anonymize, mask, salt)
        g = g.rename(columns={"Avg_Risk": "Avg_Risk_%", "Peak_Risk": "Peak_Risk_%"})
    else:
        g = pd.DataFrame(columns=["Session_ID", "App_Used", "Windows", "Flagged", "Avg_Risk_%", "Peak_Risk_%",
                                  "First_Window", "Last_Window", "Flag_Rate_%"])

    # --- full telemetry export
    levels = sel.apply(risk_level, axis=1).map(lambda k: LEVELS[k][0]) if len(sel) else pd.Series(dtype=object)
    tele = prot.assign(Risk_Level=levels)
    cols = LOG_COLS + ["Risk_Level"] + ([] if mask else [f for f in FEATS if f in tele.columns])
    tele = tele[cols]

    privacy = ["Session IDs anonymized" if anonymize else "Session IDs shown as logged"]
    if mask:
        privacy.append("application names and raw telemetry masked")
    return dict(
        ref=f"PACE-AUD-{generated:%Y-%m%d-%H%M}", generated=generated,
        range_text=range_text, time_text=f"{t_from:%H:%M} - {t_to:%H:%M}",
        shift_text=shift if shift in SHIFTS else "All shifts",
        sessions_text=f"{len(sessions)} selected" if sessions else "All sessions",
        apps_text=("All applications" if not apps else
                   (f"{len(apps)} selected" if mask else ", ".join(apps))),
        privacy_text="; ".join(privacy), anonymize=anonymize, mask=mask,
        stats=stats, drivers=drivers, summary=_summary_text(stats, range_text, drivers),
        rows=rows, n_flagged_total=n_fl, hours=hours, sessions=g, telemetry=tele)


# ------------------------------------------------------------------ on-screen print preview
def preview_html(rep, n_rows=8):
    e, s = html.escape, rep["stats"]
    meta = [("Report Ref ID", rep["ref"]), ("Generated", f"{rep['generated']:%b %d, %Y %H:%M}"),
            ("Date range", rep["range_text"]), ("Shift / time", f"{rep['shift_text']}, {rep['time_text']}"),
            ("Sessions", rep["sessions_text"]), ("Applications", rep["apps_text"]),
            ("Privacy", rep["privacy_text"]), ("Risk threshold", f"{s['threshold']:.0f}%")]
    meta_html = "".join(f'<div class="pp-meta"><b>{e(k)}</b><span>{e(v)}</span></div>' for k, v in meta)

    kpis = [("Flagged windows", str(s["flagged"])), ("Sessions affected", str(s["sessions_affected"])),
            ("Highest risk", "-" if s["peak_risk"] is None else f"{s['peak_risk']:.1f}%"),
            ("Compliance rate", _pct(s["compliance"]))]
    kpi_html = "".join(f'<div class="pp-kpi"><small>{e(k)}</small><b>{e(v)}</b></div>' for k, v in kpis)

    if rep["rows"]:
        head = "".join(f"<th>{h}</th>" for h in ("Logged", "Session", "App", "Start", "End", "Risk", "Level"))
        body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rep["rows"][:n_rows])
        more = rep["n_flagged_total"] - min(len(rep["rows"]), n_rows)
        foot = f'<div class="pp-more">+ {more} more flagged window(s) in the full report</div>' if more > 0 else ""
        table = f'<table class="pp-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{foot}'
    else:
        table = '<div class="pp-more">No windows were flagged in this selection.</div>'

    peak = max(rep["hours"]) or 1
    bars = "".join(f'<div class="pp-bar" title="{h:02d}:00 - {n} flag(s)" style="height:{max(n / peak * 100, 3):.0f}%;'
                   f'{"" if n else "opacity:.25;"}"></div>' for h, n in enumerate(rep["hours"]))
    return ('<div class="paper">'
            f'<div class="pp-band"><span>{e(INSTITUTION)}</span><span>OFFICIAL AUDIT REPORT</span></div>'
            '<div class="pp-body">'
            f'<div class="pp-eyebrow">{e(SYSTEM)}</div><div class="pp-title">{e(TITLE)}</div>'
            f'<div class="pp-metagrid">{meta_html}</div>'
            f'<div class="pp-h">1. Executive operational summary</div><p>{e(rep["summary"])}</p>'
            f'<div class="pp-kpis">{kpi_html}</div>'
            f'<div class="pp-h">2. Flagged encoding sessions audit log</div>{table}'
            f'<div class="pp-h">3. Operational chronology &amp; fatigue distribution</div>'
            f'<div class="pp-chart">{bars}</div><div class="pp-axis"><span>00h</span><span>12h</span><span>23h</span></div>'
            f'<div class="pp-foot">{e(FOOTER)}</div>'
            '</div></div>')


# ------------------------------------------------------------------ PDF
def build_pdf(rep, max_rows=500):
    try:
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, PageTemplate, Paragraph,
                                        Spacer, Table, TableStyle, KeepTogether)
    except ImportError as exc:
        raise ImportError("PDF export needs the 'reportlab' package: pip install reportlab") from exc

    esc = html.escape
    MAROON, GOLD, CREAM = colors.HexColor("#56151F"), colors.HexColor("#C9A25B"), colors.HexColor("#F5F1E6")
    INK, OLIVE = colors.HexColor("#3B0F16"), colors.HexColor("#8B7A4A")
    PW, PH = A4
    LM = 18 * mm
    W = PW - 2 * LM

    base = ParagraphStyle("b", parent=getSampleStyleSheet()["Normal"], fontName="Helvetica", fontSize=8.5,
                          leading=12.5, textColor=INK)
    cell = ParagraphStyle("c", parent=base, fontSize=7, leading=9, wordWrap="CJK")
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, wordWrap="LTR")
    title = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=MAROON)
    eyebrow = ParagraphStyle("e", parent=base, fontSize=7, leading=9, textColor=OLIVE)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=MAROON,
                        spaceBefore=12, spaceAfter=2)
    small = ParagraphStyle("s", parent=base, fontSize=7.5, leading=10, textColor=OLIVE)

    def chrome(c, doc):
        c.saveState()
        c.setFillColor(MAROON)
        c.rect(0, PH - 14 * mm, PW, 14 * mm, stroke=0, fill=1)
        c.setFillColor(GOLD)
        c.rect(0, PH - 15 * mm, PW, 1 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(LM, PH - 8.6 * mm, INSTITUTION)
        c.drawRightString(PW - LM, PH - 8.6 * mm, "OFFICIAL AUDIT REPORT")
        c.setStrokeColor(GOLD)
        c.line(LM, 14 * mm, PW - LM, 14 * mm)
        c.setFillColor(OLIVE)
        c.setFont("Helvetica", 6.5)
        c.drawString(LM, 10 * mm, FOOTER)
        c.drawRightString(PW - LM, 10 * mm, f"{rep['ref']}  |  Page {doc.page}")
        c.restoreState()

    s = rep["stats"]
    story = [Paragraph(esc(SYSTEM).upper(), eyebrow), Paragraph(esc(TITLE), title), Spacer(1, 6)]

    # meta block
    def kv(k, v):
        return [Paragraph(f"<b>{esc(k)}</b>", cell), Paragraph(esc(v), cell)]
    meta = [kv("Report Ref ID", rep["ref"]) + kv("Generated", f"{rep['generated']:%b %d, %Y %H:%M}"),
            kv("Date range", rep["range_text"]) + kv("Shift / time", f"{rep['shift_text']}, {rep['time_text']}"),
            kv("Sessions", rep["sessions_text"]) + kv("Applications", rep["apps_text"]),
            kv("Privacy", rep["privacy_text"]) + kv("Risk threshold", f"{s['threshold']:.0f}%")]
    mt = Table(meta, colWidths=[24 * mm, 63 * mm, 24 * mm, W - 111 * mm])
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CREAM), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#E8E0CC")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [mt, Paragraph("1. EXECUTIVE OPERATIONAL SUMMARY", h2),
              HRFlowable(width="100%", thickness=0.8, color=GOLD, spaceAfter=5),
              Paragraph(esc(rep["summary"]), base), Spacer(1, 8)]

    kp = [("FLAGGED WINDOWS", str(s["flagged"])), ("SESSIONS AFFECTED", str(s["sessions_affected"])),
          ("HIGHEST RISK SCORE", "-" if s["peak_risk"] is None else f"{s['peak_risk']:.1f}%"),
          ("COMPLIANCE RATE", _pct(s["compliance"]))]
    kt = Table([[Paragraph(f'<font size="6.5" color="#8B7A4A">{k}</font><br/>'
                           f'<font size="15" color="#56151F"><b>{esc(v)}</b></font>', base) for k, v in kp]],
               colWidths=[W / 4] * 4)
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CREAM), ("LINEABOVE", (0, 0), (-1, 0), 1.6, MAROON),
                            ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    story += [kt, Paragraph("2. FLAGGED ENCODING SESSIONS AUDIT LOG", h2),
              HRFlowable(width="100%", thickness=0.8, color=GOLD, spaceAfter=5)]

    if rep["rows"]:
        hdr = [Paragraph(h, head) for h in ("Logged", "Session ID", "App", "Window start", "Window end",
                                              "Risk", "Level")]
        data = [hdr] + [[Paragraph(esc(c), cell) for c in r] for r in rep["rows"][:max_rows]]
        ft = Table(data, colWidths=[27 * mm, 44 * mm, 24 * mm, 20 * mm, 20 * mm, 15 * mm, W - 150 * mm],
                   repeatRows=1)
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MAROON),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF6EA")]),
                                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E8E0CC")),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
        story.append(ft)
        if rep["n_flagged_total"] > len(rep["rows"][:max_rows]):
            story.append(Paragraph(f"Showing the {len(rep['rows'][:max_rows])} most recent of "
                                   f"{rep['n_flagged_total']} flagged windows. Export the telemetry CSV for the "
                                   "full list.", small))
    else:
        story.append(Paragraph("No windows were flagged in this selection.", base))

    sec3 = [Paragraph("3. OPERATIONAL CHRONOLOGY &amp; FATIGUE DISTRIBUTION", h2),
            HRFlowable(width="100%", thickness=0.8, color=GOLD, spaceAfter=5)]
    counts = rep["hours"]
    H = 58 * mm
    d = Drawing(W, H)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 30, 30, W - 40, H - 52
    bc.data = [counts]
    bc.bars[0].fillColor, bc.bars[0].strokeColor = MAROON, GOLD
    bc.categoryAxis.categoryNames = [f"{h:02d}" for h in range(24)]
    bc.categoryAxis.labels.fontSize = bc.valueAxis.labels.fontSize = 6
    bc.categoryAxis.labels.fontName = bc.valueAxis.labels.fontName = "Helvetica"
    bc.valueAxis.valueMin = 0
    if max(counts) <= 10:
        bc.valueAxis.valueMax, bc.valueAxis.valueStep = max(max(counts), 1), 1
    d.add(bc)
    d.add(String(W / 2, 8, "Hour of day the window started", fontName="Helvetica", fontSize=6.5, fillColor=OLIVE, textAnchor="middle"))
    d.add(String(0, H - 8, "Flagged windows", fontName="Helvetica", fontSize=6.5, fillColor=OLIVE))
    sec3.append(d)
    story.append(KeepTogether(sec3))      # heading never ends up alone at the bottom of a page
    if rep["n_flagged_total"] >= 3 and max(counts):
        story.append(Paragraph(f"Flagged windows concentrate around {counts.index(max(counts)):02d}:00 "
                               f"({max(counts)} of {rep['n_flagged_total']}).", base))

    story += [Paragraph("4. METHOD &amp; PRIVACY NOTES", h2),
              HRFlowable(width="100%", thickness=0.8, color=GOLD, spaceAfter=5)]
    notes = [f"A window is flagged when its modelled risk score is above the {s['threshold']:.0f}% threshold. "
             "The score comes from the trained cognitive-fatigue model, using typing-timing measures and the "
             "participant's short wellness survey answers.",
             "Compliance rate = share of assessed windows at or below the threshold. Windows typed below the "
             f"minimum typing rate are not assessed ({s['not_assessed']} in this selection).",
             "The audit log holds session tags and typing-timing measures only; key content is not recorded. "
             f"{rep['privacy_text']}.",
             "This report is a prompt to double-check entries. It is not an evaluation of any person."]
    story += [Paragraph(f"- {esc(n)}", base) for n in notes]

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=LM, topMargin=24 * mm, bottomMargin=19 * mm,
                          title=f"{TITLE} - {rep['ref']}", author="PACE", subject="Supervisor audit report")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(LM, 19 * mm, W, PH - 43 * mm, id="f",
                                                              leftPadding=0, rightPadding=0, topPadding=0,
                                                              bottomPadding=0)], onPage=chrome)])
    doc.build(story)
    return buf.getvalue()