import streamlit as st
from datetime import date, timedelta
from backend.utils import get_df
from ui.components import page_header, card_title, render_custom_table, telemetry_panel, toast_new

CARD_H = 560   # both cards share one height; the table scrolls inside its card (like the dashboard)

def render():
    page_header("Flagged Sessions", "Windows scored above the risk threshold, newest first.")
    
    # Optional: Remove this row if you want a completely clean layout without search/filters
    a, b, c = st.columns([2, 1, 1])
    a.text_input("Search", key="f_q", placeholder="Search flags or sessions...", label_visibility="collapsed")
    b.date_input("From", key="d_from", value=date.today() - timedelta(days=30), label_visibility="collapsed")
    c.date_input("To", key="d_to", value=date.today(), label_visibility="collapsed")

    df = get_df()
    if df is None: return
    
    # Applying session state filters (defaults if not set)
    d_from = st.session_state.get("d_from", date.today() - timedelta(days=30))
    d_to = st.session_state.get("d_to", date.today())
    q = st.session_state.get("f_q", "").strip().lower()
    
    d = df[(df["Timestamp"].dt.date >= d_from) & (df["Timestamp"].dt.date <= d_to)]
    if q:
        d = d[d["Session_ID"].str.lower().str.contains(q, regex=False)
              | d["App_Used"].astype(str).str.lower().str.contains(q, regex=False)]
        
    fl = d[d["Status"] == "FLAGGED"].sort_values("Timestamp", ascending=False).reset_index(drop=True)
    toast_new(fl)

    left, right = st.columns([2.2, 1])
    with left, st.container(border=True, height=CARD_H):
        card_title("Flagged Sessions")
        if fl.empty:
            st.info("No flagged windows in this range.")
            return
        render_custom_table(fl.head(200))
        
    sel = fl.head(50)          # windows that can be opened in the inspection panel
    if st.session_state.get("insp_pick", 0) >= len(sel):
        st.session_state["insp_pick"] = 0

    with right, st.container(border=True, height=CARD_H):
        card_title("Session Inspection")
        pick = st.selectbox("Inspect window", range(len(sel)), key="insp_pick",
                            format_func=lambda i: f"{sel.iloc[i]['Session_ID']}  ·  {sel.iloc[i]['Timestamp']:%H:%M:%S}")
        row = sel.iloc[pick]
        st.markdown("**Session ID**")
        st.code(str(row["Session_ID"]), language=None)      # full ID, with a copy button
        st.markdown(f"**Last:** {row['Timestamp']:%Y-%m-%d %H:%M:%S}")
        st.markdown("**Raw Telemetry**")
        telemetry_panel(row)