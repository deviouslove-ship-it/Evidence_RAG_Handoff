<#
.SYNOPSIS
  Scoped check run by the Kiro PostFileSave hooks in .kiro/hooks/.
.DESCRIPTION
  Reads the hook event from STDIN (field file_path) or from -File, then checks only that file:
    backend  : ruff check <file>; mypy (strict, backend/pyproject.toml) when the file is under backend/app
    frontend : eslint <file> --max-warnings=0; tsc --noEmit (project-wide, tsc cannot check one file in a project)
  Tools come from EVIDENCE_PROGRAMS_ROOT (or -ProgramsRoot) via configs/development-toolchain.json, the same
  source as scripts/verify.ps1. The global PATH is never used.
  Exit code: 0 = PASS (or file out of scope), 1 = FAIL, 3 = SKIPPED (tool or file missing; reason printed).
  Every run is appended to .agents/hook-logs/kiro-hooks.log (ignored by Git) because Kiro does not show
  PostFileSave output in the chat.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('backend', 'frontend')][string]$Scope,
    [string]$File,
    [string]$ProgramsRoot = $env:EVIDENCE_PROGRAMS_ROOT,
    [int]$MaxOutputLines = 40
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$source = 'manual(-File)'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$logDir = Join-Path $root '.agents/hook-logs'
$logFile = Join-Path $logDir 'kiro-hooks.log'

