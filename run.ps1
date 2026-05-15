# DataPilot - one-shot setup + run.
# Run from the repo root:   .\run.ps1
$ErrorActionPreference = "Stop"

# ----- Pre-flight ------------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is required. Install Python 3.11+ and re-run."
}
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (needed to spawn off-the-shelf MCP servers)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Write-Host "uv installed. Open a new terminal and re-run .\run.ps1" -ForegroundColor Yellow
    exit 0
}

# ----- venv ------------------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating venv..." -ForegroundColor Cyan
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1

Write-Host "Installing requirements..." -ForegroundColor Cyan
pip install -q -r requirements.txt

# ----- env -------------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Created .env - paste your GROQ_API_KEY into it, then re-run." -ForegroundColor Yellow
    notepad .env
    exit 0
}

# ----- demo dataset ----------------------------------------------------------
if (-not (Test-Path "data\shopflow.db")) {
    Write-Host "Building ShopFlow demo dataset..." -ForegroundColor Cyan
    python data\build_shopflow.py
}

# ----- launch ----------------------------------------------------------------
# $env:DATAPILOT_APP can be: "solution" | "student" | a full path to a .py file
$App = $env:DATAPILOT_APP
if (-not $App)              { $App = "student\app\streamlit_app.py" }
elseif ($App -eq "solution") { $App = "solution\app\streamlit_app.py" }
elseif ($App -eq "student")  { $App = "student\app\streamlit_app.py" }
Write-Host "Launching DataPilot ($App)..." -ForegroundColor Green
streamlit run $App
