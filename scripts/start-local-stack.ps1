param(
    [string]$ProgramsRoot = $env:EVIDENCE_PROGRAMS_ROOT,
    [string]$BootstrapPassword = $env:EVIDENCE_BOOTSTRAP_PASSWORD,
    [string]$DatabaseName = 'postgres',
    [switch]$SeedTestCorpus,
    [switch]$LaunchDesktop,
    [switch]$KeepAlive,
    # LAN test mode: the backend listens on all interfaces and serves the built web app
    # (frontend/dist) on the same port, so other machines only open http://<server>:<Port>.
    # PostgreSQL stays on loopback. Plain HTTP: use on a trusted test network only.
    [switch]$Lan,
    [int]$Port = 8000,
    # Needs an elevated shell: allows inbound TCP on -Port from the local subnet only.
    [switch]$OpenFirewall
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ProgramsRoot)) {
    throw 'Set EVIDENCE_PROGRAMS_ROOT or pass -ProgramsRoot.'
}
$rootFull = [IO.Path]::GetFullPath($ProgramsRoot).TrimEnd('\', '/')
$eragRoot = Join-Path $rootFull 'EvidenceRAG'
$pgBin = Join-Path $eragRoot 'postgresql/18.6/bin'
$pgData = Join-Path $eragRoot 'data/postgres-dev'
$pgLog = Join-Path $eragRoot 'audit/postgres-dev.log'
$pwFile = Join-Path $eragRoot 'secrets/postgres-dev.password'
$docStore = Join-Path $eragRoot 'data/document-store'
$pythonExe = Join-Path $eragRoot 'backend-venv/Scripts/python.exe'
$nodeExe = Join-Path $eragRoot 'runtimes/node/node.exe'
$pnpmCjs = Join-Path $eragRoot 'tools/pnpm/node_modules/pnpm/bin/pnpm.cjs'
$desktopExe = Join-Path $eragRoot 'cache/cargo-target/release/vietnamese-evidence-desktop.exe'

New-Item -ItemType Directory -Force $docStore | Out-Null
New-Item -ItemType Directory -Force (Join-Path $eragRoot 'audit') | Out-Null
$requiredTools = @($pythonExe, (Join-Path $pgBin 'pg_ctl.exe'))
if (-not $Lan) { $requiredTools += @($nodeExe, $pnpmCjs) }
foreach ($requiredTool in $requiredTools) {
    if (-not (Test-Path -LiteralPath $requiredTool -PathType Leaf)) {
        throw "Required runtime is missing: $requiredTool"
    }
}
if ($DatabaseName -notmatch '^[a-zA-Z_][a-zA-Z0-9_]*$') { throw 'Invalid database name.' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
$webRoot = Join-Path $projectRoot 'frontend/dist'
if ($Lan -and -not (Test-Path -LiteralPath (Join-Path $webRoot 'index.html') -PathType Leaf)) {
    throw "Web app is not built: $webRoot. Run: node <pnpm.cjs> --dir frontend build"
}
if ($OpenFirewall -and -not $Lan) { throw '-OpenFirewall only applies together with -Lan.' }

$ErrorActionPreference = 'Continue'
$pgReady = & (Join-Path $pgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 -t 1 2>$null
$pgExit = $LASTEXITCODE
if ($pgExit -ne 0) {
    & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData -l $pgLog -o '-h 127.0.0.1 -p 55432' -w -t 15 start | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL could not start; inspect its log.' }
    for ($p = 0; $p -lt 20; $p++) {
        $null = & (Join-Path $pgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 -t 1 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
}
$ErrorActionPreference = 'Stop'
$null = & (Join-Path $pgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 -t 1
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL is not ready.' }

$dbPassword = (Get-Content -LiteralPath $pwFile -Raw).Trim()
$encodedDbPassword = [uri]::EscapeDataString($dbPassword)
$dsn = "postgresql://evidence_dev_admin:${encodedDbPassword}@127.0.0.1:55432/$DatabaseName"

$env:DATABASE_URL = $dsn
$env:EVIDENCE_PROGRAMS_ROOT = $rootFull
$env:EVIDENCE_DOCUMENT_STORE_ROOT = $docStore
if ($SeedTestCorpus) {
    $env:EVIDENCE_CORPUS_DIR = (Join-Path $projectRoot 'evaluation/corpus_public_real')
} else { Remove-Item Env:EVIDENCE_CORPUS_DIR -ErrorAction SilentlyContinue }
$env:EVIDENCE_BOOTSTRAP_PASSWORD = $BootstrapPassword
$env:DEV_ALLOW_IN_MEMORY_STORE = 'false'
if ([string]::IsNullOrWhiteSpace($env:AI_OPERATING_MODE)) { $env:AI_OPERATING_MODE = 'LOCAL' }
$env:PYTHONPATH = (Join-Path $projectRoot 'backend')
$env:PYTHONIOENCODING = 'utf-8'
if ($Lan) { $env:EVIDENCE_WEB_ROOT = $webRoot } else { Remove-Item Env:EVIDENCE_WEB_ROOT -ErrorAction SilentlyContinue }

& $pythonExe (Join-Path $projectRoot 'scripts/seed_local_runtime.py') | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Runtime bootstrap failed. No application was launched.' }
Remove-Item Env:EVIDENCE_BOOTSTRAP_PASSWORD -ErrorAction SilentlyContinue

$listenHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$backendConn = try { @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop) } catch { @() }
if ($Lan -and $backendConn.Count -gt 0 -and -not ($backendConn | Where-Object { $_.LocalAddress -in @('0.0.0.0', '::') })) {
    throw "A backend already listens on loopback only (port $Port). Stop it, then run again with -Lan."
}
if (-not $backendConn) {
    $backendOut = Join-Path $eragRoot 'audit/backend-server.out.log'
    $backendErr = Join-Path $eragRoot 'audit/backend-server.err.log'
    Start-Process -FilePath $pythonExe `
        -ArgumentList @('-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', $listenHost, '--port', $Port) `
        -WorkingDirectory (Join-Path $projectRoot 'backend') `
        -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr | Out-Null
}

$uiConn = try { Get-NetTCPConnection -State Listen -LocalPort 1420 -ErrorAction Stop } catch { $null }
if (-not $Lan -and -not $uiConn) {
    $uiOut = Join-Path $eragRoot 'audit/ui-server.out.log'
    $uiErr = Join-Path $eragRoot 'audit/ui-server.err.log'
    $env:PATH = (Split-Path $nodeExe) + ';' + $env:PATH
    Start-Process -FilePath $nodeExe `
        -ArgumentList @($pnpmCjs, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '1420', '--strictPort') `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') `
        -WindowStyle Hidden `
        -RedirectStandardOutput $uiOut `
        -RedirectStandardError $uiErr | Out-Null
}

$stackReady = $false
for ($i = 0; $i -lt 20; $i++) {
    $backendHealth = try { Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 } catch { $null }
    $uiUrl = if ($Lan) { "http://127.0.0.1:$Port/" } else { 'http://127.0.0.1:1420' }
    $uiHealth = try { Invoke-WebRequest -Uri $uiUrl -UseBasicParsing -TimeoutSec 2 } catch { $null }
    if ($backendHealth.status -eq 'ok' -and $backendHealth.service -eq 'evidence-rag' -and $uiHealth.StatusCode -eq 200) {
        $stackReady = $true
        break
    }
    Start-Sleep -Milliseconds 500
}
if (-not $stackReady) { throw 'Application health check failed; inspect backend/UI logs.' }

if ($LaunchDesktop) {
    if (-not (Test-Path -LiteralPath $desktopExe)) { throw 'Build the desktop executable first.' }
    $existingDesktop = Get-Process -Name 'vietnamese-evidence-desktop' -ErrorAction SilentlyContinue
    if (-not $existingDesktop) {
        Start-Process -FilePath $desktopExe -WorkingDirectory (Split-Path $desktopExe) -WindowStyle Hidden | Out-Null
    }
}

if ($Lan) {
    $ruleName = "Evidence RAG test (TCP $Port)"
    if ($OpenFirewall) {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) { throw 'Open an elevated PowerShell to use -OpenFirewall.' }
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port `
            -Action Allow -Profile Private, Domain -RemoteAddress LocalSubnet | Out-Null
        Write-Host "Firewall rule created: '$ruleName' (Private/Domain profiles, local subnet only)."
    } elseif (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        Write-Host "No firewall rule for TCP $Port. Other machines may be blocked; run once from an elevated shell with -Lan -OpenFirewall."
    }
    Write-Host 'LAN test mode. Give testers one of these addresses:'
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
        ForEach-Object { Write-Host ("  http://{0}:{1}/   ({2})" -f $_.IPAddress, $Port, $_.InterfaceAlias) }
    Write-Host "PostgreSQL stays on 127.0.0.1:55432. Traffic is plain HTTP; use on a trusted network."
} else {
    Write-Host "Stack started: Backend=http://127.0.0.1:$Port | WebPortal=http://127.0.0.1:1420 | PostgreSQL=127.0.0.1:55432"
}

if ($KeepAlive) {
    while ($true) {
        Start-Sleep -Seconds 30
    }
}
