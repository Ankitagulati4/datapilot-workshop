# Module 00 — Setup (10 min)

> Goal: every laptop runs `.\run.ps1` and gets a Streamlit page on `localhost:8501`.

## What you'll do
1. Get a free Groq API key
2. Make sure `uv` is installed (we need `uvx` to launch MCP servers)
3. `pip install -r requirements.txt`
4. Run the Day-0 empty app

## Steps

### 1. Groq key (free)
- Visit https://console.groq.com → **API Keys** → create key
- Copy `.env.example` → `.env`
- Paste your key:  `GROQ_API_KEY=gsk_...`

### 2. `uv` / `uvx`
```powershell
uv --version
```
If you see "command not found", `run.ps1` will install it for you on first launch — or do it now:
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### 3. Python deps
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Build the demo database (one-time)
```powershell
python data/build_shopflow.py
```
You should see `data/shopflow.db` appear (~800 customers, 4 000 orders).

### 5. Launch the empty app
```powershell
.\run.ps1
```

## ✅ CHECK
- Browser opens `http://localhost:8501`
- Page title: **🛠️ DataPilot — let's build it**
- Sidebar shows the build progress checklist

If anything failed, fix it now — Module 01 builds on top of this.

## To check the rows 
import sqlite3, pathlib, sys

db = pathlib.Path("data/shopflow.db")
if not db.exists():
    sys.exit("data/shopflow.db not found - run: python data/build_shopflow.py")

con = sqlite3.connect(db)
for t in ["customers", "products", "orders", "order_items",
          "returns", "support_tickets", "web_sessions"]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:<18} {n:>6}")

## To run streamlit app
streamlit run student/app/streamlit_app.py