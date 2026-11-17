"""Plain-language summary for the Risk Analysis page: why windows reach / pass the threshold.

Everything here is derived from the audit log, not from the model internals: for each window, every typing
measure is compared with the TRAINING average (z-score, in standard deviations). The measures that deviate
most in flagged windows are reported as the likely drivers.
"""
import numpy as np
import pandas as pd

from backend.utils import LABEL

# feature -> (phrase when ABOVE the training average, phrase when BELOW it)
PLAIN = {
    "IKI_Variance":         ("more irregular timing between keystrokes", "steadier timing between keystrokes"),
    "KPM_Deviation":        ("a more uneven typing pace across the window", "a more even typing pace"),
    "Std_Flight_ms":        ("more variable pauses between keys", "more consistent pauses between keys"),
    "Mean_Flight_ms":       ("longer pauses between keys", "shorter pauses between keys"),
    "Mean_Dwell_ms":        ("keys held down longer", "keys held down for less time"),
    "Std_Dwell_ms":         ("less consistent key-hold times", "more consistent key-hold times"),
    "Backspace_Per_Minute": ("more corrections (backspaces)", "fewer corrections (backspaces)"),
    "Overall_KPM":          ("a faster typing pace", "a slower typing pace"),
}
MIN_SD = 0.5      # a measure must deviate at least this many SD to be called a driver


def _phrase(f, v):
    return PLAIN[f][0] if v > 0 else PLAIN[f][1]


def _join(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (", and " if len(items) > 2 else " and ") + items[-1]


def _top(series, n=3):
    s = series.dropna()
    s = s[s.abs() >= MIN_SD]
    return s.reindex(s.abs().sort_values(ascending=False).index)[:n]


def build_summary(assessed, z, near_margin=10.0):
    """assessed: FLAGGED/OK rows (already filtered). z: utils.zscores(assessed). Returns HTML/markdown."""
    a = assessed.sort_values("Timestamp")
    fl = a["Status"] == "FLAGGED"
    ok = a["Status"] == "OK"
    n, n_fl = len(a), int(fl.sum())
    scores = a["Risk_Score_%"]
    thr_s = a["Threshold_%"].dropna()
    thr = float(thr_s.iloc[-1]) if len(thr_s) else 50.0
    avg, peak = float(scores.mean()), float(scores.max())

    lines = [f"- **Overall:** {n} assessed window{'s' if n != 1 else ''}; **{n_fl}** "
             f"({n_fl / n:.0%}) scored above the **{thr:.0f}%** threshold. "
             f"Average risk is {avg:.1f}% and the peak is {peak:.1f}%."]

    near_below = int((ok & ((thr - scores) <= near_margin)).sum())
    near_above = int((fl & ((scores - thr) <= near_margin)).sum())
    if near_below or near_above:
        parts = []
        if near_below:
            parts.append(f"{near_below} ended just under it")
        if near_above:
            parts.append(f"{near_above} only just passed it")
        lines.append(f"- **Close to the limit:** within {near_margin:.0f} points of the threshold, "
                     f"{' and '.join(parts)}. Small changes in typing behaviour could move these either way.")

    drivers = pd.Series(dtype=float)
    has_z = z is not None and not z.empty
    if n_fl and has_z:
        mz = z[fl.reindex(z.index, fill_value=False)].mean()
        drivers = _top(mz, 3)
        okz = z[ok.reindex(z.index, fill_value=False)].mean() if ok.any() else pd.Series(dtype=float)
        if len(drivers):
            lines.append("- **What pushes windows over the threshold** (average deviation from the training baseline, "
                         "SD = standard deviations):")
            for f, v in drivers.items():
                extra = f"; OK windows average {okz[f]:+.1f} SD" if f in okz and pd.notna(okz[f]) else ""
                lines.append(f"    - **{LABEL[f]}** {v:+.1f} SD: {_phrase(f, v)}{extra}.")
        else:
            lines.append("- **What pushes windows over the threshold:** no single typing measure stands out; the score "
                         "reflects several small shifts happening together.")
    elif not has_z:
        lines.append("- **Typing detail:** the typing measures are not available for these windows (they were logged "
                     "before telemetry was recorded), so only score-based findings are shown.")

    top_idx = scores.idxmax()
    top_row = a.loc[top_idx]
    gap = float(top_row["Risk_Score_%"]) - thr
    where = f"{top_row['Session_ID']}, {float(top_row['Risk_Score_%']):.1f}%"
    if has_z and top_idx in z.index:
        td = _top(z.loc[top_idx], 3)
        if len(td):
            lines.append(f"- **Highest-risk window** ({where}, {abs(gap):.1f} points "
                         f"{'above' if gap > 0 else 'below'} the threshold): driven mainly by "
                         f"{_join(_phrase(f, v) for f, v in td.items())}.")
        else:
            lines.append(f"- **Highest-risk window** ({where}): no single measure stands out.")
    else:
        lines.append(f"- **Highest-risk window:** {where}, {abs(gap):.1f} points "
                     f"{'above' if gap > 0 else 'below'} the threshold.")

    if n_fl >= 3 and "Hour" in a.columns:
        hc = a.loc[fl, "Hour"].value_counts()
        h, c = int(hc.index[0]), int(hc.iloc[0])
        lines.append(f"- **When:** flagged windows concentrate around {h:02d}:00 ({c} of {n_fl}).")

    # ---- conclusion
    if n_fl == 0:
        concl = (f"No window crossed the {thr:.0f}% threshold in this selection. The highest score was "
                 f"{peak:.1f}%, {thr - peak:.1f} points below the limit.")
    else:
        cause = (f"typing shows {_join(_phrase(f, v) for f, v in drivers.head(2).items())}" if len(drivers)
                 else "several typing measures drift from the training baseline at the same time")
        concl = (f"Windows reach the {thr:.0f}% threshold when {cause}. {n_fl} of {n} windows crossed it"
                 + (f", and {near_below} more ended just under the limit and are worth watching." if near_below else "."))
    html_concl = (f'<div class="conclusion"><b>Conclusion.</b> {concl}'
                  '<div class="note">SD = standard deviations from the training-data average. This describes patterns '
                  'linked to higher scores; it is a prompt to double-check entries, not an assessment of the person.'
                  '</div></div>')
    return "\n".join(lines) + "\n\n" + html_concl