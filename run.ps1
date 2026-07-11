# Curador — full run: audit memory + vault + storage + cloud check
# Usage: .\run.ps1 [-Summary] [-Write] [-Project "Nome"]
param([switch]$Summary, [switch]$Write, [string]$Project)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CFG = Join-Path $DIR 'curador.json'

if (-not (Test-Path $CFG)) {
    Write-Error "curador.json not found. Copy curador.example.json to curador.json and fill in your paths."
    exit 1
}

$cfg = Get-Content $CFG -Raw | ConvertFrom-Json
# NOTE: the -replace expression MUST be parenthesized on its own — inside a static
# method call's parens, PowerShell treats a bare comma as an argument separator, so
# `Method($x -replace 'a', $b)` silently splits into two arguments instead of one.
$memory   = if ($cfg.memory)   { [System.Environment]::ExpandEnvironmentVariables(($cfg.memory   -replace '~', $env:USERPROFILE)) } else { '' }
$vault    = if ($cfg.vault)    { [System.Environment]::ExpandEnvironmentVariables(($cfg.vault     -replace '~', $env:USERPROFILE)) } else { '' }
$snapshot = if ($cfg.snapshot) { [System.Environment]::ExpandEnvironmentVariables(($cfg.snapshot  -replace '~', $env:USERPROFILE)) } else { '' }

# Built with @() + += throughout, never `$x = if (...) { @('one-item') } else { @() }` —
# that ternary form silently collapses a SINGLE-element array to a bare string (a real
# PowerShell footgun), which then splats character-by-character instead of as one arg.
$extraArgs = @()
if ($Summary) { $extraArgs += '--summary' }
if ($Write)   { $extraArgs += '--write' }

$snapArgs = @()
if ($snapshot) { $snapArgs += '--snapshot'; $snapArgs += $snapshot }

# --project-scope filters audit_kb.py's stale/split/size-rule/misplacement findings
# down to paths containing this substring — see "Project wrap-up" in SKILL.md.
$scopeArgs = @()
if ($Project) { $scopeArgs += '--project-scope'; $scopeArgs += $Project }

if ($memory) {
    Write-Host '=== memory ==='
    python "$DIR\scripts\audit_kb.py" --path $memory @snapArgs @scopeArgs @extraArgs
    Write-Host ''
}
if ($vault) {
    Write-Host '=== vault ==='
    python "$DIR\scripts\audit_kb.py" --path $vault @snapArgs @scopeArgs @extraArgs
    Write-Host ''

    Write-Host '=== storage ==='
    # storage_audit.py scopes by walking <vault>/<project> directly (--project), and has
    # no --write (it never fixes anything, only reports) — so it gets its own arg list.
    $storageArgs = @()
    if ($Project) { $storageArgs += '--project'; $storageArgs += $Project }
    if ($Summary) { $storageArgs += '--summary' }
    python "$DIR\scripts\storage_audit.py" --vault $vault @snapArgs @storageArgs
    Write-Host ''

    Write-Host '=== cloud ==='
    python "$DIR\scripts\check_cloud_health.py" --vault $vault
}
