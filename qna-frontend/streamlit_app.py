# streamlit_app.py


import streamlit as st
import requests
from typing import List, Dict
from datetime import datetime
import pandas as pd
import json
import html

st.set_page_config(page_title="Tiny Q&A (Gemini)", layout="centered", initial_sidebar_state="collapsed")


DEFAULT_BACKEND = "http://127.0.0.1:8000"

if "backend_url" not in st.session_state:
    st.session_state.backend_url = DEFAULT_BACKEND

if "history" not in st.session_state:
    st.session_state.history: List[Dict] = []

if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

# ensure q_input in session_state so examples can set it
if "q_input" not in st.session_state:
    st.session_state.q_input = ""

# -------------------- Custom CSS --------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined');
      .material-symbols-outlined {
        font-variation-settings:
        'FILL' 0,
        'wght' 400,
        'GRAD' 0,
        'opsz' 48;
        font-size: 48px;
        color: #007bff;
      }

      .main-card { border-radius: 12px; padding: 18px; box-shadow: 0 6px 22px rgba(0,0,0,0.06); }
      .answer-box { background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%); padding: 16px; border-radius: 8px; }
      .meta { color: #6c757d; font-size: 0.9rem; }
      .example-btn { margin-right: 8px; margin-bottom: 6px; }
      .small-muted { color: #6c757d; font-size: 0.85rem; }
      .history-item { padding: 10px; border-radius: 8px; background: #ffffff; box-shadow: 0 1px 4px rgba(15,15,15,0.03); margin-bottom: 10px; }
      .hero { display: flex; align-items: center; gap: 14px; }
      .hero h1 { margin: 0; font-size: 26px; }
      .hero .icon { display:flex; align-items:center; justify-content:center; width:60px; height:60px;
                    background:#e9f2ff; border-radius:50%; }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------- Sidebar (hidden settings) --------------------
with st.sidebar.expander("⚙️ Settings & Backend", expanded=False):
    st.markdown("**Backend URL** (change if needed)")
    st.session_state.backend_url = st.text_input("Backend URL", value=st.session_state.backend_url)
    if st.button("Check backend"):
        try:
            r = requests.get(f"{st.session_state.backend_url.rstrip('/')}/health", timeout=5)
            if r.ok:
                st.success("Backend reachable ✓")
            else:
                st.error(f"Backend responded: {r.status_code}")
        except Exception as e:
            st.error(f"Error: {e}")

# -------------------- Header / Hero --------------------
st.markdown(
    """
    <div class="hero">
        <div class="icon">
            <span class="material-symbols-outlined">forum</span>
        </div>
        <div>
            <h1>Tiny Q&A — Gemini</h1>
            <div class="small-muted">Ask anything. Smart answers powered by Google Gemini — saved to your FastAPI backend.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown("---")

# -------------------- Example quick-questions --------------------
st.markdown("**Try an example**")
examples = [
    "What is Python?",
    "Explain REST APIs in 2 sentences.",
    "How does PostgreSQL differ from MySQL?",
    "Give a one-paragraph summary of transformers."
]

# We'll track if user clicked an example and should auto-ask
ask_now = False
picked_example = None

cols = st.columns(len(examples))
for i, ex in enumerate(examples):
    if cols[i].button(ex, key=f"ex_{i}", help=f"Try: {ex}"):
        st.session_state.q_input = ex
        ask_now = True
        picked_example = ex

# -------------------- Input area (no form to avoid rerun issues) --------------------
q_input = st.text_area("Your question", height=120, placeholder="Type your question here...", key="q_input")
ask_button = st.button("Ask Gemini")

# If user clicked example, or clicked Ask button, perform the request
if ask_button or ask_now:
    q = (st.session_state.q_input or "").strip()
    if not q:
        st.error("Please type a question.")
    else:
        endpoint = f"{st.session_state.backend_url.rstrip('/')}/ask"
        try:
            with st.spinner("Thinking... contacting Gemini..."):
                resp = requests.post(endpoint, json={"question": q}, timeout=40)
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "").strip()
                now = datetime.utcnow().isoformat() + "Z"
                st.session_state.history.insert(0, {"question": q, "answer": answer, "time": now})
                st.session_state.last_answer = answer
                st.success("Answer received ✅")
            else:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text
                st.error(f"Backend error {resp.status_code}: {body}")
        except requests.RequestException as e:
            st.error(f"Request failed: {e}")

# -------------------- Latest answer --------------------
if st.session_state.last_answer:
    st.markdown("### Latest answer")
    latest = st.session_state.history[0]
    st.markdown(f"**Q:** {html.escape(latest['question'])}")
    st.markdown(f"<div class='answer-box'>{latest['answer']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-muted'>Received: {latest['time']}</div>", unsafe_allow_html=True)

# -------------------- History + utilities --------------------
st.markdown("---")
st.markdown("## History (session)")

cols = st.columns([3, 1])
with cols[0]:
    if not st.session_state.history:
        st.info("No history yet — ask something above.")
    else:
        for row in st.session_state.history[:50]:
            st.markdown(f"<div class='history-item'>"
                        f"<div class='small-muted'>{row['time']}</div>"
                        f"<div><strong>Q:</strong> {html.escape(row['question'])}</div>"
                        f"<div style='margin-top:6px;'><strong>A:</strong> {row['answer']}</div>"
                        f"</div>", unsafe_allow_html=True)
with cols[1]:
    if st.button("Clear history"):
        st.session_state.history = []
        st.session_state.last_answer = None
        st.success("History cleared")
    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history)
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="qna_history.csv", mime="text/csv")

st.markdown("---")
st.markdown("Made with ❤️ using Streamlit + Gemini + FastAPI")
