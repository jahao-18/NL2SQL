$ErrorActionPreference = "Continue"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

# The current Codex shell can expose both Path and PATH. PowerShell's process
# launcher treats them as duplicate keys, so keep the canonical Windows one.
[Environment]::SetEnvironmentVariable("PATH", $null, "Process")

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 *>&1 |
  Tee-Object -FilePath ".\uvicorn-lan.combined.log" -Append
