# ⚡ LeetCode Autonomous Agentic AI Coder

An intelligent, autonomous **ReAct (Reasoning - Action - Observation)** agent that connects to your LeetCode account, discovers unsolved problems by difficulty and language preference (Python 3 / Java), reasons through optimal algorithms using **Google Gemini Flash**, writes code, runs testcases on LeetCode's runner, auto-corrects on failures, submits to official LeetCode evaluation, and archives solutions to **PostgreSQL (Neon / Supabase)**.

---

## 🌟 Key Features

1. **Autonomous ReAct Engine:**
   - **Reasoning (Thought):** Evaluates algorithmic complexity (time & space), detects potential bottlenecks (e.g. $O(N^2)$ vs $O(N)$), and handles edge cases (empty collections, duplicates, negative numbers, overflow).
   - **Action:** Generates optimal, working code strictly conforming to LeetCode class/method definitions.
   - **Observation:** Executes code on LeetCode's runner (`/interpret_solution/`), inspects outputs against expected answers, and iterates on any failure.
   - **Official Submission:** Submits code via LeetCode's `/submit/` API and polls official verdict (`Accepted`, runtime & memory percentiles).

2. **LeetCode Account Integration:**
   - Seamless connection using your session cookie (`LEETCODE_SESSION`) and CSRF token (`csrftoken`).
   - Profile check displays your username, avatar, and account status.
   - Filters out already-solved questions (`status == 'ac'`) and premium-locked questions.

3. **Multi-Language & Difficulty Selection:**
   - Select difficulty: **Easy**, **Medium**, or **Hard**.
   - Select preferred language: **Python 3** or **Java**.
   - Choose any question from the unsolved list or click **"🔥 Auto-Solve 1"** for hands-free one-click solving!

4. **Persistent Database (PostgreSQL - Neon / Supabase):**
   - Stores question number, title, difficulty, language, solution code, runtime, memory, submission ID, and timestamp.
   - Works natively with **Neon.tech** and **Supabase** free PostgreSQL tiers.
   - Includes automatic local **SQLite fallback** (`leetcode_records.db`) if no PostgreSQL URL is configured, ensuring zero setup friction.

5. **Streamlit Fullstack UI:**
   - **Agent Workspace:** Real-time visual cards showing step-by-step agent reasoning, active code editor with syntax highlighting, and runner test outputs.
   - **Completed Questions:** Archive table and cards with metrics, search/filter, LeetCode links, and 1-click CSV/JSON export.
   - **Settings & Deploy Guide:** In-app credential management and setup instructions.

---

## 🚀 Quick Start

### 1. Clone & Install Dependencies

```bash
git clone <your-repo-url>
cd "LeetCode- Coder"

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment Secrets

Copy `.env.example` to `.env` or set values directly in the Streamlit UI sidebar:

```ini
# Gemini API Key (Get from https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# Model selection (Recommended free models)
GEMINI_MODEL=gemini-2.5-flash

# LeetCode Account Authentication (from browser DevTools)
LEETCODE_SESSION=your_leetcode_session_cookie
LEETCODE_CSRFTOKEN=your_csrftoken_cookie

# PostgreSQL Database URL (Neon / Supabase)
# Leave blank to automatically use local SQLite
DATABASE_URL=postgresql://user:pass@ep-xyz.region.neon.tech/neondb?sslmode=require
```

### 3. Run the Streamlit Application

```bash
python -m streamlit run app.py
```

Then open your browser at `http://localhost:8501`.

---

## ☁️ Deploy on Render

Create a **Web Service** for this repository with:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python render_start.py` (or `npm start`)
- **Runtime:** Python

The launcher binds Streamlit to `0.0.0.0` and Render's assigned `PORT` (using
`8501` locally when `PORT` is not set), and configures Streamlit for Render's
reverse proxy so the app's WebSocket connection can be established. Add
`GEMINI_API_KEY`, `GEMINI_MODEL`, `LEETCODE_SESSION`, `LEETCODE_CSRFTOKEN`, and
`DATABASE_URL` as environment variables in the Render dashboard rather than
committing them to the repository.

---

## 🔑 How to Get Your Credentials

### 1. Google Gemini API Key (Free)
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key**.
3. Copy the key and paste it into `.env` or the sidebar settings.

### 2. LeetCode Session Cookies (30 Seconds)
1. Open [LeetCode](https://leetcode.com) in Chrome, Firefox, or Edge and log into your account.
2. Press `F12` (or Right-Click -> **Inspect**).
3. Go to the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox).
4. In the left panel, expand **Cookies** -> `https://leetcode.com`.
5. Copy the values of:
   - `LEETCODE_SESSION`
   - `csrftoken`
6. Paste them into the sidebar or `.env`. Click **"🔍 Check LeetCode Status"** to verify connection.

### 3. Free PostgreSQL Database (Neon or Supabase)
- **Neon.tech (Instant & Free):**
  1. Sign up at [neon.tech](https://neon.tech).
  2. Create a new database project.
  3. Copy the Connection URI (e.g. `postgresql://user:password@ep-xyz.region.neon.tech/neondb?sslmode=require`).
  4. Paste into `DATABASE_URL`.
- **Supabase:**
  1. Sign up at [supabase.com](https://supabase.com).
  2. Create a project -> Project Settings -> Database -> Connection URI.

---

## ☁️ Free Deployment on Streamlit Community Cloud

1. Push your repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io).
3. Select your repository and set `app.py` as the entrypoint.
4. Go to **Advanced Settings -> Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "your_key"
   GEMINI_MODEL = "gemini-2.5-flash"
   LEETCODE_SESSION = "your_session"
   LEETCODE_CSRFTOKEN = "your_csrftoken"
   DATABASE_URL = "postgresql://..."
   ```
5. Click **Deploy**!

---

## 📂 Project Architecture

```
LeetCode- Coder/
├── app.py                # Streamlit Frontend (Workspace, Completed, Settings tabs)
├── agent.py              # Autonomous ReAct Agent with Gemini API
├── leetcode_client.py    # LeetCode GraphQL & REST API Client (Run, Submit, Question scraper)
├── database.py           # SQLAlchemy Database Manager (Neon/Supabase/SQLite)
├── requirements.txt      # Production dependencies
├── .env.example          # Environment variables template
├── .env                  # Local secret storage
└── README.md             # Documentation
```