# 1. Resolve the changed file (hook event on STDIN, or -File).
if (-not $File -and [Console]::IsInputRedirected) {
    try {
        $event = [Console]::In.ReadToEnd() | ConvertFrom-Json
        if ($event.file_path) { $File = [string]$event.file_path }
        if ($event.hook_event_name) { $source = "hook-event:$($event.hook_event_name) session:$($event.session_id)" }
    } catch {
        $File = $null
    }
}
if (-not $File) {
    Write-Output "SKIPPED [$Scope]: no file_path in hook event and no -File argument."
    exit 3
}
$full = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($File)) { $File } else { Join-Path $root $File }))
$rootPrefix = $root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $full.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { exit 0 }
$rel = $full.Substring($rootPrefix.Length).Replace('\', '/')

$inScope = switch ($Scope) {
    'backend' { $rel -match '^backend/.+\.py$' -and $rel -notmatch '(^|/)(__pycache__|\.mypy_cache|\.ruff_cache|\.pytest_cache|[^/]+\.egg-info)/' }
    'frontend' { $rel -match '^frontend/src/.+\.(ts|tsx)$' }
}
if (-not $inScope) { exit 0 }

$results = New-Object System.Collections.Generic.List[object]
function Add-Result([string]$Name, [string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
}

if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
    Add-Result 'file' 'SKIPPED' "file no longer exists: $rel"
}

# 2. Locate tools without the global PATH.
$programs = $null
if ($ProgramsRoot -and [IO.Path]::IsPathRooted($ProgramsRoot) -and (Test-Path -LiteralPath $ProgramsRoot -PathType Container)) {
    $programs = [IO.Path]::GetFullPath($ProgramsRoot).TrimEnd('\', '/')
}

function Find-Tool([string]$Name, [string[]]$ProjectFallbacks) {
    if ($programs) {
        $configPath = Join-Path $root 'configs/development-toolchain.json'
        if (Test-Path -LiteralPath $configPath) {
            $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $relative = [string]$config.executables.$Name
            if ($relative -and -not [IO.Path]::IsPathRooted($relative)) {
                $base = [IO.Path]::GetFullPath((Join-Path $programs $config.root_subdirectory))
                $candidate = [IO.Path]::GetFullPath((Join-Path $base $relative))
                if ($candidate.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and
                    (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                    return $candidate
                }
            }
        }
    }
    foreach ($fallback in $ProjectFallbacks) {
        $candidate = Join-Path $root $fallback
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Invoke-Check([string]$Name, [string]$Exe, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        $lines = @(& $Exe @Arguments 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $text = ($lines -join "`n").Trim()
    if ($text -match 'No module named (ruff|mypy)') {
        Add-Result $Name 'SKIPPED' ("python module missing: " + $Matches[1] + " is not installed in the resolved Python environment")
        return
    }
    $shown = @($lines | Select-Object -First $MaxOutputLines) -join "`n"
    if ($lines.Count -gt $MaxOutputLines) { $shown += "`n... (" + ($lines.Count - $MaxOutputLines) + ' more lines)' }
    if ($code -eq 0) { Add-Result $Name 'PASS' $text } else { Add-Result $Name 'FAIL' ("exit code $code`n$shown") }
}

if ($results.Count -eq 0) {
    if ($Scope -eq 'backend') {
        $python = Find-Tool 'python' @('.venv/Scripts/python.exe', 'backend/.venv/Scripts/python.exe')
        if (-not $python) {
            Add-Result 'ruff' 'SKIPPED' 'Python not found: set EVIDENCE_PROGRAMS_ROOT (configs/development-toolchain.json) or create .venv'
            Add-Result 'mypy' 'SKIPPED' 'Python not found: set EVIDENCE_PROGRAMS_ROOT (configs/development-toolchain.json) or create .venv'
        } else {
            Invoke-Check 'ruff' $python @('-m', 'ruff', 'check', $rel) $root
            if ($rel -match '^backend/app/') {
                Invoke-Check 'mypy' $python @('-m', 'mypy', '--config-file', 'backend/pyproject.toml', $rel) $root
            } else {
                Add-Result 'mypy' 'PASS' 'not applicable: scripts/verify.ps1 type-checks backend/app only'
            }
        }
    } else {
        $node = Find-Tool 'node' @()
        $frontend = Join-Path $root 'frontend'
        $eslint = Join-Path $frontend 'node_modules/eslint/bin/eslint.js'
        $tsc = Join-Path $frontend 'node_modules/typescript/bin/tsc'
        if (-not $node) {
            foreach ($check in 'eslint', 'tsc') {
                Add-Result $check 'SKIPPED' 'node not found: set EVIDENCE_PROGRAMS_ROOT (configs/development-toolchain.json)'
            }
        } elseif (-not (Test-Path -LiteralPath $eslint) -or -not (Test-Path -LiteralPath $tsc)) {
            foreach ($check in 'eslint', 'tsc') {
                Add-Result $check 'SKIPPED' 'frontend/node_modules incomplete (eslint or typescript missing): run pnpm install in frontend/'
            }
        } else {
            Invoke-Check 'eslint' $node @($eslint, ($rel -replace '^frontend/', ''), '--max-warnings=0') $frontend
            Invoke-Check 'tsc' $node @($tsc, '--noEmit', '-p', 'tsconfig.json') $frontend
        }
    }
}

# 3. Report. FAIL outranks SKIPPED, SKIPPED outranks PASS.
$overall = if ($results | Where-Object Status -eq 'FAIL') { 'FAIL' } elseif ($results | Where-Object Status -eq 'SKIPPED') { 'SKIPPED' } else { 'PASS' }
$summary = ($results | ForEach-Object { "$($_.Name)=$($_.Status)" }) -join ' '
$report = New-Object System.Collections.Generic.List[string]
$report.Add("RESULT $overall [$Scope] $rel :: $summary")
foreach ($r in $results) {
    if ($r.Status -ne 'PASS' -and $r.Detail) { $report.Add("  [$($r.Status)] $($r.Name): $($r.Detail)") }
}
$report | ForEach-Object { Write-Output $_ }

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:ss.fffzzz'
Add-Content -LiteralPath $logFile -Encoding UTF8 -Value (@("$stamp $source") + $report)

switch ($overall) { 'PASS' { exit 0 } 'FAIL' { exit 1 } default { exit 3 } }
