# DataPilot — Setup Steps

Run all commands from the repo root:
`C:\Users\ankit.ANKITA\Documents\Agentic AI\datapilot-workshop`

---

## 1. Create the virtual environment (sandbox)
```powershell
python -m venv .venv
```
Creates a private `.venv` folder holding an isolated Python just for this project.

## 2. Activate the virtual environment
```powershell
.\.venv\Scripts\Activate.ps1
```
Your prompt should now start with `(.venv)`.

> If you see "running scripts is disabled on this system", run this once, then activate again:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

## 3. Install the requirements
```powershell
pip install -r requirements.txt
```
Installs all project libraries (Streamlit, LangGraph, MCP, ChromaDB, etc.) into the sandbox.

---

## 4. Add your Groq API key
```powershell
Copy-Item .env.example .env
notepad .env
```
Paste your key after `GROQ_API_KEY=` (get one free at https://console.groq.com/keys), then save.

## 5. Build the demo database
```powershell
python data\build_shopflow.py
```
@'
import sqlite3
c = sqlite3.connect("data/shopflow.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("Tables in shopflow.db:")
for t in tables:
    n = c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
    print(f"  {t:16s} {n:>6} rows")
c.close()
'@ | .\.venv\Scripts\python.exe -

## 6. Build the RAG search index (needed from Module 9)
```powershell
python solution\mcp_servers\build_rag_index.py
```

---

## 7. Run the app (always from the repo root)
```powershell
$env:DATAPILOT_APP = "student"
.\run.ps1
```
Opens http://localhost:8501 in your browser. Press `Ctrl+C` to stop.

Use `$env:DATAPILOT_APP = "solution"` to run the finished reference app instead.

---
streamlit run student\app\streamlit_app.py

### Deactivate the sandbox when done
```powershell
deactivate
```
