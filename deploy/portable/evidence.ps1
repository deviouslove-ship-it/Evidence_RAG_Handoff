<#
.SYNOPSIS
  Portable launcher for Evidence RAG: PostgreSQL + backend + web app from one folder.
  No installation, no fixed paths, no fixed IP. Everything is resolved from this script's location.

.PARAMETER Action
  start          Start PostgreSQL and the web/API server (first run creates a clean database).
  stop           Stop the web/API server and PostgreSQL.
  status         Show what is running and the addresses to give to users.
  open-firewall  Allow inbound TCP on the web port from the local subnet (needs Administrator).
  close-firewall Remove that rule (needs Administrator).

.PARAMETER BootstrapPassword
  First run only: password (12+ characters) for the four starter accounts. When omitted a random
  one is generated and saved to secrets\first-login.txt.

  Settings live in config\evidence.env. This file is ASCII on purpose (Windows PowerShell 5.1).
#>
param(
    [ValidateSet('start', 'stop', 'status', 'open-firewall', 'close-firewall')]
    [string]$Action = 'start',
    [string]$BootstrapPassword = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = $PSScriptRoot

# The host machine may define variables that would redirect the bundled Python or PostgreSQL
# tools to something else (a system-wide PYTHONHOME, PGHOST, ...). Ignore them for this process.
foreach ($name in 'PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE', 'PYTHONPLATLIBDIR',
    'PYTHONUSERBASE', 'PYTHONOPTIMIZE', 'PYTHONSAFEPATH', 'PYTHONINSPECT', 'PYTHONDEVMODE', 'VIRTUAL_ENV',
    'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPASSFILE', 'PGSERVICE',
    'PGSERVICEFILE', 'PGSYSCONFDIR', 'PGOPTIONS', 'PGDATA', 'PGSSLMODE', 'PGCLIENTENCODING', 'PGLOCALEDIR') {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}

$python = Join-Path $root 'runtime\python\python.exe'
$sitePackages = Join-Path $root 'runtime\site-packages'
$pgBin = Join-Path $root 'runtime\postgresql\bin'
$backendDir = Join-Path $root 'app\backend'
$seedScript = Join-Path $root 'app\scripts\seed_local_runtime.py'
$webRoot = Join-Path $root 'web'
$dataDir = Join-Path $root 'data'
$pgData = Join-Path $dataDir 'postgres'
$docStore = Join-Path $dataDir 'documents'
$logDir = Join-Path $root 'logs'
$secretDir = Join-Path $root 'secrets'
$runDir = Join-Path $root 'run'
$cacheDir = Join-Path $root 'cache\pycache'
$configFile = Join-Path $root 'config\evidence.env'
$pgPassFile = Join-Path $secretDir 'postgres.password'
$firstLoginFile = Join-Path $secretDir 'first-login.txt'
$bootFlag = Join-Path $dataDir '.bootstrapped'
$backendPidFile = Join-Path $runDir 'backend.pid'
$dbName = 'evidence_rag'
$dbUser = 'evidence_admin'

# Keys the package controls itself; a value in evidence.env is ignored for these.
$reservedKeys = @(
    'DATABASE_URL', 'EVIDENCE_DOCUMENT_STORE_ROOT', 'EVIDENCE_WEB_ROOT', 'EVIDENCE_BOOTSTRAP_PASSWORD',
    'EVIDENCE_PROGRAMS_ROOT', 'EVIDENCE_CORPUS_DIR', 'EVIDENCE_SECRET_STORE_DIR', 'DEV_ALLOW_IN_MEMORY_STORE',
    'PYTHONPATH', 'PYTHONHOME', 'PGPASSWORD'
)

function Quote-Arg([string]$Value) {
    if ($Value -match '[\s"]') { return '"' + ($Value -replace '"', '\"') + '"' }
    return $Value
}

function Read-Settings {
    $settings = @{}
    if (Test-Path -LiteralPath $configFile) {
        foreach ($line in Get-Content -LiteralPath $configFile -Encoding UTF8) {
            $text = $line.Trim()
            if ($text -eq '' -or $text.StartsWith('#')) { continue }
            $at = $text.IndexOf('=')
            if ($at -lt 1) { Write-Warning "Ignored line in evidence.env: $text"; continue }
            $key = $text.Substring(0, $at).Trim()
            $value = $text.Substring($at + 1).Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if ($key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { Write-Warning "Ignored key in evidence.env: $key"; continue }
            if ($reservedKeys -contains $key) { Write-Warning "evidence.env cannot set $key (managed by the launcher)."; continue }
            $settings[$key] = $value
        }
    }
    return $settings
}

function Get-Setting($Settings, [string]$Name, [string]$Default) {
    if ($Settings.ContainsKey($Name) -and $Settings[$Name] -ne '') { return $Settings[$Name] }
    return $Default
}

function New-Secret([int]$Length, [string]$Alphabet) {
    $bytes = New-Object byte[] ($Length * 4)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $chars = New-Object char[] $Length
    for ($i = 0; $i -lt $Length; $i++) {
        $chars[$i] = $Alphabet[[int]([BitConverter]::ToUInt32($bytes, $i * 4) % [uint32]$Alphabet.Length)]
    }
    return (-join $chars)
}

function Write-TextFile([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# Runs a tool with output redirected to files. Never uses Start-Process -Wait: a database
# server that the tool starts would keep that wait open forever.
function Invoke-Tool([string]$Exe, [string[]]$Arguments, [string]$LogName) {
    New-Item -ItemType Directory -Force $logDir | Out-Null
    $out = Join-Path $logDir ($LogName + '.out.log')
    $err = Join-Path $logDir ($LogName + '.err.log')
    $argLine = ($Arguments | ForEach-Object { Quote-Arg $_ }) -join ' '
    $proc = Start-Process -FilePath $Exe -ArgumentList $argLine -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $proc.Handle
    $proc.WaitForExit()
    return $proc.ExitCode
}

function Show-LogTail([string]$LogName, [int]$Lines = 15) {
    foreach ($suffix in '.err.log', '.out.log') {
        $path = Join-Path $logDir ($LogName + $suffix)
        if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 0) {
            Write-Host "---- $LogName$suffix (last $Lines lines)"
            Get-Content -LiteralPath $path -Tail $Lines | ForEach-Object { Write-Host "  $_" }
        }
    }
}

function Test-Admin {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PortListening([int]$Port) {
    try { return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop) } catch { return $false }
}

function Get-BackendProcess {
    if (-not (Test-Path -LiteralPath $backendPidFile)) { return $null }
    $pidText = "$(Get-Content -LiteralPath $backendPidFile -Raw)".Trim()
    if ($pidText -notmatch '^\d+$') { return $null }
    $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
    # A recycled PID must not be mistaken for our server: compare the executable path.
    if ($proc -and $proc.Path -eq $python) { return $proc }
    return $null
}

function Test-PgRunning {
    return ((Invoke-Tool (Join-Path $pgBin 'pg_ctl.exe') @('status', '-D', $pgData) 'pg_ctl-status') -eq 0)
}

function Get-LanAddresses {
    try {
        Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
            ForEach-Object { [pscustomobject]@{ Address = $_.IPAddress; Interface = $_.InterfaceAlias } }
    } catch {
        [Net.Dns]::GetHostAddresses([Net.Dns]::GetHostName()) |
            Where-Object { $_.AddressFamily -eq 'InterNetwork' -and $_.ToString() -notmatch '^(127\.|169\.254\.)' } |
            ForEach-Object { [pscustomobject]@{ Address = $_.ToString(); Interface = '' } }
    }
}

function Write-Addresses([string]$ListenHost, [int]$Port) {
    if ($ListenHost -eq '0.0.0.0' -or $ListenHost -eq '::') {
        Write-Host 'Give testers one of these addresses (same network):'
        foreach ($item in (Get-LanAddresses)) {
            Write-Host ("  http://{0}:{1}/   {2}" -f $item.Address, $Port, $item.Interface)
        }
        Write-Host ("  http://{0}:{1}/   (by computer name)" -f $env:COMPUTERNAME, $Port)
        Write-Host ("  http://127.0.0.1:{0}/   (this computer)" -f $Port)
    } else {
        Write-Host ("Listening on http://{0}:{1}/" -f $ListenHost, $Port)
    }
}

function Assert-Package {
    foreach ($required in @(
            $python, (Join-Path $pgBin 'pg_ctl.exe'), (Join-Path $pgBin 'initdb.exe'),
            (Join-Path $pgBin 'postgres.exe'), (Join-Path $pgBin 'psql.exe'),
            (Join-Path $pgBin 'pg_isready.exe'), (Join-Path $backendDir 'app\main.py'),
            $seedScript, (Join-Path $webRoot 'index.html'), $sitePackages)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Package is incomplete, missing: $required"
        }
    }
}

function Start-Stack {
    Assert-Package
    $settings = Read-Settings
    $listenHost = Get-Setting $settings 'EVIDENCE_LISTEN_HOST' '0.0.0.0'
    $httpPort = [int](Get-Setting $settings 'EVIDENCE_HTTP_PORT' '8000')
    $pgPort = [int](Get-Setting $settings 'EVIDENCE_PG_PORT' '55432')
    foreach ($port in $httpPort, $pgPort) {
        if ($port -lt 1024 -or $port -gt 65535) { throw "Port $port is outside 1024-65535." }
    }
    $healthHost = if ($listenHost -eq '0.0.0.0' -or $listenHost -eq '::') { '127.0.0.1' } else { $listenHost }

    foreach ($dir in $dataDir, $docStore, $logDir, $secretDir, $runDir, $cacheDir) {
        New-Item -ItemType Directory -Force $dir | Out-Null
    }

    $existing = Get-BackendProcess
    if ($existing) {
        Write-Host "Already running (process $($existing.Id))."
        Write-Addresses $listenHost $httpPort
        return
    }
    if (Test-PortListening $httpPort) { throw "Port $httpPort is already in use by another program. Change EVIDENCE_HTTP_PORT in config\evidence.env." }

    # ---- PostgreSQL: create a clean cluster on first run ----
    $firstRun = -not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))
    if ($firstRun) {
        Write-Host 'First run: creating a clean database...'
        $dbPassword = New-Secret 32 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        Write-TextFile $pgPassFile $dbPassword
        $rc = Invoke-Tool (Join-Path $pgBin 'initdb.exe') @(
            '-D', $pgData, '-U', $dbUser, '-E', 'UTF8', '--locale=C', '-A', 'scram-sha-256', "--pwfile=$pgPassFile"
        ) 'initdb'
        if ($rc -ne 0) { Show-LogTail 'initdb'; throw 'initdb failed.' }
    }
    if (-not (Test-Path -LiteralPath $pgPassFile)) {
        throw "Database exists but secrets\postgres.password is missing. Restore it from the backup of this folder."
    }
    $dbPassword = "$(Get-Content -LiteralPath $pgPassFile -Raw)".Trim()

    $pgRunning = Test-PgRunning
    if (-not $pgRunning) {
        if (Test-PortListening $pgPort) { throw "Port $pgPort is already in use by another program. Change EVIDENCE_PG_PORT in config\evidence.env." }
        $rc = Invoke-Tool (Join-Path $pgBin 'pg_ctl.exe') @(
            'start', '-D', $pgData, '-l', (Join-Path $logDir 'postgres.log'),
            '-o', "-h 127.0.0.1 -p $pgPort", '-w', '-t', '90'
        ) 'pg_ctl-start'
        if ($rc -ne 0) { Show-LogTail 'pg_ctl-start'; Show-LogTail 'postgres'; throw 'PostgreSQL did not start.' }
    }

    $env:PGPASSWORD = $dbPassword
    try {
        $psql = Join-Path $pgBin 'psql.exe'
        $common = @('-h', '127.0.0.1', '-p', "$pgPort", '-U', $dbUser, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1')
        $rc = Invoke-Tool $psql ($common + @('-tAc', "SELECT 1 FROM pg_database WHERE datname = '$dbName'")) 'psql-check'
        if ($rc -ne 0) { Show-LogTail 'psql-check'; throw 'Cannot connect to PostgreSQL (wrong password in secrets\postgres.password?).' }
        # An empty result file means the database does not exist yet (Get-Content -Raw returns $null).
        $exists = "$(Get-Content -LiteralPath (Join-Path $logDir 'psql-check.out.log') -Raw)".Trim()
        if ($exists -ne '1') {
            $rc = Invoke-Tool $psql ($common + @('-c', "CREATE DATABASE $dbName ENCODING 'UTF8' TEMPLATE template0")) 'psql-create'
            if ($rc -ne 0) { Show-LogTail 'psql-create'; throw "Cannot create database $dbName." }
        }
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }

    # ---- Environment for the backend (settings file first, launcher-owned values last) ----
    foreach ($key in $settings.Keys) {
        if ($settings[$key] -ne '') { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
    }
    # OCR for scanned PDFs is an optional plug-in, not shipped by default.  When an
    # administrator places Tesseract (with its tessdata) under runtime\tesseract, it is used;
    # EVIDENCE_OCR_EXECUTABLE in evidence.env points elsewhere if needed.
    $bundledOcr = Join-Path $root 'runtime\tesseract\tesseract.exe'
    if (-not $env:EVIDENCE_OCR_EXECUTABLE -and (Test-Path -LiteralPath $bundledOcr)) {
        $env:EVIDENCE_OCR_EXECUTABLE = $bundledOcr
    }
    $encodedPassword = [uri]::EscapeDataString($dbPassword)
    $env:DATABASE_URL = "postgresql://${dbUser}:${encodedPassword}@127.0.0.1:${pgPort}/${dbName}"
    $env:EVIDENCE_DOCUMENT_STORE_ROOT = $docStore
    $env:EVIDENCE_SECRET_STORE_DIR = Join-Path $secretDir 'ai-keys'
    $env:EVIDENCE_WEB_ROOT = $webRoot
    $env:DEV_ALLOW_IN_MEMORY_STORE = 'false'
    $env:PYTHONPATH = "$sitePackages;$backendDir"
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONPYCACHEPREFIX = $cacheDir
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'

    # ---- First run: migrations + starter accounts (never approves any document) ----
    if (-not (Test-Path -LiteralPath $bootFlag)) {
        $generated = $false
        if ($BootstrapPassword -eq '') {
            $BootstrapPassword = New-Secret 20 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_'
            $generated = $true
        }
        if ($BootstrapPassword.Length -lt 12) { throw 'BootstrapPassword must have at least 12 characters.' }
        $env:EVIDENCE_BOOTSTRAP_PASSWORD = $BootstrapPassword
        try {
            $rc = Invoke-Tool $python @('-s', $seedScript) 'seed'
        } finally {
            Remove-Item Env:EVIDENCE_BOOTSTRAP_PASSWORD -ErrorAction SilentlyContinue
        }
        if ($rc -ne 0) { Show-LogTail 'seed'; throw 'Database setup failed (see logs\seed.err.log).' }
        Write-TextFile $bootFlag ((Get-Date).ToString('o'))
        $accounts = 'admin (system admin + auditor), curator (uploads sources), reviewer (approves sources), chuyenvien (searches)'
        $created = 0
        try { $created = [int]("$(Get-Content -LiteralPath (Join-Path $logDir 'seed.out.log') -Raw)" | ConvertFrom-Json).users_created } catch { }
        if ($created -eq 0) {
            Write-Host 'Database already had accounts; no starter accounts were created and no password was changed.'
        } elseif ($generated) {
            Write-TextFile $firstLoginFile (
                "Evidence RAG - starter accounts created $((Get-Date).ToString('yyyy-MM-dd HH:mm'))`r`n" +
                "Accounts: admin, curator, reviewer, chuyenvien`r`n" +
                "Password (same for all four): $BootstrapPassword`r`n" +
                "Each account must choose a new password at first login. Delete this file afterwards.`r`n")
            Write-Host ''
            Write-Host "Starter accounts: $accounts"
            Write-Host "Password for all four (saved in secrets\first-login.txt): $BootstrapPassword"
            Write-Host 'Each account is forced to change it at first login.'
            Write-Host ''
        } else {
            Write-Host "Starter accounts created with the password you supplied: $accounts"
        }
    }

    # ---- Backend + web ----
    $proc = Start-Process -FilePath $python -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') `
        -RedirectStandardError (Join-Path $logDir 'backend.err.log') `
        -ArgumentList ((@('-s', '-m', 'uvicorn', 'app.main:create_app', '--factory', '--no-access-log',
                    '--host', $listenHost, '--port', "$httpPort") | ForEach-Object { Quote-Arg $_ }) -join ' ')
    $null = $proc.Handle
    Write-TextFile $backendPidFile "$($proc.Id)"

    $ready = $false
    for ($i = 0; $i -lt 180; $i++) {
        if ($proc.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://${healthHost}:${httpPort}/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        Show-LogTail 'backend' 25
        Remove-Item -LiteralPath $backendPidFile -ErrorAction SilentlyContinue
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
        throw 'The web/API server did not become ready (see logs\backend.err.log).'
    }

    Write-Host 'Evidence RAG is running.'
    Write-Addresses $listenHost $httpPort
    $ruleName = "Evidence RAG (TCP $httpPort)"
    if (($listenHost -eq '0.0.0.0' -or $listenHost -eq '::') -and
        -not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        Write-Host "Other computers may be blocked by the firewall: run open-firewall.cmd once as Administrator."
    }
    Write-Host 'Traffic is plain HTTP. Use only on a trusted network.'
}

function Stop-Stack {
    Assert-Package
    $backend = Get-BackendProcess
    if ($backend) {
        Stop-Process -Id $backend.Id -Force
        Write-Host "Web/API server stopped (process $($backend.Id))."
    } else {
        Write-Host 'Web/API server was not running.'
    }
    Remove-Item -LiteralPath $backendPidFile -ErrorAction SilentlyContinue
    if ((Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION')) -and (Test-PgRunning)) {
        $rc = Invoke-Tool (Join-Path $pgBin 'pg_ctl.exe') @('stop', '-D', $pgData, '-m', 'fast', '-w', '-t', '60') 'pg_ctl-stop'
        if ($rc -ne 0) { Show-LogTail 'pg_ctl-stop'; throw 'PostgreSQL did not stop cleanly.' }
        Write-Host 'PostgreSQL stopped.'
    } else {
        Write-Host 'PostgreSQL was not running.'
    }
}

function Show-Status {
    Assert-Package
    $settings = Read-Settings
    $listenHost = Get-Setting $settings 'EVIDENCE_LISTEN_HOST' '0.0.0.0'
    $httpPort = [int](Get-Setting $settings 'EVIDENCE_HTTP_PORT' '8000')
    $backend = Get-BackendProcess
    $pgRunning = (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION')) -and (Test-PgRunning)
    Write-Host ("Package folder : {0}" -f $root)
    Write-Host ("Database       : {0}" -f $(if ($pgRunning) { 'running' } elseif (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION')) { 'stopped' } else { 'not created yet (first start creates it)' }))
    Write-Host ("Web/API server : {0}" -f $(if ($backend) { "running (process $($backend.Id))" } else { 'stopped' }))
    if ($backend) {
        $healthHost = if ($listenHost -eq '0.0.0.0' -or $listenHost -eq '::') { '127.0.0.1' } else { $listenHost }
        try {
            $health = Invoke-RestMethod -Uri "http://${healthHost}:${httpPort}/health" -TimeoutSec 3
            Write-Host "Health         : $($health.status)"
        } catch { Write-Host 'Health         : no response' }
        Write-Addresses $listenHost $httpPort
    }
    Write-Host ("First login    : {0}" -f $(if (Test-Path -LiteralPath $firstLoginFile) { 'secrets\first-login.txt still exists - delete it after the accounts changed their passwords' } else { 'file not present' }))
}

function Set-FirewallRule([bool]$Open) {
    $settings = Read-Settings
    $httpPort = [int](Get-Setting $settings 'EVIDENCE_HTTP_PORT' '8000')
    $profiles = (Get-Setting $settings 'EVIDENCE_FIREWALL_PROFILE' 'Private,Domain') -split '\s*,\s*'
    $ruleName = "Evidence RAG (TCP $httpPort)"
    if (-not (Test-Admin)) { throw 'Run this as Administrator (right-click the .cmd file > Run as administrator).' }
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($Open) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $httpPort `
            -Action Allow -Profile $profiles -RemoteAddress LocalSubnet | Out-Null
        Write-Host "Firewall rule '$ruleName' created: profiles $($profiles -join ','), local subnet only."
    } else {
        Write-Host "Firewall rule '$ruleName' removed."
    }
}

try {
    switch ($Action) {
        'start' { Start-Stack }
        'stop' { Stop-Stack }
        'status' { Show-Status }
        'open-firewall' { Set-FirewallRule $true }
        'close-firewall' { Set-FirewallRule $false }
    }
} catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($env:EVIDENCE_DEBUG -eq '1') { Write-Host $_.InvocationInfo.PositionMessage; Write-Host $_.ScriptStackTrace }
    exit 1
}
