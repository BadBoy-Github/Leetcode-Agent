import os
import sys

# Allow running directly via `python app.py` by bootstrapping streamlit
if __name__ == "__main__":
    try:
        import streamlit as st
        import streamlit.web.cli as stcli
        if not st.runtime.exists():
            sys.argv = ["streamlit", "run", os.path.abspath(__file__)]
            sys.exit(stcli.main())
    except Exception:
        pass

import streamlit as st
import time
import json
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from dotenv import load_dotenv

# Ensure local modules are found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db, SolvedQuestion
from leetcode_client import LeetCodeClient, LEETCODE_LANGUAGES, normalize_lang_slug, get_prism_highlight
from agent import LeetCodeAgent

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="LeetCode Agentic AI Coder",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Dark mode, glassmorphism, glowing badges)
st.markdown("""
<style>
    /* Global Styles */
    .main-header {
        background: linear-gradient(135deg, #1e1e2f 0%, #111119 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FFA116, #FF6B00, #FFD166);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .sub-title {
        color: #a0aec0;
        font-size: 1.05rem;
        margin-top: 6px;
        margin-bottom: 0;
    }
    
    /* Step Cards */
    .react-step-card {
        background: #181926;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .react-step-card:hover {
        border-color: rgba(255, 161, 22, 0.4);
    }
    .step-header {
        font-weight: 700;
        font-size: 1.1rem;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
    }
    .thought-box {
        background: rgba(147, 51, 234, 0.08);
        border-left: 4px solid #a855f7;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        color: #e2e8f0;
        font-size: 0.95rem;
        line-height: 1.5;
        margin-bottom: 12px;
    }
    .action-box {
        background: rgba(59, 130, 246, 0.08);
        border-left: 4px solid #3b82f6;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        color: #e2e8f0;
        font-size: 0.95rem;
        margin-bottom: 12px;
    }
    .observation-success {
        background: rgba(16, 185, 129, 0.08);
        border-left: 4px solid #10b981;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        color: #a7f3d0;
        font-size: 0.95rem;
    }
    .observation-fail {
        background: rgba(239, 68, 68, 0.08);
        border-left: 4px solid #ef4444;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        color: #fca5a5;
        font-size: 0.95rem;
    }

    /* Badges */
    .badge-easy {
        background-color: rgba(0, 184, 163, 0.2);
        color: #00b8a3;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.82rem;
    }
    .badge-medium {
        background-color: rgba(255, 192, 30, 0.2);
        color: #ffc01e;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.82rem;
    }
    .badge-hard {
        background-color: rgba(255, 55, 95, 0.2);
        color: #ff375f;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.82rem;
    }
    .badge-lang {
        background-color: rgba(59, 130, 246, 0.2);
        color: #60a5fa;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.82rem;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to save variables to .env
def save_env_file(env_vars: Dict[str, str]):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    existing_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    lines_dict = {}
    for line in existing_lines:
        line_s = line.strip()
        if line_s and not line_s.startswith("#") and "=" in line_s:
            k, v = line_s.split("=", 1)
            lines_dict[k.strip()] = v.strip()

    # Update with new values
    for k, v in env_vars.items():
        if v:
            lines_dict[k] = v

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("# LeetCode Agent Configuration\n")
        for k, v in lines_dict.items():
            f.write(f"{k}={v}\n")

# Session state initialization
if "unsolved_questions" not in st.session_state:
    st.session_state.unsolved_questions = []
if "agent_logs" not in st.session_state:
    st.session_state.agent_logs = []
if "last_solved" not in st.session_state:
    st.session_state.last_solved = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# Sidebar Configuration
with st.sidebar:
    st.markdown("### ⚙️ System Settings & Keys")
    
    # 1. Gemini Configuration
    st.markdown("#### 🤖 Gemini Model")
    gemini_key = st.text_input(
        "Gemini API Key",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="Get your free key from https://aistudio.google.com/app/apikey"
    )
    
    gemini_model = st.selectbox(
        "Model Version",
        options=["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"],
        index=0,
        help="Recommended: gemini-3.5-flash-lite or gemini-3.5-flash (free tier enabled)"
    )

    # 2. LeetCode Account Authentication
    st.markdown("#### 🔐 LeetCode Account")
    leetcode_session = st.text_input(
        "LEETCODE_SESSION Cookie",
        value=os.getenv("LEETCODE_SESSION", ""),
        type="password",
        help="Session cookie from LeetCode.com DevTools (Application -> Cookies)"
    )
    
    leetcode_csrf = st.text_input(
        "csrftoken Cookie",
        value=os.getenv("LEETCODE_CSRFTOKEN", ""),
        type="password",
        help="csrftoken cookie from LeetCode.com DevTools"
    )

    # LeetCode status test
    if st.button("🔍 Check LeetCode Status", use_container_width=True):
        client_test = LeetCodeClient(session_cookie=leetcode_session, csrf_token=leetcode_csrf)
        status = client_test.get_user_status()
        if status.get("signed_in"):
            st.success(f"Connected as **{status.get('username')}** 🎉")
            if status.get("avatar"):
                st.image(status.get("avatar"), width=60)
            if status.get("is_premium"):
                st.info("⭐ Premium Member")
        else:
            st.warning("Not logged in. You can still test questions, but login is needed to submit to your profile.")

    # 3. Database Configuration
    st.markdown("#### 🗄️ PostgreSQL Database")
    db_url = st.text_input(
        "DATABASE_URL (Neon / Supabase)",
        value=os.getenv("DATABASE_URL", ""),
        type="password",
        help="PostgreSQL connection string, e.g. postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require"
    )

    # Test DB
    db_instance = get_db(db_url)
    db_status = db_instance.test_connection()
    if db_status.get("is_postgres"):
        st.success("🟢 Connected to PostgreSQL (Neon / Supabase)")
    else:
        st.info("🟡 Using Local SQLite Database (`leetcode_records.db`)")

    # Save settings button
    if st.button("💾 Save Credentials to .env", use_container_width=True):
        save_env_file({
            "GEMINI_API_KEY": gemini_key,
            "GEMINI_MODEL": gemini_model,
            "LEETCODE_SESSION": leetcode_session,
            "LEETCODE_CSRFTOKEN": leetcode_csrf,
            "DATABASE_URL": db_url,
        })
        st.success("Credentials saved to `.env` successfully!")

    st.markdown("---")
    with st.expander("❓ How to get LeetCode Cookies"):
        st.markdown("""
        **30-Second Guide:**
        1. Open [LeetCode.com](https://leetcode.com) and log in.
        2. Press `F12` (or Right-Click -> Inspect).
        3. Go to the **Application** tab (Chrome/Edge) or **Storage** (Firefox).
        4. In the left panel, expand **Cookies** -> `https://leetcode.com`.
        5. Find and copy:
           - `LEETCODE_SESSION`
           - `csrftoken`
        6. Paste them in the fields above!
        """)

# Main Content Header
st.markdown("""
<div class="main-header">
    <h1 class="main-title">⚡ LeetCode Autonomous Agentic AI</h1>
    <p class="sub-title">ReAct (Reasoning - Action - Observation) engine that solves unsolved LeetCode problems in 18+ languages (Python, Java, C++, Go, Rust, etc.), runs testcases, submits directly to LeetCode, and archives solutions to PostgreSQL.</p>
</div>
""", unsafe_allow_html=True)

# Tabs
tab_solver, tab_completed, tab_guide = st.tabs([
    "🚀 Agent Workspace",
    "🏆 Completed Questions",
    "📖 Setup & Deploy Guide"
])

# Initialize clients with current inputs
current_leetcode = LeetCodeClient(session_cookie=leetcode_session, csrf_token=leetcode_csrf)
current_db = get_db(db_url)
current_agent = LeetCodeAgent(
    gemini_api_key=gemini_key,
    model_name=gemini_model,
    leetcode_client=current_leetcode,
    db_manager=current_db
)

# ==========================================
# TAB 1: AGENT WORKSPACE
# ==========================================
with tab_solver:
    col_filters, col_actions = st.columns([2, 1], gap="medium")

    with col_filters:
        st.markdown("#### 🎯 Filter & Select Target Problem")
        c1, c2 = st.columns(2)
        with c1:
            difficulty_choice = st.selectbox(
                "Difficulty Level",
                options=["Easy", "Medium", "Hard"],
                index=0
            )
        with c2:
            lang_options = list(LEETCODE_LANGUAGES.keys())
            language_choice = st.selectbox(
                "Preferred Language",
                options=lang_options,
                index=0,
                help="Choose any programming language supported by LeetCode"
            )
            selected_lang_slug = LEETCODE_LANGUAGES[language_choice]["slug"]

    with col_actions:
        st.markdown("#### ⚡ Quick Actions")
        c_fetch, c_quick = st.columns(2)
        with c_fetch:
            fetch_clicked = st.button("🔄 Fetch Unsolved", use_container_width=True)
        with c_quick:
            quick_solve_clicked = st.button("🔥 Auto-Solve 1", type="primary", use_container_width=True)

    # Fetch unsolved questions whenever language, difficulty, or fetch button is clicked
    current_filter_key = f"{difficulty_choice.upper()}_{selected_lang_slug}"
    should_refetch = (
        fetch_clicked
        or "active_filter_key" not in st.session_state
        or st.session_state.active_filter_key != current_filter_key
        or not st.session_state.unsolved_questions
    )

    if should_refetch:
        with st.spinner(f"Fetching unsolved {difficulty_choice} questions for {language_choice}..."):
            questions = current_leetcode.get_unsolved_questions(
                difficulty=difficulty_choice.upper(),
                preferred_lang=selected_lang_slug,
                limit=30
            )
            # Filter out any questions already present in our database
            solved_slugs = current_db.get_solved_slugs()
            filtered_unsolved = [q for q in questions if q["title_slug"] not in solved_slugs]
            st.session_state.unsolved_questions = filtered_unsolved
            st.session_state.active_filter_key = current_filter_key

    # Display Question Picker
    chosen_question = None
    if st.session_state.unsolved_questions:
        # Build display labels with difficulty badge and language
        display_lang = language_choice  # e.g. "Python 3", "Java", "C++"
        options = {
            f"{q['difficulty']} {display_lang.upper()} ({selected_lang_slug.upper()}) #{q['frontend_id']} {q['title']} Acceptance Rate: {q['ac_rate']}%": q
            for q in st.session_state.unsolved_questions
        }
        selected_key = st.selectbox(
            f"Select an unsolved {difficulty_choice} question ({len(st.session_state.unsolved_questions)} available):",
            options=list(options.keys()),
            index=0
        )
        chosen_question = options[selected_key]

        # Preview problem card
        with st.container():
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 12px 18px; margin-bottom: 14px;">
                <span class="badge-{chosen_question['difficulty'].lower()}">{chosen_question['difficulty']}</span>
                <span class="badge-lang" style="margin-left: 8px;">{display_lang} ({selected_lang_slug})</span>
                <strong style="margin-left: 12px; font-size: 1.05rem;">#{chosen_question['frontend_id']} {chosen_question['title']}</strong>
                <span style="color: #a0aec0; margin-left: 12px;">Acceptance Rate: {chosen_question['ac_rate']}%</span>
                <a href="{chosen_question['url']}" target="_blank" style="margin-left: 12px; color: #FFA116; text-decoration: none;">View on LeetCode ↗</a>
                <div style="margin-top: 6px; font-size: 0.85rem; color: #94a3b8;">Tags: {', '.join(chosen_question['tags']) if chosen_question['tags'] else 'General'}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No unsolved questions loaded yet. Click 'Fetch Unsolved' to query LeetCode.")

    # Launch buttons
    launch_clicked = st.button("🚀 Solve Selected Question", type="primary", use_container_width=True)

    target_to_solve = None
    if quick_solve_clicked and st.session_state.unsolved_questions:
        target_to_solve = st.session_state.unsolved_questions[0]
    elif launch_clicked and chosen_question:
        target_to_solve = chosen_question

    # --- AGENT EXECUTION PROCESS ---
    if target_to_solve:
        if not gemini_key:
            st.error("⚠️ Gemini API Key is required. Please enter your Gemini API Key in the left sidebar.")
        else:
            st.markdown("---")
            st.markdown(f"### 🤖 Agent ReAct Execution: #{target_to_solve['frontend_id']} - {target_to_solve['title']}")
            
            # Real-time event UI container
            live_status = st.empty()
            live_code_area = st.empty()
            logs_container = st.container()

            events_list = []

            def stream_callback(event: Dict[str, Any]):
                events_list.append(event)
                etype = event.get("type")

                # Live status indicator
                if etype == "status":
                    live_status.info(f"⏳ {event.get('message')}")
                elif etype == "info":
                    live_status.markdown(f"ℹ️ *{event.get('message')}*")
                elif etype == "thought":
                    with logs_container:
                        st.markdown(f"""
                        <div class="react-step-card">
                            <div class="step-header">🧠 Step {event.get('step')}: Reasoning (Thought)</div>
                            <div class="thought-box">{event.get('content')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                elif etype == "action":
                    action_type = event.get("action_type")
                    code_text = event.get("code")
                    if code_text:
                        live_code_area.markdown(f"#### 💻 Current Solution ({selected_lang_slug})")
                        live_code_area.code(code_text, language=get_prism_highlight(selected_lang_slug))
                    with logs_container:
                        st.markdown(f"""
                        <div class="react-step-card">
                            <div class="step-header">⚡ Step {event.get('step')}: Action [{action_type}]</div>
                            <div class="action-box">{event.get('content', '')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                elif etype == "observation":
                    is_pass = event.get("passed", False)
                    obs_class = "observation-success" if is_pass else "observation-fail"
                    with logs_container:
                        st.markdown(f"""
                        <div class="react-step-card">
                            <div class="step-header">👁️ Step {event.get('step')}: Observation</div>
                            <div class="{obs_class}">{event.get('content')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        if event.get("details"):
                            st.caption(f"Details: {event.get('details')}")
                elif etype == "success":
                    live_status.success(f"🎉 {event.get('content')}")
                elif etype == "error":
                    live_status.error(f"❌ {event.get('message')}")

            # Run agent loop
            with st.spinner("Agentic AI is reasoning and executing..."):
                start_time = time.time()
                result = current_agent.solve_question(
                    title_slug=target_to_solve["title_slug"],
                    preferred_lang=selected_lang_slug,
                    max_iterations=5,
                    event_callback=stream_callback
                )
                elapsed = round(time.time() - start_time, 2)

            if result.get("success"):
                st.balloons()
                st.success(f"✅ Mission Accomplished in {elapsed}s! Question #{result.get('frontend_id')} has been solved and archived to Database.")
                
                # Update unsolved list to remove solved question
                st.session_state.unsolved_questions = [
                    q for q in st.session_state.unsolved_questions
                    if q["title_slug"] != target_to_solve["title_slug"]
                ]
            else:
                st.error(f"Agent finished without full acceptance: {result.get('error')}")

# ==========================================
# TAB 2: COMPLETED (SOLVED HISTORY)
# ==========================================
with tab_completed:
    st.markdown("### 🏆 Solved Questions Archive")
    st.caption("All questions solved by the Agentic AI and recorded into your PostgreSQL / Neon / Supabase database.")

    # Auto-sync solved questions on first load if authenticated
    if current_leetcode.is_authenticated() and not st.session_state.get("lc_synced_auto"):
        try:
            current_leetcode.sync_solved_with_db(current_db)
            st.session_state.lc_synced_auto = True
        except Exception:
            pass

    # Action buttons & stats header
    c_s1, c_s2 = st.columns([2, 1])
    with c_s1:
        if st.button("🔄 Sync All Solved from LeetCode", type="primary", use_container_width=True):
            with st.spinner("Syncing your complete solved question history from LeetCode..."):
                synced_n = current_leetcode.sync_solved_with_db(current_db)
                if synced_n > 0:
                    st.success(f"Successfully synced {synced_n} question(s) from LeetCode into your Neon database!")
                else:
                    st.info("All solved questions from your LeetCode account are already up-to-date in Neon!")
                time.sleep(1)
                st.rerun()
    with c_s2:
        if st.button("🔄 Refresh History", use_container_width=True):
            st.rerun()

    # Metric stats bar
    stats = current_db.get_stats()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Solved", stats["total"])
    m2.metric("Easy", stats["easy"])
    m3.metric("Medium", stats["medium"])
    m4.metric("Hard", stats["hard"])

    # Show per-language breakdown if any solutions exist
    lang_breakdown = stats.get("lang_breakdown", {})
    if lang_breakdown:
        lang_parts = [f"{lang.upper()}: {count}" for lang, count in sorted(lang_breakdown.items(), key=lambda x: -x[1])]
        st.caption(f"📊 Language Breakdown: {' | '.join(lang_parts)}")

    st.markdown("---")

    # Dynamic available languages from database
    all_raw_records = current_db.get_all_solved()
    discovered_langs = sorted(list({r["language"] for r in all_raw_records if r.get("language")}))
    lang_filter_options = ["All"] + discovered_langs

    # Filter controls
    f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
    with f_col1:
        f_diff = st.selectbox("Filter Difficulty", options=["All", "Easy", "Medium", "Hard"], key="hist_diff")
    with f_col2:
        f_lang = st.selectbox("Filter Language", options=lang_filter_options, key="hist_lang")
    with f_col3:
        search_query = st.text_input("🔍 Search by Title or Question #", placeholder="e.g. Two Sum, Counter, 2620, or 1")

    # Fetch solved rows
    solved_records = current_db.get_all_solved(
        difficulty=None if f_diff == "All" else f_diff,
        language=None if f_lang == "All" else f_lang
    )

    if search_query:
        sq = search_query.strip().lower()
        solved_records = [
            r for r in solved_records
            if sq in r["title"].lower() or sq in str(r["frontend_id"])
        ]

    if not solved_records:
        st.info("No completed questions found in database yet. Run the agent in the Workspace tab to solve your first question!")
    else:
        # Display each solved question as a card
        for rec in solved_records:
            with st.expander(
                f"#{rec['frontend_id']} - {rec['title']} | {rec['difficulty']} | {rec['language'].upper()} | Runtime: {rec['runtime']} | Solved: {rec['solved_at']}",
                expanded=False
            ):
                col_meta1, col_meta2 = st.columns([2, 1])
                with col_meta1:
                    st.markdown(f"""
                    **Difficulty**: `{rec['difficulty']}` | **Status**: `{rec['status']}` | **Language**: `{rec['language']}`  
                    **Runtime**: `{rec['runtime']}` | **Memory**: `{rec['memory']}`  
                    **LeetCode Link**: [https://leetcode.com/problems/{rec['title_slug']}](https://leetcode.com/problems/{rec['title_slug']}/)
                    """)
                with col_meta2:
                    if st.button("🗑️ Remove from DB", key=f"del_{rec['id']}"):
                        current_db.delete_solution(rec["id"])
                        st.rerun()

                if rec.get("notes"):
                    st.markdown(f"**Agent Reasoning & Approach:**\n> {rec['notes']}")

                st.markdown("**Accepted Solution Code:**")
                st.code(rec["code"], language=get_prism_highlight(rec["language"]))

        # Export options
        st.markdown("---")
        df_export = pd.DataFrame(solved_records)
        c_csv, c_json = st.columns(2)
        with c_csv:
            csv_data = df_export.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export as CSV", data=csv_data, file_name="leetcode_solved.csv", mime="text/csv", use_container_width=True)
        with c_json:
            json_data = json.dumps(solved_records, indent=2).encode("utf-8")
            st.download_button("📥 Export as JSON", data=json_data, file_name="leetcode_solved.json", mime="application/json", use_container_width=True)

# ==========================================
# TAB 3: SETUP & DEPLOY GUIDE
# ==========================================
with tab_guide:
    st.markdown("""
    ### 📖 Fullstack Architecture & Deployment Guide

    #### 1. How the Agentic ReAct Engine Works
    1. **Question Discovery:** Programmatically connects to LeetCode's GraphQL API, filters for free, unsolved problems of chosen difficulty (`Easy`, `Medium`, `Hard`) that support your preferred language (Python 3, Java, C++, Go, Rust, JavaScript, TypeScript, and 11 more).
    2. **Reasoning (Thought):** Powered by Google Gemini (e.g. `gemini-2.5-flash`), analyzes time/space constraints, edge-cases (bounds, nulls, negatives), and selects optimal algorithmic strategies.
    3. **Action:** Emits clean, compilable solution code matching the LeetCode template.
    4. **Observation & Run Code:** Executes the code against LeetCode's runner (`/interpret_solution/`). If errors or failed cases occur, the feedback is fed back into the reasoning loop to adjust the code.
    5. **Submission:** Submits code via `/submit/`. Upon receiving `Accepted`, records the question number, title, slug, code, runtime, and memory percentiles into PostgreSQL.

    ---

    #### 2. Free Database Setup (Neon or Supabase)
    You can use any free PostgreSQL database:
    - **Neon.tech (Recommended):**
      1. Go to [Neon.tech](https://neon.tech) and create a free project.
      2. Copy your connection URI (looks like `postgresql://user:pass@ep-xyz.region.neon.tech/neondb?sslmode=require`).
      3. Paste it into the `DATABASE_URL` field in the sidebar or `.env`.
    - **Supabase:**
      1. Go to [Supabase.com](https://supabase.com) and create a new project.
      2. In Project Settings -> Database, copy the URI string.
      3. Paste it into `DATABASE_URL`.
    - *Fallback:* If no URL is provided, the app automatically runs on local SQLite (`leetcode_records.db`) without crashing!

    ---

    #### 3. Free Deployment on Streamlit Community Cloud
    1. Push this project repository to your GitHub account.
    2. Visit [share.streamlit.io](https://share.streamlit.io).
    3. Select your repository and set Main file path to `app.py`.
    4. In **Advanced Settings -> Secrets**, paste your environment variables:
    ```toml
    GEMINI_API_KEY = "AIzaSy..."
    GEMINI_MODEL = "gemini-2.5-flash"
    LEETCODE_SESSION = "your_leetcode_session_cookie"
    LEETCODE_CSRFTOKEN = "your_csrftoken_cookie"
    DATABASE_URL = "postgresql://user:pass@ep-xyz.region.neon.tech/neondb?sslmode=require"
    ```
    5. Click **Deploy**! Your Agentic LeetCode Coder is live on the web!
    """)
