<#
  run_all.ps1 - rebuild everything from the raw datasets (Windows PowerShell).

  Usage (from the repository root):
      powershell -ExecutionPolicy Bypass -File .\run_all.ps1            # full pipeline
      powershell -ExecutionPolicy Bypass -File .\run_all.ps1 -SkipDb    # without PostgreSQL steps
      powershell -ExecutionPolicy Bypass -File .\run_all.ps1 -WithMqtt  # also run the MQTT demo (~70 s)

  Prerequisites: Python 3.11+, Git, Graphviz, PostgreSQL 16/17 with a database and user
  described in .env (copy .env.example). About 2 GB free disk for the raw datasets.
#>
param([switch]$SkipDb, [switch]$WithMqtt)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($name, [scriptblock]$cmd) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    $t = Get-Date
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $name (exit $LASTEXITCODE)" }
    Write-Host ("    done in {0:N0} s" -f ((Get-Date) - $t).TotalSeconds) -ForegroundColor DarkGray
}

if (-not (Test-Path .venv)) {
    Step "Create virtual environment" { python -m venv .venv }
}
$py = ".\.venv\Scripts\python.exe"
Step "Install requirements" { & $py -m pip install -q -r python\requirements.txt }
if (-not $SkipDb -and -not (Test-Path .env)) { throw "Create .env from .env.example first (PostgreSQL connection), or use -SkipDb" }

Step "00 Download datasets"            { & $py python\00_download_datasets.py }
Step "01 Verify datasets"              { & $py python\01_verify_datasets.py }
Step "02 Reference tables"             { & $py python\02_build_reference_tables.py }
Step "03 Edge features (Bosch)"        { & $py -W ignore python\03_extract_edge_features.py }
Step "04 Calibrate derivation models"  { & $py -W ignore python\04_calibrate_models.py }
Step "05 Build fleet table"            { & $py python\05_build_fleet_table.py }
Step "Part A data volume"              { & $py python\part_a_data_volume.py }
if (-not $SkipDb) {
    Step "06 Load PostgreSQL"          { & $py python\06_load_postgres.py }
    Step "07 Run SQL queries"          { & $py python\07_run_sql.py }
}
Step "ML: Bosch anomaly"               { & $py -W ignore python\ml\ml_bosch_anomaly.py }
Step "ML: UMich tool wear"             { & $py -W ignore python\ml\ml_umich_toolwear.py }
Step "ML: Azure failure 24 h"          { & $py -W ignore python\ml\ml_azure_failure.py }
Step "ML: AI4I failure modes"          { & $py -W ignore python\ml\ml_ai4i_failure_modes.py }
Step "ML: business impact (INR)"       { & $py -W ignore python\ml\business_impact.py }
Step "Part C decision matrix + cost"   { & $py -W ignore python\part_c_decision_matrix.py }
Step "Diagrams"                        { & $py python\make_diagrams.py }
if ($WithMqtt -and -not $SkipDb) {
    Step "MQTT store-and-forward demo" { & $py -W ignore python\edge\run_mqtt_demo.py }
}
Write-Host "`nAll steps completed. Start the dashboard with:  cd dashboard; ..\.venv\Scripts\streamlit.exe run app.py" -ForegroundColor Green
