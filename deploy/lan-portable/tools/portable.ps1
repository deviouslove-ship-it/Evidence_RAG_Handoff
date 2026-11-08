<#
  Evidence RAG - Windows LAN portable launcher.
  Called by Start-Server.bat, Stop-Server.bat, Backup-Data.bat, Restore-Data.bat.

  Every path is derived from this script's location. Nothing is read from, or written to,
  the machine outside the package folder (no PATH, no registry, no user profile, no services).
  Console text avoids diacritics on purpose so it displays correctly in any console font.
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop', 'status', 'backup', 'restore', 'verify', 'firewall')]
    [string]$Action,
    [string]$Path = '',
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$script:Root = (Split-Path -Parent $PSScriptRoot).TrimEnd('\')
. (Join-Path $PSScriptRoot 'portable-lib.ps1')

# ---- layout ---------------------------------------------------------------------------------
$script:Rt = Join-Path $Root 'runtime'
$script:Py = Join-Path $Rt 'python\python.exe'
$script:SitePackages = Join-Path $Rt 'site-packages'
$script:PgBin = Join-Path $Rt 'postgresql\bin'
$script:OllamaDir = Join-Path $Rt 'ollama'
$script:OllamaExe = Join-Path $OllamaDir 'ollama.exe'
$script:TessDir = Join-Path $Rt 'tesseract'
$script:ModelsDir = Join-Path $Root 'models\ollama'
$script:BackendDir = Join-Path $Root 'app\backend'
$script:WebRoot = Join-Path $Root 'app\web'
$script:DataDir = Join-Path $Root 'data'
$script:PgData = Join-Path $DataDir 'postgres'
$script:DocStore = Join-Path $DataDir 'documents'
$script:OllamaHome = Join-Path $DataDir 'ollama-home'
$script:SeedDir = Join-Path $Root 'seed'
$script:LogDir = Join-Path $Root 'logs'
$script:RunDir = Join-Path $Root 'run'
$script:SecretDir = Join-Path $Root 'secrets'
$script:BackupRoot = Join-Path $Root 'backups'
$script:ConfigFile = Join-Path $Root 'config\evidence.env'
$script:ManifestFile = Join-Path $Root 'MANIFEST.json'
$script:ChecksumFile = Join-Path $Root 'checksums.sha256'
$script:PgPassFile = Join-Path $SecretDir 'postgres.password'
$script:LauncherLog = Join-Path $LogDir 'launcher.log'
$script:DbName = 'evidence_rag'
$script:DbUser = 'evidence_admin'
$script:LegacyOllamaPort = 11434
$script:OllamaPortFile = Join-Path $DataDir '.ollama-port'

$script:ReservedKeys = @(
    'DATABASE_URL', 'EVIDENCE_DOCUMENT_STORE_ROOT', 'EVIDENCE_WEB_ROOT', 'EVIDENCE_BOOTSTRAP_PASSWORD',
    'EVIDENCE_PROGRAMS_ROOT', 'EVIDENCE_CORPUS_DIR', 'EVIDENCE_SECRET_STORE_DIR', 'DEV_ALLOW_IN_MEMORY_STORE',
    'EVIDENCE_OCR_EXECUTABLE', 'EVIDENCE_OCR_TESSDATA', 'PYTHONPATH', 'PYTHONHOME', 'PGPASSWORD', 'OLLAMA_MODELS',
    'OLLAMA_HOST'
)

# ---- output ---------------------------------------------------------------------------------
function Write-Log([string]$Message, [string]$Level = 'INFO') {
    $line = '{0} [{1}] {2}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        New-Item -ItemType Directory -Force $LogDir | Out-Null
        [IO.File]::AppendAllText($LauncherLog, $line + "`r`n", $Utf8NoBom)
    } catch { }
}

function Write-Step([string]$Text) { Write-Host ''; Write-Host $Text -ForegroundColor Cyan; Write-Log $Text }
function Write-Ok([string]$Text) { Write-Host "  [OK]  $Text" -ForegroundColor Green; Write-Log $Text }
function Write-Info([string]$Text) { Write-Host "        $Text"; Write-Log $Text }
function Write-Warn([string]$Text) { Write-Host "  [CANH BAO]  $Text" -ForegroundColor Yellow; Write-Log $Text 'WARN' }
function Write-Fail([string]$Text) { Write-Host "  [LOI]  $Text" -ForegroundColor Red; Write-Log $Text 'ERROR' }

function Show-LogTail([string]$File, [int]$Lines = 12) {
    if ((Test-Path -LiteralPath $File) -and (Get-Item -LiteralPath $File).Length -gt 0) {
        Write-Host "        ---- $(Split-Path -Leaf $File) (cuoi) ----" -ForegroundColor DarkGray
        Get-Content -LiteralPath $File -Tail $Lines -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
    }
}

# ---- environment ---------------------------------------------------------------------------
# Child processes must only see the bundled tools: anything the host machine defines for
# Python, PostgreSQL, Ollama, Tesseract or a proxy is dropped for this process tree.
function Initialize-Environment {
    foreach ($item in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(PG|PYTHON|OLLAMA|VIRTUAL_ENV|CONDA|TESSDATA|TESSERACT|HF_|TRANSFORMERS|TORCH|PIP_|UV_)' })) {
        Remove-Item -LiteralPath ("Env:" + $item.Name) -ErrorAction SilentlyContinue
    }
    foreach ($name in 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy') {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }
    $sys32 = Join-Path $env:SystemRoot 'System32'
    $env:PATH = (@(
            (Join-Path $Rt 'postgresql\bin'), (Join-Path $Rt 'python'), $TessDir, $OllamaDir,
            $sys32, $env:SystemRoot, (Join-Path $sys32 'Wbem'), (Join-Path $sys32 'WindowsPowerShell\v1.0')
        )) -join ';'
    $env:NO_PROXY = '127.0.0.1,localhost,::1'
    New-Item -ItemType Directory -Force $RunDir, $LogDir, $DataDir, $SecretDir, (Join-Path $RunDir 'tmp') | Out-Null
    $env:TEMP = Join-Path $RunDir 'tmp'
    $env:TMP = $env:TEMP
}

function Read-Settings {
    $settings = @{}
    if (Test-Path -LiteralPath $ConfigFile) {
        foreach ($line in Get-Content -LiteralPath $ConfigFile -Encoding UTF8) {
            $text = $line.Trim()
            if ($text -eq '' -or $text.StartsWith('#')) { continue }
            $at = $text.IndexOf('=')
            if ($at -lt 1) { Write-Warn "Bo qua dong khong hop le trong config\evidence.env: $text"; continue }
            $key = $text.Substring(0, $at).Trim()
            $value = $text.Substring($at + 1).Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if ($key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { Write-Warn "Bo qua khoa khong hop le: $key"; continue }
            if ($ReservedKeys -contains $key) { Write-Warn "config\evidence.env khong duoc dat $key (do bo khoi dong quan ly)."; continue }
            $settings[$key] = $value
        }
    }
    return $settings
}

function Get-Setting($Settings, [string]$Name, [string]$Default) {
    if ($Settings.ContainsKey($Name) -and $Settings[$Name] -ne '') { return $Settings[$Name] }
    return $Default
}

function Get-Config {
    $settings = Read-Settings
    $cfg = [ordered]@{
        Settings   = $settings
        ListenHost = Get-Setting $settings 'EVIDENCE_LISTEN_HOST' '0.0.0.0'
        HttpPort   = 0; PgPort = 0; OllamaPort = 0
    }
    foreach ($pair in @(@('HttpPort', 'EVIDENCE_HTTP_PORT', '8800'), @('PgPort', 'EVIDENCE_PG_PORT', '55433'), @('OllamaPort', 'EVIDENCE_OLLAMA_PORT', '21434'))) {
        $raw = Get-Setting $settings $pair[1] $pair[2]
        $number = 0
        if (-not [int]::TryParse($raw, [ref]$number) -or $number -lt 1024 -or $number -gt 65535) {
            throw "$($pair[1]) = '$raw' khong hop le (can so nguyen tu 1024 den 65535) trong config\evidence.env."
        }
        $cfg[$pair[0]] = $number
    }
    $address = $null
    if (-not [Net.IPAddress]::TryParse($cfg.ListenHost, [ref]$address)) { throw "EVIDENCE_LISTEN_HOST = '$($cfg.ListenHost)' khong phai dia chi IP hop le." }
    if (@($cfg.HttpPort, $cfg.PgPort, $cfg.OllamaPort | Select-Object -Unique).Count -ne 3) {
        throw 'Cong web, PostgreSQL va Ollama phai khac nhau (EVIDENCE_HTTP_PORT / EVIDENCE_PG_PORT / EVIDENCE_OLLAMA_PORT).'
    }
    return $cfg
}

# ---- processes and ports --------------------------------------------------------------------
function Get-PortableProcesses {
    $prefix = $Root + '\'
    $own = $PID
    $result = @()
    foreach ($proc in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if ($proc.ProcessId -eq $own -or -not $proc.ExecutablePath) { continue }
        if ($proc.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { $result += $proc }
    }
    return $result
}

function Get-ProcessPath([int]$ProcessId) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($proc) { return [string]$proc.ExecutablePath }
    return ''
}

function Test-IsPortable([string]$ExePath) {
    return ($ExePath -and $ExePath.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase))
}

# The reliable test for "can this server bind the port": try to bind it exclusively.
function Test-PortBindable([string]$Address, [int]$Port) {
    $listener = $null
    try {
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Parse($Address), $Port)
        # Not exclusive on purpose: connections of the previous run in TIME_WAIT must not block a restart.
        $listener.Start()
        return $true
    } catch { return $false } finally {
        if ($listener) { try { $listener.Stop() } catch { } }
    }
}

