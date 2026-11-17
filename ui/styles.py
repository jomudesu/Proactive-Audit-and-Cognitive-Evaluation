import streamlit as st

MAROON, GOLD, CREAM, INK, OLIVE = "#56151F", "#C9A25B", "#F5F1E6", "#3B0F16", "#8B7A4A"
LINE = "rgba(139, 122, 74, 0.45)"      # card / table borders


def apply_styles():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0');

    /* ============ BASE ============ */
    .stApp {{ background:{CREAM}; font-family:'Inter', sans-serif; color-scheme:light; }}
    h1,h2,h3,h4 {{ color:{MAROON} !important; font-weight:700; }}
    div[data-testid="stCaptionContainer"] p {{ color:{OLIVE} !important; font-weight:500; }}
    .stMarkdown p, .stText {{ color:{INK} !important; }}

    /* ============ PAGE LAYOUT (spacing) ============ */
    .block-container, [data-testid="stMainBlockContainer"] {{
        padding: 5.5rem 2.5rem 3rem 2.5rem !important;   /* top clears the fixed header */
        max-width: 100% !important;
    }}
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {{ gap: 1.25rem; }}

    .page-title {{ font-size:2.4rem; font-weight:800; line-height:1.15; color:{MAROON}; margin:0 0 .35rem 0; letter-spacing:-0.01em; }}
    .page-sub   {{ font-size:1.05rem; color:{INK}; margin:0; }}

    /* ============ TOP HEADER ============ */
    header[data-testid="stHeader"] {{ background:{MAROON}; }}
    header[data-testid="stHeader"] * {{ color:{CREAM} !important; }}
    header[data-testid="stHeader"] svg {{ fill:{CREAM} !important; }}

    /* ============ SIDEBAR ============ */
    section[data-testid="stSidebar"] {{ background:{MAROON}; border-right:2px solid {GOLD}; }}
    section[data-testid="stSidebar"] > div:first-child {{ padding-top:1rem !important; }}
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding:1rem 1.25rem 2rem 1.25rem; }}
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap:.75rem; }}

    section[data-testid="stSidebar"] * {{ color:{CREAM} !important; -webkit-text-fill-color:{CREAM} !important; }}
    section[data-testid="stSidebar"] .brand small {{ color:{GOLD} !important; -webkit-text-fill-color:{GOLD} !important; }}
    section[data-testid="stSidebar"] hr {{ border-color:rgba(201,162,91,.35); margin:.5rem 0 1rem 0; }}

    .brand {{ font-weight:800; font-size:2rem; line-height:1; margin:0 0 .25rem 0 !important; }}
    .brand small {{ display:block; font-weight:400; font-size:.8rem; margin-top:5px; }}

    /* Sidebar navigation buttons */
    section[data-testid="stSidebar"] a {{
        display:flex; align-items:center; gap:12px; min-height:56px; box-sizing:border-box;
        border:1px solid rgba(201,162,91,.3); border-radius:12px;
        margin-bottom:.5rem; padding:14px 18px; transition:all .2s; text-decoration:none;
        font-size:1.05rem; font-weight:500;
    }}
    section[data-testid="stSidebar"] a:hover {{ background:rgba(255,255,255,.1); border-color:{GOLD}; }}
    section[data-testid="stSidebar"] a[aria-current="page"] {{ background:rgba(255,255,255,.14); border-color:{GOLD}; font-weight:700; }}

    /* ============ SCROLLBARS (visible slider inside scrollable cards) ============ */
    [data-testid="stMain"] * {{ scrollbar-width:thin; scrollbar-color:{GOLD} #EFE7D3; }}
    [data-testid="stMain"] *::-webkit-scrollbar {{ width:10px; height:10px; }}
    [data-testid="stMain"] *::-webkit-scrollbar-track {{ background:#EFE7D3; border-radius:8px; }}
    [data-testid="stMain"] *::-webkit-scrollbar-thumb {{ background:{GOLD}; border-radius:8px; border:2px solid #EFE7D3; }}
    [data-testid="stMain"] *::-webkit-scrollbar-thumb:hover {{ background:{MAROON}; }}

    /* ============ CARDS ============ */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background:#FFFFFF; border:1.5px solid {LINE}; border-radius:14px;
        padding:18px 20px; box-shadow:0 4px 10px rgba(86,21,31,.08);
    }}
    .card-title {{ font-size:1.15rem; font-weight:700; color:{INK}; margin:0 0 14px 0; line-height:1.2; }}
    .insp {{ font-size:1rem; line-height:1.7; color:{INK}; }}
    .conclusion {{ margin-top:14px; padding:14px 18px; background:#FBF6EA; border-left:4px solid {GOLD};
                   border-radius:8px; color:{INK}; font-size:1rem; line-height:1.55; }}
    .conclusion .note {{ margin-top:8px; font-size:.8rem; color:{OLIVE}; }}
    .empty {{ color:{OLIVE}; font-size:.95rem; padding:24px 0; text-align:center; }}

    /* ============ KPI CARDS ============ */
    .kpi {{
        display:flex; align-items:center; justify-content:space-between; gap:16px;
        height:96px; box-sizing:border-box; padding:0 22px; overflow:hidden;
        background:#FFFFFF; border:1.5px solid {LINE}; border-radius:12px;
        box-shadow:0 4px 10px rgba(86,21,31,.08);
    }}
    .kpi > div:first-child {{ min-width:0; }}
    .kpi-label {{ font-size:.95rem; font-weight:500; color:{INK}; margin-bottom:6px; line-height:1.2; }}
    .kpi-value {{ font-size:2rem; font-weight:800; color:{MAROON}; line-height:1.05; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .kpi-value.sm {{ font-size:1.45rem; line-height:1.3; }}   /* long text values, e.g. "IKI Variance ↑" */
    .kpi-icon  {{ flex:0 0 56px; width:56px; height:56px; border-radius:50%; background:#F3EAD6;
                  display:flex; align-items:center; justify-content:center; }}
    .kpi-icon span {{
        font-family:'Material Symbols Outlined'; font-size:30px; line-height:1; color:{GOLD};
        font-feature-settings:'liga'; -webkit-font-feature-settings:'liga';
        text-transform:none; letter-spacing:normal; white-space:nowrap; direction:ltr;
    }}

    /* ============ FLAGGED SESSIONS TABLE ============ */
    .pace-wrap {{ width:100%; }}   /* no own scroller: the card scrolls, so the header can stay sticky */
    .pace-table {{ width:100%; min-width:720px; table-layout:fixed; border-collapse:separate; border-spacing:0; }}
    .pace-table th {{
        position:sticky; top:-18px; z-index:2;   /* -18px = the card's top padding, so the header sits flush with the card edge */
        background:{MAROON}; color:#FFFFFF !important; -webkit-text-fill-color:#FFFFFF;
        font-size:.82rem; font-weight:600; text-align:left; padding:14px 12px; white-space:nowrap;
    }}
    .pace-table th:first-child {{ border-radius:12px 0 0 12px; padding-left:16px; }}
    .pace-table th:last-child  {{ border-radius:0 12px 12px 0; }}
    .pace-table td {{
        font-size:.82rem; color:{INK} !important; padding:14px 12px; vertical-align:middle;
        border-bottom:1px solid #E8E0CC; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
    }}
    .pace-table td:first-child {{ padding-left:16px; }}
    .pace-table thead + tbody tr:first-child td {{ border-top:6px solid #FFFFFF; }}
    .pace-table tbody tr:hover td {{ background:{CREAM}; }}
    .pace-table .c {{ text-align:center; }}

    /* Status badges: every state has a dark-on-light or light-on-dark pair (WCAG AA+) */
    .pace-badge {{
        display:inline-block; min-width:84px; box-sizing:border-box; padding:5px 12px;
        white-space:nowrap; border-radius:999px; font-size:.75rem; font-weight:600; line-height:1.2; text-align:center;
    }}
    .pace-badge.high  {{ background:{MAROON}; color:#FFFFFF !important; -webkit-text-fill-color:#FFFFFF; }}
    .pace-badge.near  {{ background:#FBE3B0;  color:#6B3E00 !important; -webkit-text-fill-color:#6B3E00; }}
    .pace-badge.low   {{ background:#E3F1E4;  color:#1F5E2A !important; -webkit-text-fill-color:#1F5E2A; }}
    .pace-badge.other    {{ background:#E6C98F;  color:{MAROON} !important;  -webkit-text-fill-color:{MAROON}; }}

    /* ============ TELEMETRY PANEL ============ */
    .tele-row {{ display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid #EEE7D6; font-size:.95rem; }}
    .tele-row span:first-child {{ color:{INK}; }}
    .tele-row span:last-child  {{ font-weight:700; color:{MAROON}; }}

    /* ============ BUTTONS & WIDGET LABELS ============ */
    [data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:600; }}
    [data-testid="stMain"] .stButton button, [data-testid="stMain"] .stDownloadButton button,
    div[role="dialog"] .stButton button, div[role="dialog"] .stDownloadButton button,
    [data-testid="stFormSubmitButton"] button {{
        border:1.5px solid {OLIVE}; border-radius:12px; background:#FFFFFF; color:{INK}; min-height:44px; font-weight:600;
    }}
    [data-testid="stMain"] .stButton button p, [data-testid="stMain"] .stDownloadButton button p,
    div[role="dialog"] button p, [data-testid="stFormSubmitButton"] button p {{ color:inherit !important; }}
    [data-testid="stMain"] .stButton button:hover:not(:disabled), [data-testid="stMain"] .stDownloadButton button:hover:not(:disabled) {{
        border-color:{MAROON}; color:{MAROON}; background:{CREAM};
    }}
    [data-testid="stMain"] .stButton button[kind="primary"], [data-testid="stBaseButton-primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"] {{
        background:{GOLD}; border-color:{OLIVE}; color:{MAROON}; box-shadow:0 3px 8px rgba(86,21,31,.18);
    }}
    [data-testid="stMain"] .stButton button:disabled, [data-testid="stMain"] .stDownloadButton button:disabled {{ opacity:.45; }}
    /* sidebar buttons (e.g. Lock dashboard) match the nav links */
    section[data-testid="stSidebar"] .stButton button {{
        background:transparent; border:1px solid rgba(201,162,91,.3); border-radius:12px; min-height:48px;
    }}
    section[data-testid="stSidebar"] .stButton button:hover {{ background:rgba(255,255,255,.1); border-color:{GOLD}; }}
    [data-testid="stAudio"] {{ display:none; }}           /* alert chime plays without a visible player */

    /* ============ PRINT PREVIEW (Reports page) ============ */
    .paper {{ background:#FFFFFF; border:1px solid {LINE}; border-radius:6px; box-shadow:0 4px 14px rgba(86,21,31,.14);
              overflow:hidden; color:{INK}; font-size:.68rem; line-height:1.45; }}
    .pp-band {{ display:flex; justify-content:space-between; gap:8px; background:{MAROON}; color:#FFFFFF;
                border-bottom:3px solid {GOLD}; padding:7px 12px; font-size:.5rem; font-weight:700; letter-spacing:.03em; }}
    .pp-body {{ padding:12px 14px 14px; }}
    .pp-eyebrow {{ font-size:.55rem; color:{OLIVE}; text-transform:uppercase; letter-spacing:.04em; }}
    .pp-title {{ font-size:1.05rem; font-weight:800; color:{MAROON}; margin:2px 0 8px 0; line-height:1.2; }}
    .pp-metagrid {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; background:#E8E0CC; border:1px solid #E8E0CC; }}
    .pp-meta {{ background:#FBF6EA; padding:4px 7px; display:flex; flex-direction:column; min-width:0; }}
    .pp-meta b {{ font-size:.5rem; color:{OLIVE}; text-transform:uppercase; }}
    .pp-meta span {{ font-size:.62rem; overflow-wrap:anywhere; }}
    .pp-h {{ font-size:.68rem; font-weight:800; color:{MAROON}; text-transform:uppercase; border-bottom:1.5px solid {GOLD};
             margin:12px 0 6px 0; padding-bottom:2px; }}
    .paper p {{ margin:0 0 6px 0; color:{INK} !important; font-size:.64rem; }}
    .pp-kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:5px; margin-top:6px; }}
    .pp-kpi {{ background:#FBF6EA; border-top:2px solid {MAROON}; padding:5px 6px; display:flex; flex-direction:column; }}
    .pp-kpi small {{ font-size:.48rem; color:{OLIVE}; text-transform:uppercase; }}
    .pp-kpi b {{ font-size:.95rem; color:{MAROON}; line-height:1.1; }}
    .pp-table {{ width:100%; border-collapse:collapse; table-layout:fixed; font-size:.52rem; }}
    .pp-table th {{ background:{MAROON}; color:#FFFFFF; font-weight:700; text-align:left; padding:3px 4px; }}
    .pp-table td {{ padding:3px 4px; border-bottom:1px solid #EEE7D6; overflow-wrap:anywhere; }}
    .pp-more {{ font-size:.55rem; color:{OLIVE}; padding:4px 0; }}
    .pp-chart {{ display:flex; align-items:flex-end; gap:2px; height:64px; border-bottom:1px solid {OLIVE}; padding:0 2px; }}
    .pp-bar {{ flex:1; background:{MAROON}; border-top:2px solid {GOLD}; min-height:2px; }}
    .pp-axis {{ display:flex; justify-content:space-between; font-size:.5rem; color:{OLIVE}; }}
    .pp-foot {{ margin-top:14px; padding-top:5px; border-top:1px solid {GOLD}; font-size:.45rem; color:{OLIVE}; }}

    /* ============ TOAST ============ */
    [data-testid="stToast"] {{ background-color:{MAROON}; color:white; border:1px solid {GOLD}; border-radius:12px; padding:14px 18px; min-width:340px; }}
    [data-testid="stToast"] p {{ color:white !important; }}
    </style>
    """, unsafe_allow_html=True)