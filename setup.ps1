# One-time setup (run from the bankmate-ai folder in PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "`nSetup done. Next: ollama pull qwen2.5:3b-instruct ; then .\run_ingest.ps1" -ForegroundColor Green