function Get-PortListener([int]$Port) {
    $found = $null
    try { $found = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop) } catch { $found = @() }
    if ($found.Count -eq 0) { return $null }
    $owner = [int]$found[0].OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owner" -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        ProcessId = $owner; Name = $(if ($proc) { $proc.Name } else { '?' })
        Path = $(if ($proc) { [string]$proc.ExecutablePath } else { '' })
        Addresses = (($found | ForEach-Object { $_.LocalAddress }) | Select-Object -Unique) -join ', '
    }
}

function Read-PidFile([string]$Name) {
    $file = Join-Path $RunDir "$Name.pid"
    $text = (Read-TextOrEmpty $file).Trim()
    if ($text -notmatch '^\d+$') { return 0 }
    return [int]$text
}

# A saved PID counts only if the process is alive AND runs the expected bundled executable
# (a recycled PID of another program is never mistaken for ours).
function Get-OwnProcess([string]$Name, [string]$ExpectedExe) {
    $id = Read-PidFile $Name
    if ($id -le 0) { return $null }
    $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    $path = Get-ProcessPath $id
    if ($path -and [string]::Equals($path, $ExpectedExe, [StringComparison]::OrdinalIgnoreCase)) { return $proc }
    return $null
}

function Start-Detached {
    param([string]$Exe, [string[]]$Arguments, [string]$WorkDir, [hashtable]$Environment, [string]$OutLog, [string]$ErrLog)
    Rotate-Log $OutLog; Rotate-Log $ErrLog
    $saved = @{}
    foreach ($key in @($Environment.Keys)) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
    }
    try {
        $argText = ($Arguments | ForEach-Object { ConvertTo-ArgText $_ }) -join ' '
        $proc = Start-Process -FilePath $Exe -ArgumentList $argText -WorkingDirectory $WorkDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        $null = $proc.Handle
        return $proc
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
}

# Renaming a folder can fail for a moment while an antivirus scanner still holds a file in it.
function Move-Directory([string]$From, [string]$To) {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try { Move-Item -LiteralPath $From -Destination $To -ErrorAction Stop; return } catch {
            if ($attempt -eq 20) { throw "Khong doi ten duoc thu muc $From : $($_.Exception.Message)" }
            Start-Sleep -Milliseconds 750
        }
    }
}

function Rotate-Log([string]$File) {
    if ((Test-Path -LiteralPath $File) -and (Get-Item -LiteralPath $File).Length -gt 0) {
        Move-Item -LiteralPath $File -Destination ($File + '.1') -Force -ErrorAction SilentlyContinue
    }
}

# Ctrl+C is delivered to the hidden console of the target process, so servers (uvicorn, ollama)
# run their normal shutdown. Falls back to terminating the process after the timeout.
function Stop-Gracefully([int]$ProcessId, [string]$Label, [int]$TimeoutSeconds = 30) {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return }
    $helper = 'import ctypes,sys;k=ctypes.windll.kernel32;k.FreeConsole();ok=k.AttachConsole(int(sys.argv[1]));k.SetConsoleCtrlHandler(None,1);ok and k.GenerateConsoleCtrlEvent(0,0);sys.exit(0 if ok else 1)'
    try {
        $null = Invoke-Tool -Exe $Py -Arguments @('-I', '-c', $helper, "$ProcessId") `
            -OutFile (Join-Path $LogDir 'signal.out.txt') -ErrFile (Join-Path $LogDir 'signal.err.txt') -TimeoutSeconds 20
    } catch { Write-Log "Khong gui duoc tin hieu dung toi $Label : $($_.Exception.Message)" 'WARN' }
    if ($proc.WaitForExit($TimeoutSeconds * 1000)) { Write-Ok "$Label da dung (dung quy trinh binh thuong)."; return }
    Write-Warn "$Label khong phan hoi sau $TimeoutSeconds giay, buoc dung."
    try { $proc.Kill() } catch { }
    $null = $proc.WaitForExit(10000)
}

function Stop-ProcessTree([int]$ProcessId) {
    $null = Invoke-Tool -Exe (Join-Path $env:SystemRoot 'System32\taskkill.exe') -Arguments @('/PID', "$ProcessId", '/T', '/F') `
        -OutFile (Join-Path $LogDir 'taskkill.out.txt') -ErrFile (Join-Path $LogDir 'taskkill.err.txt') -TimeoutSeconds 30
}

# Reads one line from the console, or from redirected input when the launcher is scripted.
function Read-Line([string]$Prompt) {
    Write-Host $Prompt -NoNewline
    $line = [Console]::In.ReadLine()
    Write-Host ''
    if ($null -eq $line) { Write-Log "Doc dong nhap: khong co du lieu (EOF)"; return '' }
    Write-Log ("Doc dong nhap: '{0}'" -f $line.Trim())
    return $line.Trim()
}

# ---- HTTP (never through a proxy) ----------------------------------------------------------
function Invoke-Http([string]$Url, [string]$Method = 'GET', [string]$Body = '', [int]$TimeoutSeconds = 5) {
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.Method = $Method
    $request.Proxy = $null
    $request.Timeout = $TimeoutSeconds * 1000
    $request.ReadWriteTimeout = $TimeoutSeconds * 1000
    $request.AllowAutoRedirect = $false
    if ($Body -ne '') {
        $bytes = $Utf8NoBom.GetBytes($Body)
        $request.ContentType = 'application/json'
        $request.ContentLength = $bytes.Length
        $stream = $request.GetRequestStream(); $stream.Write($bytes, 0, $bytes.Length); $stream.Close()
    }
    $response = $null
    try {
        try { $response = $request.GetResponse() } catch [Net.WebException] {
            if ($_.Exception.Response) { $response = $_.Exception.Response } else { throw }
        }
        $reader = New-Object IO.StreamReader($response.GetResponseStream(), $Utf8NoBom)
        try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Body = $text }
    } finally {
        if ($response) { $response.Close() }
    }
}

function Test-Http([string]$Url, [int]$TimeoutSeconds = 3) {
    try { return (Invoke-Http $Url 'GET' '' $TimeoutSeconds) } catch { return $null }
}

