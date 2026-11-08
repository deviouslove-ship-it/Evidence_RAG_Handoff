<#
  Evidence RAG - mo ung dung web de test giao dien (du lieu thu nghiem 100 van ban).
  File nay ASCII de chay dung tren Windows PowerShell 5.1. Khong ghi mat khau o day.

  start  : bat PostgreSQL, Ollama, may chu web+API, roi mo trinh duyet.
  stop   : tat may chu web+API, Ollama va PostgreSQL (du lieu giu nguyen).
  status : xem dang chay hay khong.

  Duong dan lay tu vi tri file nay. Thu muc cai dat (Programs\EvidenceRAG) lay tu bien moi truong
  EVIDENCE_PROGRAMS_ROOT, neu khong co thi dung thu muc Programs cung o dia voi du an.
#>
param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [int]$Port = 8000,
    [string]$Database = 'evidence_rerank_eval',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repo = $PSScriptRoot
$programs = $env:EVIDENCE_PROGRAMS_ROOT
if ([string]::IsNullOrWhiteSpace($programs)) { $programs = Join-Path (Split-Path -Qualifier $repo) 'Programs' }
$erag = Join-Path $programs 'EvidenceRAG'
$pgBin = Join-Path $erag 'postgresql\18.6\bin'
$pgData = Join-Path $erag 'data\postgres-dev'
$pgPasswordFile = Join-Path $erag 'secrets\postgres-dev.password'
$python = Join-Path $erag 'backend-venv\Scripts\python.exe'
$ollama = Join-Path $erag 'tools\ollama\ollama.exe'
$ollamaModels = Join-Path $erag 'models\ollama'
$docStore = Join-Path $erag 'data\rerank-eval\document-store'
$webRoot = Join-Path $repo 'frontend\dist'
$logDir = Join-Path $erag 'audit'
# OCR (optional): newest Tesseract under <Programs>\EvidenceRAG\tools\tesseract\<version>.
$ocrExe = Get-ChildItem -Path (Join-Path $erag 'tools\tesseract') -Filter 'tesseract.exe' -Recurse -Depth 1 -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
$pgPort = 55432
$ollamaPort = 11434
$url = "http://127.0.0.1:$Port/"

function Test-Port([int]$p) {
    $c = New-Object Net.Sockets.TcpClient
    try { $c.Connect('127.0.0.1', $p); return $true } catch { return $false } finally { $c.Close() }
}
function Wait-Port([int]$p, [int]$seconds) {
    for ($i = 0; $i -lt $seconds -and -not (Test-Port $p); $i++) { Start-Sleep -Seconds 1 }
    return (Test-Port $p)
}
function Get-Health {
    try { return Invoke-RestMethod -Uri "${url}health" -TimeoutSec 3 } catch { return $null }
}
function Stop-Backend([int]$p) {
    # The venv launcher and the real server both carry the uvicorn command line; match on it
    # (not only on the listening socket) so nothing is left behind.
    $found = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match "--port $p(\s|$)" })
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    $ids = @($found | ForEach-Object { $_.ProcessId }) + $owners | Sort-Object -Unique
    foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    for ($i = 0; $i -lt 10 -and (Test-Port $p); $i++) { Start-Sleep -Milliseconds 500 }
    return $ids.Count
}

if ($Action -eq 'status') {
    Write-Host ("PostgreSQL ({0}): {1}" -f $pgPort, $(if (Test-Port $pgPort) { 'dang chay' } else { 'dung' }))
    Write-Host ("Ollama ({0}):     {1}" -f $ollamaPort, $(if (Test-Port $ollamaPort) { 'dang chay' } else { 'dung' }))
    $h = Get-Health
    Write-Host ("Ung dung ({0}):   {1}" -f $Port, $(if ($h -and $h.status -eq 'ok') { "dang chay - $url" } else { 'dung' }))
    return
}

if ($Action -eq 'stop') {
    $stopped = Stop-Backend $Port
    Write-Host ("Da tat may chu ung dung ({0} tien trinh)." -f $stopped)
    Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Da tat Ollama."
    if (Test-Port $pgPort) {
        & (Join-Path $pgBin 'pg_ctl.exe') stop -D $pgData -m fast -w -t 60 | Out-Null
        Write-Host "Da tat PostgreSQL (du lieu duoc giu nguyen)."
    }
    return
}

