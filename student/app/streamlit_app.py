"""DataPilot — student starter.

You will grow this file module by module until it matches
`solution/app/streamlit_app.py`. Right now it does nothing useful
and that is on purpose.

Run:  .\\run.ps1
"""
import streamlit as st

st.set_page_config(page_title="DataPilot (student)", page_icon="🛠️", layout="wide")
st.title("🛠️ DataPilot — let's build it")
st.caption("Module 0: empty shell. By Module 11 this is a working SQL+DQ chat app.")

with st.sidebar:
    st.header("Build progress")
    st.info(
        "Follow the MODULE cards in `student/`:\n\n"
        "**Phase 1 — Foundation** (90 min)\n"
        "- MODULE_00_SETUP\n"
        "- MODULE_01_MCP\n"
        "- MODULE_02_CHAT\n"
        "- MODULE_03_GUARDRAILS\n"
        "- MODULE_04_CHARTS\n"
        "- MODULE_05_CONFIG\n\n"
        "**Phase 2 — Platform** (90 min)\n"
        "- MODULE_06_RECAP\n"
        "- MODULE_07_DQ_SERVER\n"
        "- MODULE_08_HEALTH\n"
        "- MODULE_09_SAVED\n"
        "- MODULE_10_COST\n"
        "- MODULE_11_CLAUDE"
    )

st.write("👈 Open `MODULE_00_SETUP.md` and start building.")
st.write("Stuck? Peek at `solution/app/streamlit_app.py` for the finished version.")