# ---- manifest and preflight ------------------------------------------------------------------
function Get-PackageManifest {
    if (-not (Test-Path -LiteralPath $ManifestFile)) { throw 'Thieu MANIFEST.json: bo phat hanh khong day du.' }
    return (Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Test-OllamaModel($Model) {
    $manifestPath = Join-Path $ModelsDir ($Model.manifest -replace '/', '\')
    if (-not (Test-Path -LiteralPath $manifestPath)) { return "thieu manifest cua model $($Model.name): $manifestPath" }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return "manifest model $($Model.name) khong doc duoc" }
    $layers = @($manifest.config) + @($manifest.layers)
    foreach ($layer in $layers) {
        $blob = Join-Path $ModelsDir ('blobs\' + ([string]$layer.digest).Replace(':', '-'))
        if (-not (Test-Path -LiteralPath $blob)) { return "thieu tep model $($Model.name): $blob" }
        if ((Get-Item -LiteralPath $blob).Length -ne [int64]$layer.size) { return "tep model $($Model.name) sai kich thuoc: $blob" }
    }
    return ''
}

function Test-Preflight($Cfg, $Manifest) {
    $missing = New-Object System.Collections.Generic.List[string]
    $required = @(
        $Py, $SitePackages, (Join-Path $BackendDir 'app\main.py'), (Join-Path $WebRoot 'index.html'),
        (Join-Path $PgBin 'postgres.exe'), (Join-Path $PgBin 'pg_ctl.exe'), (Join-Path $PgBin 'initdb.exe'), (Join-Path $PgBin 'psql.exe'),
        (Join-Path $PgBin 'pg_dump.exe'), (Join-Path $PgBin 'pg_restore.exe'), (Join-Path $PgBin 'pg_isready.exe'),
        (Join-Path $Rt 'postgresql\lib\vector.dll'), (Join-Path $Rt 'postgresql\share\extension\vector.control'),
        $OllamaExe, (Join-Path $OllamaDir 'lib\ollama'),
        (Join-Path $TessDir 'tesseract.exe'), (Join-Path $TessDir 'tessdata\vie.traineddata'), (Join-Path $TessDir 'tessdata\eng.traineddata'),
        $ManifestFile
    )
    foreach ($item in $required) { if (-not (Test-Path -LiteralPath $item)) { $missing.Add("thieu thanh phan: " + $item.Substring($Root.Length + 1)) } }
    if ($missing.Count -gt 0) { throw ("Bo phat hanh khong day du:`n        " + ($missing -join "`n        ")) }
    foreach ($model in @($Manifest.models)) {
        $problem = Test-OllamaModel $model
        if ($problem) { $missing.Add($problem.Replace($Root + '\', '')) }
    }
    if ($missing.Count -gt 0) { throw ("Model AI cuc bo khong day du:`n        " + ($missing -join "`n        ")) }
    Write-Ok ("Runtime: Python, PostgreSQL + pgvector, Ollama, Tesseract (vie+eng) day du.")
    Write-Ok ("Model AI cuc bo: " + ((@($Manifest.models) | ForEach-Object { $_.name }) -join ', ') + " (tep trong models\ollama day du).")

    $hasCluster = Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION')
    if ($hasCluster) {
        $dataMajor = (Read-TextOrEmpty (Join-Path $PgData 'PG_VERSION')).Trim()
        $binMajor = [string]$Manifest.components.postgresql.major
        if ($binMajor -and $dataMajor -ne $binMajor) {
            throw "Thu muc data\postgres thuoc PostgreSQL $dataMajor nhung runtime di kem la $binMajor. Dung Restore-Data.bat de khoi phuc tu ban sao luu."
        }
        if (-not (Get-PgPassword)) {
            throw 'Co data\postgres nhung thieu secrets\postgres.password (mat khau co so du lieu). Khoi phuc tep nay tu ban sao luu cua thu muc, hoac dung Restore-Data.bat.'
        }
        Write-Ok 'Co so du lieu: data\postgres san sang.'
    } else {
        foreach ($item in (Join-Path $SeedDir 'evidence-rag.dump'), (Join-Path $SeedDir 'seed-manifest.json')) {
            if (-not (Test-Path -LiteralPath $item)) { throw "Chua co data\postgres va cung khong co du lieu goc de khoi tao: thieu $($item.Substring($Root.Length + 1))" }
        }
        Write-Ok 'Co so du lieu: chua khoi tao, se tao tu du lieu goc trong seed\ (chi lan dau).'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $DocStore 'originals'))) { throw 'Thieu kho tai lieu goc data\documents\originals.' }

    $drive = Get-PSDrive -Name $Root.Substring(0, 1) -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt 1GB) { throw ("O dia chua thu muc nay con duoi 1 GB trong ({0:N1} GB).") -f ($drive.Free / 1GB) }
    if ($Root.Length -gt 170) { throw "Duong dan thu muc qua dai ($($Root.Length) ky tu). Dat thu muc o vi tri ngan hon (goc o dia, ten ngan)." }
    if ($Root.Length -gt 120) { Write-Warn "Duong dan thu muc dai ($($Root.Length) ky tu); nen dat ngan hon." }
    if ($Root -match '[^\x00-\x7F]') { Write-Warn 'Duong dan thu muc co ky tu co dau; neu gap loi, hay dat thu muc o duong dan khong dau.' }
    try {
        $probe = Join-Path $RunDir ('write-test-' + [guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllText($probe, 'x'); Remove-Item -LiteralPath $probe -Force
    } catch { throw "Khong ghi duoc vao thu muc run\ : $($_.Exception.Message)" }
    Write-Ok 'Cau hinh, quyen ghi va dung luong dia: dat.'
}

# ---- PostgreSQL ------------------------------------------------------------------------------
function Get-PgPassword {
    if (-not (Test-Path -LiteralPath $PgPassFile)) { return '' }
    return (Read-TextOrEmpty $PgPassFile).Trim()
}

function New-Secret([int]$Length) {
    $alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes = New-Object byte[] ($Length * 4)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $chars = New-Object char[] $Length
    for ($i = 0; $i -lt $Length; $i++) { $chars[$i] = $alphabet[[int]([BitConverter]::ToUInt32($bytes, $i * 4) % [uint32]$alphabet.Length)] }
    return (-join $chars)
}

function New-PgConn([int]$Port, [string]$Database = '') {
    return @{
        Psql = Join-Path $PgBin 'psql.exe'; Host = '127.0.0.1'; Port = $Port; User = $DbUser
        Password = (Get-PgPassword); Database = $(if ($Database) { $Database } else { $DbName }); WorkDir = $RunDir
    }
}

function Invoke-Pg([string]$ToolName, [string[]]$Arguments, [string]$Tag, [int]$TimeoutSeconds = 600, [hashtable]$Environment = @{}) {
    $env2 = @{ PGPASSWORD = (Get-PgPassword); PGCLIENTENCODING = 'UTF8' }
    foreach ($key in $Environment.Keys) { $env2[$key] = $Environment[$key] }
    return (Invoke-Tool -Exe (Join-Path $PgBin $ToolName) -Arguments $Arguments `
            -OutFile (Join-Path $LogDir "$Tag.out.log") -ErrFile (Join-Path $LogDir "$Tag.err.log") -Environment $env2 -TimeoutSeconds $TimeoutSeconds)
}

function Get-PgState([string]$DataDirectory) {
    $pidFile = Join-Path $DataDirectory 'postmaster.pid'
    $result = [pscustomobject]@{ Running = $false; ProcessId = 0; Port = 0; Stale = $false }
    if (-not (Test-Path -LiteralPath $pidFile)) { return $result }
    $lines = @(Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue)
    if ($lines.Count -lt 4 -or $lines[0] -notmatch '^\d+$') { $result.Stale = $true; return $result }
    $id = [int]$lines[0]
    $path = Get-ProcessPath $id
    if ($path -and [string]::Equals($path, (Join-Path $PgBin 'postgres.exe'), [StringComparison]::OrdinalIgnoreCase)) {
        $result.Running = $true; $result.ProcessId = $id; $result.Port = [int]$lines[3]
    } else { $result.Stale = $true }
    return $result
}

function Start-PgServer([string]$DataDirectory, [int]$Port, [string]$LogTag) {
    $state = Get-PgState $DataDirectory
    if ($state.Stale) {
        Write-Log "Xoa postmaster.pid cu (tien trinh $($state.ProcessId) khong con) trong $DataDirectory" 'WARN'
        Remove-Item -LiteralPath (Join-Path $DataDirectory 'postmaster.pid') -Force -ErrorAction SilentlyContinue
    }
    $log = Join-Path $LogDir "$LogTag.log"
    Rotate-Log $log
    $rc = Invoke-Pg 'pg_ctl.exe' @('start', '-D', $DataDirectory, '-l', $log, '-o', "-h 127.0.0.1 -p $Port -c listen_addresses=127.0.0.1", '-w', '-t', '120') "pg_ctl-start" 180
    if ($rc -ne 0) {
        Show-LogTail (Join-Path $LogDir 'pg_ctl-start.err.log'); Show-LogTail $log 20
        throw 'PostgreSQL khong khoi dong duoc. Neu thu muc data\postgres duoc chep tu may khac va khong tuong thich, dung Restore-Data.bat de khoi phuc tu ban sao luu.'
    }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        $rc2 = Invoke-Pg 'pg_isready.exe' @('-h', '127.0.0.1', '-p', "$Port", '-t', '2') 'pg_isready' 30
        if ($rc2 -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { Show-LogTail $log 20; throw 'PostgreSQL da chay nhung chua san sang nhan ket noi.' }
}

function Stop-PgServer([string]$DataDirectory) {
    $state = Get-PgState $DataDirectory
    if (-not $state.Running) { return $false }
    $rc = Invoke-Pg 'pg_ctl.exe' @('stop', '-D', $DataDirectory, '-m', 'fast', '-w', '-t', '120') 'pg_ctl-stop' 180
    if ($rc -ne 0) {
        Show-LogTail (Join-Path $LogDir 'pg_ctl-stop.err.log')
        throw 'PostgreSQL khong dung duoc an toan trong 120 giay. Khong buoc tat de tranh hong du lieu; thu lai Stop-Server.bat sau it phut.'
    }
    return $true
}

# Builds a brand-new cluster in $Target from a pg_dump archive and checks it against the
# fingerprint recorded when the dump was made. The caller decides what happens to the result.
function New-ClusterFromDump([string]$Target, [string]$Dump, $Expected, [int]$Port) {
    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
    if (-not (Test-Path -LiteralPath $PgPassFile)) { Write-Utf8File $PgPassFile (New-Secret 32) }
    $rc = Invoke-Pg 'initdb.exe' @('-D', $Target, '-U', $DbUser, '-E', 'UTF8', '--locale=C', '-A', 'scram-sha-256', "--pwfile=$PgPassFile") 'initdb' 300
    if ($rc -ne 0) { Show-LogTail (Join-Path $LogDir 'initdb.err.log'); throw 'initdb that bai.' }
    $started = $false
    try {
        Start-PgServer $Target $Port 'postgres-init'
        $started = $true
        $conn = New-PgConn $Port 'postgres'
        $null = Invoke-Psql $conn @("CREATE DATABASE $DbName ENCODING 'UTF8' TEMPLATE template0") -Tag 'psql-create'
        $rc = Invoke-Pg 'pg_restore.exe' @('-h', '127.0.0.1', '-p', "$Port", '-U', $DbUser, '-d', $DbName, '--no-owner', '--no-acl', '--exit-on-error', '-j', '2', $Dump) 'pg_restore' 1800
        if ($rc -ne 0) { Show-LogTail (Join-Path $LogDir 'pg_restore.err.log') 20; throw 'pg_restore that bai.' }
        $null = Invoke-Psql (New-PgConn $Port) @('ANALYZE') -Tag 'psql-analyze' -TimeoutSeconds 900
        $actual = Get-DbFingerprint (New-PgConn $Port)
        $problems = Compare-DbFingerprint $Expected $actual
        if ($problems.Count -gt 0) {
            $problems | Select-Object -First 10 | ForEach-Object { Write-Fail $_ }
            throw 'Du lieu sau khi khoi phuc KHONG khop voi du lieu goc; da huy, khong thay the du lieu hien co.'
        }
        return $actual
    } finally {
        if ($started) { try { $null = Invoke-Pg 'pg_ctl.exe' @('stop', '-D', $Target, '-m', 'fast', '-w', '-t', '120') 'pg_ctl-stop-init' 180 } catch { } }
    }
}

function Sync-OllamaEndpoint([int]$Port) {
    $previous = $LegacyOllamaPort
    $saved = (Read-TextOrEmpty $OllamaPortFile).Trim()
    if ($saved -match '^\d+$') { $previous = [int]$saved }
    if ($previous -ne $Port) {
        # Only provider rows that still point at the bundled Ollama's previous loopback port are changed;
        # providers an administrator pointed elsewhere are left alone.
        $sql = "UPDATE providers SET endpoint = regexp_replace(endpoint, '^http://(127\.0\.0\.1|localhost):$previous/', 'http://127.0.0.1:$Port/') " +
        "WHERE adapter = 'ollama_local' AND endpoint ~ '^http://(127\.0\.0\.1|localhost):$previous/'; SELECT 'UPDATED|' || count(*) FROM providers WHERE endpoint LIKE 'http://127.0.0.1:$Port/%';"
        $out = Invoke-Psql (New-PgConn (Get-PgState $PgData).Port) @($sql) -Tag 'psql-endpoint'
        Write-Log "Dong bo dia chi Ollama noi bo: cong $previous -> $Port. $($out.Trim())"
        Write-Info "Dia chi AI cuc bo trong Model Registry: 127.0.0.1:$Port (cong Ollama di kem)."
    }
    Write-Utf8File $OllamaPortFile "$Port"
}

# ---- networking info ------------------------------------------------------------------------
function Get-LanAddresses {
    $items = @()
    try {
        $configs = @(Get-NetIPConfiguration -ErrorAction Stop)
        foreach ($c in $configs) {
            foreach ($a in @($c.IPv4Address)) {
                if ($a.IPAddress -match '^(127\.|169\.254\.)') { continue }
                $items += [pscustomobject]@{ Address = $a.IPAddress; Interface = $c.InterfaceAlias; Gateway = [bool]$c.IPv4DefaultGateway }
            }
        }
    } catch {
        foreach ($a in [Net.Dns]::GetHostAddresses([Net.Dns]::GetHostName())) {
            if ($a.AddressFamily -eq 'InterNetwork' -and $a.ToString() -notmatch '^(127\.|169\.254\.)') {
                $items += [pscustomobject]@{ Address = $a.ToString(); Interface = ''; Gateway = $false }
            }
        }
    }
    return @($items | Sort-Object -Property @{ Expression = { -not $_.Gateway } }, Address)
}

function Test-FirewallOpen([int]$Port) {
    try {
        $policy = New-Object -ComObject HNetCfg.FwPolicy2
        foreach ($rule in $policy.Rules) {
            if (-not $rule.Enabled -or $rule.Direction -ne 1 -or $rule.Action -ne 1) { continue }
            $app = [string]$rule.ApplicationName
            if ($app -and [string]::Equals($app, $Py, [StringComparison]::OrdinalIgnoreCase)) { return $true }
            if ($rule.Protocol -eq 6 -or $rule.Protocol -eq 256) {
                foreach ($piece in ([string]$rule.LocalPorts -split ',')) {
                    $p = $piece.Trim()
                    if ($p -eq "$Port") { return $true }
                    if ($p -match '^(\d+)-(\d+)$' -and [int]$Matches[1] -le $Port -and $Port -le [int]$Matches[2]) { return $true }
                }
            }
        }
        return $false
    } catch { return $null }
}

function Show-Access($Cfg) {
    $port = $Cfg.HttpPort
    Write-Host ''
    Write-Host '  =====================================================================' -ForegroundColor Green
    Write-Host '   EVIDENCE RAG DANG CHAY' -ForegroundColor Green
    Write-Host '  =====================================================================' -ForegroundColor Green
    if ($Cfg.ListenHost -eq '0.0.0.0' -or $Cfg.ListenHost -eq '::') {
        Write-Host '   Dia chi cho cac may trong mang LAN (chi can trinh duyet):'
        foreach ($item in (Get-LanAddresses)) {
            $tag = if ($item.Gateway) { '  <- dung dia chi nay' } else { '' }
            Write-Host ("     http://{0}:{1}/    [{2}]{3}" -f $item.Address, $port, $item.Interface, $tag) -ForegroundColor White
        }
        Write-Host ("     http://{0}:{1}/    (theo ten may)" -f $env:COMPUTERNAME, $port)
    } else {
        Write-Host ("   Dang nghe tai http://{0}:{1}/ (khong mo cho may khac)." -f $Cfg.ListenHost, $port)
    }
    Write-Host ("   Tren may nay: http://127.0.0.1:{0}/" -f $port)
    Write-Host '   PostgreSQL va Ollama chi nghe 127.0.0.1 (khong mo ra mang).'
    Write-Host '   Dung HTTP khong ma hoa: chi dung trong mang noi bo tin cay.'
    if ($Cfg.ListenHost -eq '0.0.0.0' -or $Cfg.ListenHost -eq '::') {
        $open = Test-FirewallOpen $port
        if ($open -eq $false) {
            Write-Host ''
            Write-Warn "Windows Firewall co the dang chan cong ${port}: may khac se khong vao duoc."
            Write-Info 'Chay tools\Allow-LAN-Firewall.bat (dong y hop thoai quyen Administrator), chi can mot lan.'
        }
    }
    Write-Host '   Dung may chu: Stop-Server.bat'
    Write-Host ''
}

# ---- action: start -------------------------------------------------------------------------
function Start-Stack {
    $manifest = Get-PackageManifest
    $cfg = Get-Config
    Write-Host ''
    Write-Host '  EVIDENCE RAG - KHOI DONG MAY CHU' -ForegroundColor White
    Write-Host "  Thu muc: $Root"
    Write-Log "Start: root=$Root http=$($cfg.HttpPort) pg=$($cfg.PgPort) ollama=$($cfg.OllamaPort) listen=$($cfg.ListenHost)"

    Write-Step '[1/6] Kiem tra runtime, model, co so du lieu, cau hinh'
    Test-Preflight $cfg $manifest

    # Components already running from this folder are reused; anything else on a port is a conflict.
    $pgState = Get-PgState $PgData
    $ollamaProc = Get-OwnProcess 'ollama' $OllamaExe
    $backendProc = Get-OwnProcess 'backend' $Py
    $webAddress = if ($cfg.ListenHost -eq '::') { '0.0.0.0' } else { $cfg.ListenHost }
    foreach ($check in @(
            @{ Name = 'May chu web (EVIDENCE_HTTP_PORT)'; Port = $cfg.HttpPort; Own = [bool]$backendProc; Address = $webAddress },
            @{ Name = 'PostgreSQL (EVIDENCE_PG_PORT)'; Port = $cfg.PgPort; Own = $pgState.Running; Address = '127.0.0.1' },
            @{ Name = 'Ollama (EVIDENCE_OLLAMA_PORT)'; Port = $cfg.OllamaPort; Own = [bool]$ollamaProc; Address = '127.0.0.1' })) {
        if ($check.Own) { continue }
        $listener = Get-PortListener $check.Port
        $free = Test-PortBindable $check.Address $check.Port
        if ($listener -or -not $free) {
            $who = if ($listener) { "{0} (PID {1}) {2}" -f $listener.Name, $listener.ProcessId, $listener.Path } else { 'khong xac dinh duoc chuong trinh' }
            throw ("Cong {0} ({1}) dang duoc chuong trinh khac dung: {2}. Dong chuong trinh do hoac doi cong trong config\evidence.env." -f $check.Port, $check.Name, $who)
        }
    }
    Write-Ok "Cong mang: web $($cfg.HttpPort), PostgreSQL $($cfg.PgPort) (localhost), Ollama $($cfg.OllamaPort) (localhost)."

    if ($backendProc -and $pgState.Running -and $ollamaProc) {
        $health = Test-Http "http://127.0.0.1:$($cfg.HttpPort)/health" 4
        if ($health -and $health.Status -eq 200) {
            Write-Host ''
            Write-Ok "May chu da chay san (PID web $($backendProc.Id)); khong khoi dong lai."
            Show-Access $cfg
            return
        }
        Write-Warn 'Cac tien trinh dang chay nhung web khong tra loi; se dung lai va khoi dong lai.'
        Stop-Stack -Quiet
        $pgState = Get-PgState $PgData; $ollamaProc = $null; $backendProc = $null
    }
    $blocked = @($Py, $OllamaExe, (Join-Path $TessDir 'tesseract.exe'), (Join-Path $PgBin 'postgres.exe')) |
        Where-Object { Get-Item -LiteralPath $_ -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue }
    if ($blocked) {
        Write-Info 'Goi duoc tai tu Internet/email nen bi danh dau "blocked"; go dau nay cho cac tep trong goi (chi mot lan)...'
        Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
    }

    Write-Step '[2/6] Co so du lieu PostgreSQL + pgvector'
    if (-not (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION'))) {
        Write-Info 'Lan dau: khoi tao co so du lieu rieng tu ban du lieu goc (khong dung PostgreSQL cua may).'
        Write-Info 'Quy trinh: initdb -> pg_restore -> doi chieu noi dung tung bang -> chi khi khop moi dua vao su dung.'
        $expected = Get-Content -LiteralPath (Join-Path $SeedDir 'seed-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $stage = $PgData + '.initializing'
        $started = Get-Date
        $null = New-ClusterFromDump $stage (Join-Path $SeedDir 'evidence-rag.dump') $expected.fingerprint $cfg.PgPort
        Move-Directory $stage $PgData
        Write-Utf8File $OllamaPortFile "$LegacyOllamaPort"
        Write-Ok ("Da tao data\postgres tu du lieu goc ({0:N0} giay). Noi dung moi bang da duoc doi chieu khop." -f ((Get-Date) - $started).TotalSeconds)
    }
    if (-not $pgState.Running) {
        Start-PgServer $PgData $cfg.PgPort 'postgres'
        $script:StartedNow['postgres'] = $true
        $pgState = Get-PgState $PgData
        Write-Ok "PostgreSQL dang chay (PID $($pgState.ProcessId), 127.0.0.1:$($pgState.Port))."
    } else {
        Write-Ok "PostgreSQL da chay san (PID $($pgState.ProcessId), cong $($pgState.Port))."
    }
    $dbPort = $pgState.Port
    $conn = New-PgConn $dbPort
    $summary = (Invoke-Psql $conn @("SELECT (SELECT count(*) FROM documents) || '|' || (SELECT count(*) FROM node_embeddings) || '|' || (SELECT count(*) FROM users) || '|' || (SELECT extversion FROM pg_extension WHERE extname = 'vector')") -Tag 'psql-summary').Trim().Split('|')
    Write-Ok ("Du lieu: {0} tai lieu, {1} vector, {2} tai khoan, pgvector {3}." -f $summary[0], $summary[1], $summary[2], $summary[3])
    Sync-OllamaEndpoint $cfg.OllamaPort

    Write-Step '[3/6] Ollama (AI cuc bo, chi nghe localhost)'
    if (-not $ollamaProc) {
        New-Item -ItemType Directory -Force $OllamaHome, (Join-Path $OllamaHome 'AppData\Roaming'), (Join-Path $OllamaHome 'AppData\Local') | Out-Null
        $ollamaEnv = @{
            OLLAMA_HOST = "127.0.0.1:$($cfg.OllamaPort)"; OLLAMA_MODELS = $ModelsDir; OLLAMA_NOPRUNE = '1'; OLLAMA_NO_CLOUD = '1'
            OLLAMA_ORIGINS = 'http://127.0.0.1'; USERPROFILE = $OllamaHome; HOME = $OllamaHome
            APPDATA = (Join-Path $OllamaHome 'AppData\Roaming'); LOCALAPPDATA = (Join-Path $OllamaHome 'AppData\Local')
        }
        $proc = Start-Detached $OllamaExe @('serve') $OllamaDir $ollamaEnv (Join-Path $LogDir 'ollama.out.log') (Join-Path $LogDir 'ollama.err.log')
        Write-Utf8File (Join-Path $RunDir 'ollama.pid') "$($proc.Id)"
        $script:StartedNow['ollama'] = $true
        $ready = $false
        for ($i = 0; $i -lt 120; $i++) {
            if ($proc.HasExited) { break }
            $r = Test-Http "http://127.0.0.1:$($cfg.OllamaPort)/api/version" 2
            if ($r -and $r.Status -eq 200) { $ready = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { Show-LogTail (Join-Path $LogDir 'ollama.err.log') 15; Show-LogTail (Join-Path $LogDir 'ollama.out.log') 15; throw 'Ollama khong khoi dong duoc (xem logs\ollama.err.log).' }
        $ollamaProc = $proc
        Write-Ok "Ollama dang chay (PID $($proc.Id), 127.0.0.1:$($cfg.OllamaPort), thu muc model: models\ollama)."
    } else {
        Write-Ok "Ollama da chay san (PID $($ollamaProc.Id))."
    }
    $tags = Invoke-Http "http://127.0.0.1:$($cfg.OllamaPort)/api/tags" 'GET' '' 15
    $names = @(($tags.Body | ConvertFrom-Json).models | ForEach-Object { $_.name })
    foreach ($model in @($manifest.models)) {
        if ($names -notcontains $model.name) { throw "Ollama khong thay model $($model.name) trong models\ollama (tim thay: $($names -join ', '))." }
    }
    Write-Ok ("Ollama nhan day du model: " + ((@($manifest.models) | ForEach-Object { $_.name }) -join ', ') + ".")

    Write-Step '[4/6] May chu FastAPI (web + API + OCR)'
    if (-not $backendProc) {
        $appEnv = [ordered]@{}
        foreach ($key in $cfg.Settings.Keys) { if ($cfg.Settings[$key] -ne '') { $appEnv[$key] = $cfg.Settings[$key] } }
        $encoded = [uri]::EscapeDataString((Get-PgPassword))
        $appEnv['DATABASE_URL'] = "postgresql://${DbUser}:${encoded}@127.0.0.1:${dbPort}/${DbName}"
        $appEnv['EVIDENCE_DOCUMENT_STORE_ROOT'] = $DocStore
        $appEnv['EVIDENCE_SECRET_STORE_DIR'] = Join-Path $SecretDir 'ai-keys'
        $appEnv['EVIDENCE_WEB_ROOT'] = $WebRoot
        $appEnv['EVIDENCE_OCR_EXECUTABLE'] = Join-Path $TessDir 'tesseract.exe'
        $appEnv['EVIDENCE_OCR_TESSDATA'] = Join-Path $TessDir 'tessdata'
        if (-not $appEnv.Contains('EVIDENCE_OCR_LANGUAGES')) { $appEnv['EVIDENCE_OCR_LANGUAGES'] = 'vie+eng' }
        if (-not $appEnv.Contains('AI_OPERATING_MODE')) { $appEnv['AI_OPERATING_MODE'] = 'LOCAL' }
        $appEnv['DEV_ALLOW_IN_MEMORY_STORE'] = 'false'
        $appEnv['PYTHONPATH'] = "$SitePackages;$BackendDir"
        $appEnv['PYTHONNOUSERSITE'] = '1'
        $appEnv['PYTHONPYCACHEPREFIX'] = Join-Path $RunDir 'pycache'
        $appEnv['PYTHONIOENCODING'] = 'utf-8'
        $appEnv['PYTHONUTF8'] = '1'
        New-Item -ItemType Directory -Force (Join-Path $SecretDir 'ai-keys') | Out-Null
        $proc = Start-Detached $Py @('-s', '-m', 'uvicorn', 'app.main:create_app', '--factory', '--no-access-log', '--host', $cfg.ListenHost, '--port', "$($cfg.HttpPort)") `
            $BackendDir $appEnv (Join-Path $LogDir 'backend.out.log') (Join-Path $LogDir 'backend.err.log')
        Write-Utf8File (Join-Path $RunDir 'backend.pid') "$($proc.Id)"
        $script:StartedNow['backend'] = $true
        $ready = $false
        for ($i = 0; $i -lt 240; $i++) {
            if ($proc.HasExited) { break }
            $r = Test-Http "http://127.0.0.1:$($cfg.HttpPort)/health" 2
            if ($r -and $r.Status -eq 200) { $ready = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) {
            Show-LogTail (Join-Path $LogDir 'backend.err.log') 25
            Remove-Item -LiteralPath (Join-Path $RunDir 'backend.pid') -ErrorAction SilentlyContinue
            if (-not $proc.HasExited) { Stop-ProcessTree $proc.Id }
            throw 'May chu web/API khong san sang (xem logs\backend.err.log).'
        }
        $backendProc = $proc
        Write-Ok "May chu web/API dang chay (PID $($proc.Id), cong $($cfg.HttpPort))."
    } else {
        Write-Ok "May chu web/API da chay san (PID $($backendProc.Id))."
    }

    Write-Step '[5/6] Kiem tra trang thai san sang'
    $health = Invoke-Http "http://127.0.0.1:$($cfg.HttpPort)/health" 'GET' '' 10
    $healthJson = $health.Body | ConvertFrom-Json
    if ($health.Status -ne 200 -or $healthJson.status -ne 'ok') { throw "Kiem tra /health that bai: $($health.Status) $($health.Body)" }
    $homePage = Invoke-Http "http://127.0.0.1:$($cfg.HttpPort)/" 'GET' '' 10
    if ($homePage.Status -ne 200 -or $homePage.Body -notmatch '<div id="root"|<html') { throw 'May chu khong phuc vu duoc giao dien web (app\web).' }
    Write-Ok 'Giao dien web va API tra loi dung.'
    $modeResp = Test-Http "http://127.0.0.1:$($cfg.HttpPort)/api/v1/system/mode" 10
    if ($modeResp -and $modeResp.Status -eq 200) { Write-Ok ("Che do AI cua he thong: " + (($modeResp.Body | ConvertFrom-Json) | ConvertTo-Json -Compress)) }
    $warnings = 0
    foreach ($model in @($manifest.models)) {
        if ($model.role -eq 'embedding') {
            try {
                $body = (@{ model = $model.name; input = 'kiem tra' } | ConvertTo-Json -Compress)
                $r = Invoke-Http "http://127.0.0.1:$($cfg.OllamaPort)/api/embed" 'POST' $body 180
                $dims = @((($r.Body | ConvertFrom-Json).embeddings)[0]).Count
                if ($r.Status -eq 200 -and $dims -eq [int]$model.dimensions) { Write-Ok "Model embedding $($model.name) hoat dong offline ($dims chieu)." }
                else { $warnings++; Write-Warn "Model embedding $($model.name) tra ve $dims chieu (can $($model.dimensions)), ma $($r.Status)." }
            } catch { $warnings++; Write-Warn "Khong chay duoc model embedding $($model.name): $($_.Exception.Message)" }
        } else {
            try {
                $body = (@{ model = $model.name; prompt = 'Tra loi mot tu: OK'; stream = $false; think = $false; options = @{ num_predict = 4 } } | ConvertTo-Json -Compress)
                $r = Invoke-Http "http://127.0.0.1:$($cfg.OllamaPort)/api/generate" 'POST' $body 240
                if ($r.Status -eq 200) { Write-Ok "Model sinh van ban $($model.name) hoat dong offline." }
                else { $warnings++; Write-Warn "Model $($model.name) tra ve ma $($r.Status)." }
            } catch { $warnings++; Write-Warn "Khong chay duoc model $($model.name): $($_.Exception.Message)" }
        }
    }

    Write-Step '[6/6] Hoan tat'
    if ($warnings -gt 0) { Write-Warn "May chu web chay, nhung $warnings model AI chua phan hoi; cac chuc nang AI co the cham hoac tam khong dung duoc. Xem logs\ollama.err.log." }
    Show-Access $cfg
    Write-Log 'Start xong.'
}

# ---- action: stop --------------------------------------------------------------------------
function Stop-Stack([switch]$Quiet) {
    if (-not $Quiet) { Write-Host ''; Write-Host '  EVIDENCE RAG - DUNG MAY CHU' -ForegroundColor White }
    $stoppedAny = $false
    $backend = Get-OwnProcess 'backend' $Py
    if ($backend) { Stop-Gracefully $backend.Id 'May chu web/API' 40; $stoppedAny = $true } else { Write-Info 'May chu web/API khong chay.' }
    Remove-Item -LiteralPath (Join-Path $RunDir 'backend.pid') -Force -ErrorAction SilentlyContinue

    $ollama = Get-OwnProcess 'ollama' $OllamaExe
    if ($ollama) { Stop-Gracefully $ollama.Id 'Ollama' 30; $stoppedAny = $true } else { Write-Info 'Ollama khong chay.' }
    Remove-Item -LiteralPath (Join-Path $RunDir 'ollama.pid') -Force -ErrorAction SilentlyContinue

    if (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION')) {
        if (Stop-PgServer $PgData) { Write-Ok 'PostgreSQL da dung an toan (pg_ctl stop -m fast).'; $stoppedAny = $true } else { Write-Info 'PostgreSQL khong chay.' }
    }
    # Anything else still running from this folder (for example a worker left by a crash).
    $pgExe = Join-Path $PgBin 'postgres.exe'
    foreach ($left in @(Get-PortableProcesses)) {
        if ([string]::Equals($left.ExecutablePath, $pgExe, [StringComparison]::OrdinalIgnoreCase)) { continue }
        Write-Warn "Tien trinh con sot lai thuoc goi nay: $($left.Name) (PID $($left.ProcessId)); dung."
        Stop-ProcessTree $left.ProcessId
        $stoppedAny = $true
    }
    if (-not $Quiet) {
        Write-Host ''
        if ($stoppedAny) { Write-Ok 'Da dung cac tien trinh cua bo portable. Cac ung dung khac tren may khong bi anh huong.' }
        else { Write-Ok 'Khong co tien trinh nao cua bo portable dang chay.' }
    }
    Write-Log 'Stop xong.'
}

# ---- action: status ------------------------------------------------------------------------
function Show-Status {
    $manifest = Get-PackageManifest
    $cfg = Get-Config
    $pg = Get-PgState $PgData
    $backend = Get-OwnProcess 'backend' $Py
    $ollama = Get-OwnProcess 'ollama' $OllamaExe
    Write-Host ''
    Write-Host "  Thu muc          : $Root"
    Write-Host ("  Phien ban goi    : {0} (build {1})" -f $manifest.package.version, $manifest.package.built_at_utc)
    Write-Host ("  PostgreSQL       : {0}" -f $(if ($pg.Running) { "chay (PID $($pg.ProcessId), cong $($pg.Port))" } elseif (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION')) { 'dung' } else { 'chua khoi tao (se tao khi Start)' }))
    Write-Host ("  Ollama           : {0}" -f $(if ($ollama) { "chay (PID $($ollama.Id), cong $($cfg.OllamaPort))" } else { 'dung' }))
    Write-Host ("  May chu web/API  : {0}" -f $(if ($backend) { "chay (PID $($backend.Id), cong $($cfg.HttpPort))" } else { 'dung' }))
    if ($backend) {
        $h = Test-Http "http://127.0.0.1:$($cfg.HttpPort)/health" 5
        Write-Host ("  /health          : {0}" -f $(if ($h) { "$($h.Status) $($h.Body)" } else { 'khong phan hoi' }))
        Show-Access $cfg
    }
    if ($pg.Running) {
        $s = (Invoke-Psql (New-PgConn $pg.Port) @("SELECT (SELECT count(*) FROM documents) || ' tai lieu, ' || (SELECT count(*) FROM document_nodes) || ' nut, ' || (SELECT count(*) FROM node_embeddings) || ' vector, ' || (SELECT count(*) FROM users) || ' tai khoan'") -Tag 'psql-status').Trim()
        Write-Host "  Du lieu          : $s"
    }
    $others = @(Get-PortableProcesses)
    Write-Host ("  Tien trinh goi   : {0}" -f $others.Count)
}

# ---- action: verify ------------------------------------------------------------------------
function Invoke-VerifyPackage {
    if (-not (Test-Path -LiteralPath $ChecksumFile)) { throw 'Khong co checksums.sha256.' }
    $lines = @(Get-Content -LiteralPath $ChecksumFile -Encoding UTF8 | Where-Object { $_.Trim() -ne '' })
    Write-Host ''
    Write-Host "  Kiem tra toan ven $($lines.Count) tep theo checksums.sha256 (SHA-256) ..."
    $bad = 0; $done = 0
    foreach ($line in $lines) {
        $hash = $line.Substring(0, 64); $rel = $line.Substring(66)
        $file = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $file)) { Write-Fail "THIEU: $rel"; $bad++ }
        elseif ((Get-FileSha256 $file) -ne $hash) { Write-Fail "SAI MA BAM: $rel"; $bad++ }
        $done++
        if ($done % 2000 -eq 0) { Write-Info "$done / $($lines.Count) ..." }
    }
    if ($bad -gt 0) { throw "$bad tep thieu hoac bi thay doi so voi ban phat hanh." }
    Write-Ok "Tat ca $($lines.Count) tep khop ban phat hanh (khong tinh data\, logs\, run\, backups\, secrets\)."
}

# ---- action: firewall ----------------------------------------------------------------------
function Set-LanFirewall {
    $cfg = Get-Config
    $mode = if ($Path -eq 'remove') { 'remove' } else { 'add' }
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can quyen Administrator: chuot phai vao Allow-LAN-Firewall.bat > Run as administrator.'
    }
    $name = "Evidence RAG LAN (TCP $($cfg.HttpPort))"
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($mode -eq 'add') {
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $cfg.HttpPort -Action Allow `
            -Profile Private, Domain -RemoteAddress LocalSubnet | Out-Null
        Write-Ok "Da tao quy tac '$name': cho phep cong $($cfg.HttpPort) tu mang con noi bo, profile Private/Domain."
    } else {
        Write-Ok "Da go quy tac '$name'."
    }
}

# ---- backup and restore --------------------------------------------------------------------
function Copy-Documents([string]$From, [string]$To) {
    New-Item -ItemType Directory -Force $To | Out-Null
    # Copy only: nothing in the destination is ever deleted (/MIR and /PURGE are not used).
    # robocopy exit codes below 8 mean success (files copied or already identical).
    $rc = Invoke-Tool -Exe (Join-Path $env:SystemRoot 'System32\robocopy.exe') `
        -Arguments @($From, $To, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:2', '/NFL', '/NDL', '/NP', '/NJH') `
        -OutFile (Join-Path $LogDir 'robocopy.log') -ErrFile (Join-Path $LogDir 'robocopy.err.log') -TimeoutSeconds 3600
    if ($rc -ge 8) { throw "Sao chep tai lieu that bai (robocopy ma $rc, xem logs\robocopy.log)." }
}

function New-Backup {
    $manifest = Get-PackageManifest
    $cfg = Get-Config
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $dest = if ($Path) { [IO.Path]::GetFullPath($Path) } else { Join-Path $BackupRoot "backup-$stamp" }
    if ((Test-Path -LiteralPath $dest) -and @(Get-ChildItem -LiteralPath $dest -Force).Count -gt 0) { throw "Thu muc sao luu da co noi dung: $dest" }
    Write-Host ''
    Write-Host '  EVIDENCE RAG - SAO LUU DU LIEU' -ForegroundColor White
    Write-Host "  Dich: $dest"
    if (-not (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION'))) { throw 'Chua co co so du lieu (data\postgres) de sao luu.' }

    $startedHere = $false
    $pg = Get-PgState $PgData
    if (-not $pg.Running) {
        $listener = Get-PortListener $cfg.PgPort
        if ($listener) { throw "Cong PostgreSQL $($cfg.PgPort) dang bi chuong trinh khac dung: $($listener.Name)." }
        Write-Step '[1/4] Khoi dong PostgreSQL tam thoi de sao luu'
        Start-PgServer $PgData $cfg.PgPort 'postgres'
        $startedHere = $true
        $pg = Get-PgState $PgData
    } else { Write-Step '[1/4] PostgreSQL dang chay: sao luu truc tuyen (khong can dung may chu)' }
    $snapshot = $null
    $success = $false
    $createdDest = -not (Test-Path -LiteralPath $dest)
    try {
        New-Item -ItemType Directory -Force $dest | Out-Null
        $conn = New-PgConn $pg.Port
        Write-Step '[2/4] Sao luu co so du lieu (anh chup nhat quan, gom ca vector va chi muc)'
        $snapshot = Open-DbSnapshot $conn
        $dumpFile = Join-Path $dest 'evidence-rag.dump'
        $rc = Invoke-Pg 'pg_dump.exe' @('-h', '127.0.0.1', '-p', "$($pg.Port)", '-U', $DbUser, '-d', $DbName, '-Fc', '-Z', '6', '--no-owner', '--no-acl',
            '--exclude-table-data=public.auth_sessions', "--snapshot=$($snapshot.Id)", '-f', $dumpFile) 'pg_dump' 3600
        if ($rc -ne 0) { Show-LogTail (Join-Path $LogDir 'pg_dump.err.log'); throw 'pg_dump that bai.' }
        $fingerprint = Get-DbFingerprint $conn $snapshot.Id
        Close-DbSnapshot $snapshot; $snapshot = $null
        $rc = Invoke-Pg 'pg_restore.exe' @('--list', $dumpFile) 'pg_restore-list' 120
        if ($rc -ne 0) { throw 'Tep sao luu co so du lieu khong doc lai duoc (pg_restore --list).' }
        Write-Ok ("Co so du lieu: {0:N1} MB, {1} bang, schema {2}." -f ((Get-Item -LiteralPath $dumpFile).Length / 1MB), $fingerprint.tables.Count, $fingerprint.schema_version)

        Write-Step '[3/4] Sao luu kho tai lieu goc (originals, sources) va cau hinh'
        $missing = Test-DocumentReferences $conn $DocStore
        if ($missing.Count -gt 0) { throw ("Kho tai lieu thieu tep ma co so du lieu tham chieu (vi du: {0})." -f ($missing | Select-Object -First 3 | ForEach-Object { $_ }) -join ', ') }
        Copy-Documents $DocStore (Join-Path $dest 'documents')
        New-Item -ItemType Directory -Force (Join-Path $dest 'config') | Out-Null
        if (Test-Path -LiteralPath $ConfigFile) { Copy-Item -LiteralPath $ConfigFile -Destination (Join-Path $dest 'config\evidence.env') }
        $docCheck = Test-DocumentStore (Join-Path $dest 'documents')
        if ($docCheck.Mismatched.Count -gt 0) { throw ("Tai lieu sao luu bi sai ma SHA-256: " + ($docCheck.Mismatched -join ', ')) }
        if ($docCheck.Unexpected.Count -gt 0) { Write-Warn ("Kho tai lieu co tep khong theo quy uoc ten SHA-256 (van duoc sao chep): " + ($docCheck.Unexpected -join ', ')) }
        Write-Ok "Kho tai lieu: $($docCheck.Files) tep, ma SHA-256 cua tung tep khop ten tep."

        Write-Step '[4/4] Ghi so kiem tra'
        $sums = New-Object System.Collections.Generic.List[string]
        foreach ($file in Get-ChildItem -LiteralPath $dest -Recurse -File) {
            $rel = $file.FullName.Substring($dest.Length + 1)
            $sums.Add((Get-FileSha256 $file.FullName) + '  ' + $rel)
        }
        Write-Utf8File (Join-Path $dest 'checksums.sha256') (($sums -join "`n") + "`n")
        $info = [ordered]@{
            backup_format = 1
            created_at_utc = (Get-Date).ToUniversalTime().ToString('o')
            package_version = $manifest.package.version
            database = $DbName
            excluded_table_data = @('auth_sessions')
            documents_files = $docCheck.Files
            fingerprint = $fingerprint
        }
        Write-Utf8File (Join-Path $dest 'backup-manifest.json') ($info | ConvertTo-Json -Depth 8)
        $success = $true
        Write-Host ''
        Write-Ok "Sao luu xong: $dest"
        Write-Info 'Khoi phuc bang Restore-Data.bat. Nen chep thu muc nay sang o dia/may khac.'
    } finally {
        Close-DbSnapshot $snapshot
        if ($startedHere) { try { $null = Stop-PgServer $PgData } catch { Write-Warn $_.Exception.Message } }
        if (-not $success -and $createdDest -and (Test-Path -LiteralPath $dest)) {
            # Only the folder this run created is removed, so a half-written backup is never mistaken for a good one.
            Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue
            Write-Warn 'Sao luu that bai; da xoa thu muc sao luu do dang (khong anh huong du lieu).'
        }
    }
}

function Restore-Backup {
    $manifest = Get-PackageManifest
    $cfg = Get-Config
    Write-Host ''
    Write-Host '  EVIDENCE RAG - KHOI PHUC DU LIEU' -ForegroundColor White
    $source = $Path
    if (-not $source) {
        $found = @()
        if (Test-Path -LiteralPath $BackupRoot) { $found = @(Get-ChildItem -LiteralPath $BackupRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'backup-manifest.json') } | Sort-Object Name -Descending) }
        if ($found.Count -eq 0) { throw 'Khong co ban sao luu nao trong backups\. Dung: Restore-Data.bat <thu muc sao luu>' }
        if ($Yes) { throw 'Voi -Yes phai chi ro thu muc sao luu.' }
        Write-Host '  Cac ban sao luu hien co (moi nhat truoc):'
        for ($i = 0; $i -lt $found.Count; $i++) { Write-Host ("    [{0}] {1}" -f ($i + 1), $found[$i].Name) }
        $choice = Read-Line '  Chon so ban can khoi phuc (Enter de huy): '
        if ($choice -notmatch '^\d+$' -or [int]$choice -lt 1 -or [int]$choice -gt $found.Count) { Write-Info 'Da huy.'; return }
        $source = $found[[int]$choice - 1].FullName
    }
    $source = [IO.Path]::GetFullPath($source)
    foreach ($item in 'backup-manifest.json', 'evidence-rag.dump', 'checksums.sha256') {
        if (-not (Test-Path -LiteralPath (Join-Path $source $item))) { throw "Ban sao luu khong hop le, thieu $item : $source" }
    }
    $info = Get-Content -LiteralPath (Join-Path $source 'backup-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json

    Write-Step '[1/6] Kiem tra toan ven ban sao luu'
    $bad = 0
    foreach ($line in (Get-Content -LiteralPath (Join-Path $source 'checksums.sha256') -Encoding UTF8 | Where-Object { $_.Trim() -ne '' })) {
        $file = Join-Path $source $line.Substring(66)
        if (-not (Test-Path -LiteralPath $file) -or (Get-FileSha256 $file) -ne $line.Substring(0, 64)) { Write-Fail "Hong/thieu: $($line.Substring(66))"; $bad++ }
    }
    if ($bad -gt 0) { throw "Ban sao luu bi hong ($bad tep). Khong khoi phuc." }
    $t = $info.fingerprint.tables
    Write-Ok ("Ban sao luu hop le: tao luc {0}, {1} tai lieu, {2} vector, {3} tai khoan." -f $info.created_at_utc, $t.documents.rows, $t.node_embeddings.rows, $t.users.rows)

    Write-Step '[2/6] Xac nhan'
    Write-Host '  Toan bo co so du lieu HIEN TAI se bi thay bang ban sao luu nay.' -ForegroundColor Yellow
    Write-Host '  Truoc do he thong tu sao luu du lieu hien tai vao backups\pre-restore-* de co the quay lai.'
    if (-not $Yes) {
        $answer = Read-Line '  Go KHOI PHUC (viet hoa) de xac nhan, Enter de huy: '
        if ($answer -ne 'KHOI PHUC') { Write-Info 'Da huy, khong thay doi gi.'; return }
    }

    Write-Step '[3/6] Dung may chu (neu dang chay)'
    $wasRunning = [bool](Get-OwnProcess 'backend' $Py)
    Stop-Stack -Quiet
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')

    if (Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION')) {
        Write-Step '[4/6] Sao luu du lieu hien tai (an toan truoc khi thay)'
        $savedPath = $script:Path
        try {
            $script:Path = Join-Path $BackupRoot "pre-restore-$stamp"
            New-Backup
        } catch {
            Write-Warn "Khong sao luu duoc du lieu hien tai: $($_.Exception.Message)"
            Write-Warn 'Du lieu hien tai van duoc giu nguyen o data\postgres.before-restore-* sau khi khoi phuc.'
        } finally { $script:Path = $savedPath }
    } else { Write-Step '[4/6] Chua co du lieu hien tai, bo qua sao luu an toan' }

    Write-Step '[5/6] Dung co so du lieu moi tu ban sao luu va doi chieu'
    $listener = Get-PortListener $cfg.PgPort
    if ($listener) { throw "Cong PostgreSQL $($cfg.PgPort) dang bi chuong trinh khac dung: $($listener.Name)." }
    $stage = $PgData + '.restoring'
    $null = New-ClusterFromDump $stage (Join-Path $source 'evidence-rag.dump') $info.fingerprint $cfg.PgPort
    Write-Ok 'Noi dung tung bang cua co so du lieu moi khop 100% voi ban sao luu.'
    if (Test-Path -LiteralPath $PgData) {
        $old = "$PgData.before-restore-$stamp"
        Move-Directory $PgData $old
        Write-Info "Du lieu cu duoc giu o: $old (co the xoa khi chac chan)."
    }
    Move-Directory $stage $PgData
    Write-Utf8File $OllamaPortFile "$LegacyOllamaPort"

    Write-Step '[6/6] Khoi phuc kho tai lieu goc'
    Copy-Documents (Join-Path $source 'documents') $DocStore
    $docCheck = Test-DocumentStore $DocStore
    if ($docCheck.Mismatched.Count -gt 0) { throw ("Tai lieu sau khoi phuc sai ma SHA-256: " + ($docCheck.Mismatched -join ', ')) }
    Write-Ok "Kho tai lieu: $($docCheck.Files) tep, SHA-256 khop."
    Write-Host ''
    Write-Ok 'Khoi phuc xong.'
    if ($wasRunning) { Write-Info 'May chu da dung truoc khi khoi phuc; khoi dong lai...'; Start-Stack }
    else { Write-Info 'Chay Start-Server.bat de khoi dong lai.' }
}

# ---- main ----------------------------------------------------------------------------------
$lockStream = $null
$script:StartedNow = @{}
try {
    Initialize-Environment
    $lockFile = Join-Path $RunDir 'launcher.lock'
    try {
        $lockStream = New-Object IO.FileStream($lockFile, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        throw 'Mot lenh khac cua bo portable (Start/Stop/Backup/Restore) dang chay. Doi no ket thuc roi thu lai.'
    }
    switch ($Action) {
        'start' { Start-Stack }
        'stop' { Stop-Stack }
        'status' { Show-Status }
        'backup' { New-Backup }
        'restore' { Restore-Backup }
        'verify' { Invoke-VerifyPackage }
        'firewall' { Set-LanFirewall }
    }
    exit 0
} catch {
    Write-Host ''
    Write-Fail $_.Exception.Message
    Write-Log ($_.ScriptStackTrace) 'ERROR'
    Write-Host ''
    Write-Host "        Chi tiet: $LauncherLog" -ForegroundColor DarkGray
    if ($Action -eq 'start' -and $script:StartedNow.Count -gt 0) {
        # Roll back: stop only what this run started, so a failed start never leaves a half-running system.
        Write-Host '        Dang dung cac thanh phan vua khoi dong de tranh de he thong o trang thai nua chung...' -ForegroundColor DarkGray
        try {
            if ($script:StartedNow['backend']) { $p = Get-OwnProcess 'backend' $Py; if ($p) { Stop-Gracefully $p.Id 'May chu web/API' 20 }; Remove-Item -LiteralPath (Join-Path $RunDir 'backend.pid') -Force -ErrorAction SilentlyContinue }
            if ($script:StartedNow['ollama']) { $p = Get-OwnProcess 'ollama' $OllamaExe; if ($p) { Stop-Gracefully $p.Id 'Ollama' 20 }; Remove-Item -LiteralPath (Join-Path $RunDir 'ollama.pid') -Force -ErrorAction SilentlyContinue }
            if ($script:StartedNow['postgres']) { $null = Stop-PgServer $PgData }
            Write-Log 'Rollback sau khi khoi dong that bai: xong.'
        } catch { Write-Log "Rollback loi: $($_.Exception.Message)" 'ERROR'; Write-Host '        Khong dung het duoc; dung Stop-Server.bat de dung.' -ForegroundColor DarkGray }
    }
    exit 1
} finally {
    if ($lockStream) { $lockStream.Dispose() }
}
