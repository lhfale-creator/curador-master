# Curador — full run: audit memory + vault + cloud check
# Usage: .\run.ps1 [--summary] [--write]
param([switch]$Summary, [switch]$Write)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CFG = Join-Path $DIR 'curador.json'

if (-not (Test-Path $CFG)) {
    Write-Error "curador.json not found. Copy curador.example.json to curador.json and fill in your paths."
    exit 1
}

$cfg = Get-Content $CFG -Raw | ConvertFrom-Json
$memory  = if ($cfg.memory)   { [System.Environment]::ExpandEnvironmentVariables($cfg.memory -replace '~', $env:USERPROFILE) } else { '' }
$vault   = if ($cfg.vault)    { [System.Environment]::ExpandEnvironmentVariables($cfg.vault  -replace '~', $env:USERPROFILE) } else { '' }
$snapshot= if ($cfg.snapshot) { [System.Environment]::ExpandEnvironmentVariables($cfg.snapshot -replace '~', $env:USERPROFILE) } else { '' }

$extraArgs = @()
if ($Summary) { $extraArgs += '--summary' }
if ($Write)   { $extraArgs += '--write' }
$snapArgs = if ($snapshot) { @('--snapshot', $snapshot) } else { @() }

if ($memory) {
    Write-Host '=== memory ==='
    python "$DIR\scripts\audit_kb.py" --path $memory @snapArgs @extraArgs
    Write-Host ''
}
if ($vault) {
    Write-Host '=== vault ==='
    python "$DIR\scripts\audit_kb.py" --path $vault @snapArgs @extraArgs
    Write-Host ''
    Write-Host '=== cloud ==='
    python "$DIR\scripts\check_cloud_health.py" --vault $vault
}