# ---- start ----
foreach ($needed in @($python, (Join-Path $pgBin 'pg_ctl.exe'), $pgPasswordFile, (Join-Path $webRoot 'index.html'))) {
    if (-not (Test-Path -LiteralPath $needed)) { throw "Thieu: $needed" }
}
if (-not (Test-Path -LiteralPath $docStore)) { throw "Thieu kho tai lieu thu nghiem: $docStore" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "[1/4] PostgreSQL..."
if (-not (Test-Port $pgPort)) {
    $pgArgs = "start -D `"$pgData`" -o `"-h 127.0.0.1 -p $pgPort`" -l `"$(Join-Path $logDir 'postgres-test-app.log')`" -t 60"
    Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList $pgArgs -WindowStyle Hidden
    if (-not (Wait-Port $pgPort 60)) { throw "PostgreSQL khong khoi dong duoc. Xem $(Join-Path $logDir 'postgres-test-app.log')" }
    Start-Sleep -Seconds 2
}

Write-Host "[2/4] Ollama (embedding va mo rong tu khoa)..."
if (Test-Path -LiteralPath $ollama) {
    if (-not (Test-Port $ollamaPort)) {
        $env:OLLAMA_MODELS = $ollamaModels
        $env:OLLAMA_HOST = "127.0.0.1:$ollamaPort"
        Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir 'ollama-test-app.out.log') `
            -RedirectStandardError (Join-Path $logDir 'ollama-test-app.err.log')
        if (-not (Wait-Port $ollamaPort 30)) { Write-Host "  Canh bao: Ollama khong len. Tim kiem theo nghia se khong chay." }
    }
    if (Test-Port $ollamaPort) {
        # load the embedding model now so the first search is not slow
        try {
            $body = @{ model = 'qwen3-embedding:0.6b'; prompt = 'khoi dong' } | ConvertTo-Json -Compress
            Invoke-RestMethod -Uri "http://127.0.0.1:$ollamaPort/api/embeddings" -Method Post -Body $body `
                -ContentType 'application/json' -TimeoutSec 90 | Out-Null
        } catch { Write-Host "  Canh bao: chua nap duoc model embedding." }
    }
} else {
    Write-Host "  Canh bao: khong thay Ollama; tim kiem theo nghia se khong chay."
}

Write-Host "[3/4] May chu web va API (cong $Port)..."
$health = Get-Health
if (-not ($health -and $health.status -eq 'ok')) {
    if (Test-Port $Port) { throw "Cong $Port dang bi chuong trinh khac dung. Doi cong: ung-dung-test.ps1 -Port 8100" }
    $pgPassword = (Get-Content -LiteralPath $pgPasswordFile -Raw).Trim()
    $env:DATABASE_URL = "postgresql://evidence_dev_admin:$([uri]::EscapeDataString($pgPassword))@127.0.0.1:$pgPort/$Database"
    $env:EVIDENCE_PROGRAMS_ROOT = $programs
    $env:EVIDENCE_DOCUMENT_STORE_ROOT = $docStore
    $env:EVIDENCE_WEB_ROOT = $webRoot
    $env:AI_OPERATING_MODE = 'LOCAL'
    $env:DEV_ALLOW_IN_MEMORY_STORE = 'false'
    $env:PYTHONPATH = Join-Path $repo 'backend'
    $env:PYTHONIOENCODING = 'utf-8'
    # Keys typed in Admin Portal > AI are kept encrypted (Windows DPAPI) in this folder.
    $env:EVIDENCE_SECRET_STORE_DIR = Join-Path $erag 'secrets\ai-keys'
    if ($ocrExe) { $env:EVIDENCE_OCR_EXECUTABLE = $ocrExe } else { Remove-Item Env:EVIDENCE_OCR_EXECUTABLE -ErrorAction SilentlyContinue }
    foreach ($name in 'EVIDENCE_RERANK_BACKEND', 'EVIDENCE_CROSS_ENCODER_URL', 'EVIDENCE_RERANK_DEFAULT',
        'EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD', 'EVIDENCE_BOOTSTRAP_PASSWORD', 'DEEPSEEK_API_KEY') {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }
    Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', "$Port") `
        -WorkingDirectory (Join-Path $repo 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'test-app-backend.out.log') `
        -RedirectStandardError (Join-Path $logDir 'test-app-backend.err.log')
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        $health = Get-Health
        if ($health -and $health.status -eq 'ok') { break }
    }
    if (-not ($health -and $health.status -eq 'ok')) {
        throw "May chu khong len. Xem $(Join-Path $logDir 'test-app-backend.err.log')"
    }
}

Write-Host "[4/4] Mo trinh duyet..."
if (-not $NoBrowser) { Start-Process $url }

Write-Host ""
Write-Host "UNG DUNG DANG CHAY: $url"
Write-Host "Du lieu thu nghiem: 100 van ban, tim kiem toan dien mac dinh RRF thuan."
Write-Host "Tai khoan: chuyenvien (hoi dap/tim kiem), admin (quan tri), curator (nap van ban), reviewer (duyet)."
Write-Host "Cua so nay co the dong; ung dung van chay. De tat: bam Dung-ung-dung-test.bat"
