<#
.SYNOPSIS
  Builds Evidence-RAG-Portable: a self-contained Windows package that runs the whole system
  (web app, FastAPI, PostgreSQL + pgvector, Ollama with its models, Tesseract OCR) from one
  folder, offline, with the current database, vectors and source documents.

.DESCRIPTION
  Nothing is modified in the development environment: the database is read through a
  consistent snapshot (pg_dump), documents and runtimes are copied. The package restores the
  database into its own PostgreSQL cluster on first start (see deploy\lan-portable\tools).

.PARAMETER ProgramsRoot
  Folder that contains EvidenceRAG\ (development toolchain, models and data).
.PARAMETER OutputRoot
  Folder that will contain Evidence-RAG-Portable\ (must be outside the source repository).
.PARAMETER SourceDatabase
  Database to package. Default: the one the running development backend uses.
.PARAMETER SourceDocumentStore
  Document store (originals\, sources\) that belongs to that database.
.PARAMETER Zip
  Also write Evidence-RAG-Portable.zip (+ .sha256) next to the folder.
#>
param(
    [string]$ProgramsRoot = $env:EVIDENCE_PROGRAMS_ROOT,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$PackageName = 'Evidence-RAG-Portable',
    [string]$SourceDatabase = 'evidence_rerank_eval',
    [string]$SourceDocumentStore = '',
    [int]$SourcePgPort = 55432,
    [string]$SourcePgUser = 'evidence_dev_admin',
    [switch]$SkipWebBuild,
    [switch]$Force,
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = Split-Path -Parent $PSScriptRoot
$templates = Join-Path $repo 'deploy\lan-portable'
. (Join-Path $templates 'tools\portable-lib.ps1')
if ([string]::IsNullOrWhiteSpace($ProgramsRoot)) { throw 'Set EVIDENCE_PROGRAMS_ROOT or pass -ProgramsRoot.' }
$erag = Join-Path ([IO.Path]::GetFullPath($ProgramsRoot).TrimEnd('\', '/')) 'EvidenceRAG'
$outputRoot = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\', '/')
$package = Join-Path $outputRoot $PackageName
$work = Join-Path $outputRoot 'work'
$markerName = '.evidence-rag-portable-build'
$startedAt = Get-Date

function Say([string]$Text) { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $Text) }

if ($package.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase) -or $repo.StartsWith($package, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an output folder outside the source repository.'
}

# ---- toolchain (all derived from ProgramsRoot) ------------------------------------------------
$venv = Join-Path $erag 'backend-venv'
$sitePackages = Join-Path $venv 'Lib\site-packages'
$homeLine = Select-String -LiteralPath (Join-Path $venv 'pyvenv.cfg') -Pattern '^\s*home\s*=' | Select-Object -First 1
if (-not $homeLine) { throw 'pyvenv.cfg has no home entry.' }
$pythonHome = ($homeLine.Line -replace '^\s*home\s*=\s*', '').Trim()
$pgRoots = @(Get-ChildItem -LiteralPath (Join-Path $erag 'postgresql') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\pg_ctl.exe') })
if ($pgRoots.Count -ne 1) { throw "Expected exactly one PostgreSQL under $(Join-Path $erag 'postgresql'), found $($pgRoots.Count)." }
$pgHome = $pgRoots[0].FullName
$ollamaSource = Join-Path $erag 'tools\ollama'
$tessRoots = @(Get-ChildItem -LiteralPath (Join-Path $erag 'tools\tesseract') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'tesseract.exe') })
if ($tessRoots.Count -ne 1) { throw "Expected exactly one Tesseract under tools\tesseract, found $($tessRoots.Count)." }
$tessSource = $tessRoots[0].FullName
$modelsSource = Join-Path $erag 'models\ollama'
$nodeExe = Join-Path $erag 'runtimes\node\node.exe'
$pnpmCjs = Join-Path $erag 'tools\pnpm\node_modules\pnpm\bin\pnpm.cjs'
$frontendDir = Join-Path $repo 'frontend'
$distDir = Join-Path $frontendDir 'dist'
if (-not $SourceDocumentStore) { $SourceDocumentStore = Join-Path $erag 'data\rerank-eval\document-store' }
$pwFile = Join-Path $erag 'secrets\postgres-dev.password'
foreach ($required in $pythonHome, $sitePackages, $ollamaSource, $tessSource, $modelsSource, $SourceDocumentStore, $pwFile,
    (Join-Path $pgHome 'lib\vector.dll'), (Join-Path $pgHome 'share\extension\vector.control'), (Join-Path $ollamaSource 'ollama.exe')) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}

# ---- output folder ------------------------------------------------------------------------------
New-Item -ItemType Directory -Force $outputRoot, $work | Out-Null
if (Test-Path -LiteralPath $package) {
    if (-not $Force) { throw "Package folder exists: ${package} (use -Force to replace a package built by this script)." }
    if (-not (Test-Path -LiteralPath (Join-Path $package $markerName))) { throw "Refusing to delete ${package}: not built by this script." }
    if (Test-Path -LiteralPath (Join-Path $package 'data\postgres')) { throw "${package} has been started (data\postgres exists); it holds live data. Move it away first." }
    Remove-Item -LiteralPath $package -Recurse -Force
}
New-Item -ItemType Directory -Force $package | Out-Null
Write-Utf8File (Join-Path $package $markerName) 'incomplete build'

function Copy-Tree([string]$Source, [string]$Target, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @()) {
    $opts = @('/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:2', '/W:2', '/COPY:DAT', '/DCOPY:DAT')
    if ($ExcludeDirs.Count -gt 0) { $opts += '/XD'; $opts += $ExcludeDirs }
    if ($ExcludeFiles.Count -gt 0) { $opts += '/XF'; $opts += $ExcludeFiles }
    & robocopy.exe $Source $Target @opts | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $Source" }
    $global:LASTEXITCODE = 0
}

function Write-TextAsset([string]$Source, [string]$Target, [bool]$Bom) {
    $text = [IO.File]::ReadAllText($Source, [Text.Encoding]::UTF8)
    $text = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
    New-Item -ItemType Directory -Force (Split-Path -Parent $Target) | Out-Null
    [IO.File]::WriteAllText($Target, $text, (New-Object Text.UTF8Encoding($Bom)))
}

# ---- 1. source database: consistent snapshot, fingerprint, dump -----------------------------------
Say "Reading source database '$SourceDatabase' through a consistent snapshot..."
$sourceConn = @{
    Psql = Join-Path $pgHome 'bin\psql.exe'; Host = '127.0.0.1'; Port = $SourcePgPort; User = $SourcePgUser
    Password = (Get-Content -LiteralPath $pwFile -Raw).Trim(); Database = $SourceDatabase; WorkDir = $work
}
$seedDir = Join-Path $package 'seed'
New-Item -ItemType Directory -Force $seedDir | Out-Null
$dumpFile = Join-Path $seedDir 'evidence-rag.dump'
$snapshot = Open-DbSnapshot $sourceConn
try {
    $fingerprint = Get-DbFingerprint $sourceConn $snapshot.Id
    $rc = Invoke-Tool -Exe (Join-Path $pgHome 'bin\pg_dump.exe') -OutFile (Join-Path $work 'pg_dump.out.txt') -ErrFile (Join-Path $work 'pg_dump.err.txt') `
        -Environment @{ PGPASSWORD = $sourceConn.Password } -TimeoutSeconds 3600 -Arguments @(
        '-h', '127.0.0.1', '-p', "$SourcePgPort", '-U', $SourcePgUser, '-d', $SourceDatabase, '-Fc', '-Z', '6', '--no-owner', '--no-acl',
        '--exclude-table-data=public.auth_sessions', "--snapshot=$($snapshot.Id)", '-f', $dumpFile)
    if ($rc -ne 0) { throw "pg_dump failed: $(Read-TextOrEmpty (Join-Path $work 'pg_dump.err.txt'))" }
    # Registry facts for the manifest, read in the same snapshot.
    $q = @("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;", "SET TRANSACTION SNAPSHOT '$($snapshot.Id)';",
        "SELECT 'P|' || p.adapter || '|' || p.endpoint || '|' || mp.profile_key || '|' || mp.model_id || '|' || mp.capabilities::text FROM model_profiles mp JOIN providers p ON p.id = mp.provider_id ORDER BY mp.profile_key;",
        "SELECT 'R|' || r.mode || '|' || r.stage || '|' || mp.profile_key FROM stage_routes r JOIN model_profiles mp ON mp.id = r.profile_id ORDER BY 1;",
        "SELECT 'I|' || model_id || '|' || dimensions || '|' || is_active || '|' || status || '|' || node_count FROM embedding_indices ORDER BY created_at;",
        "SELECT 'U|' || u.username || '|' || coalesce((SELECT string_agg(role_code, ',' ORDER BY role_code) FROM user_roles ur WHERE ur.user_id = u.id), '') FROM users u ORDER BY u.username;",
        "SELECT 'C|' || (SELECT count(*) FROM auth_sessions);", 'COMMIT;')
    Write-Utf8File (Join-Path $work 'registry.sql') (($q -join "`n") + "`n")
    $registryText = Invoke-Psql $sourceConn -File (Join-Path $work 'registry.sql') -Tag 'registry'
} finally {
    Close-DbSnapshot $snapshot
}
$registryLines = @($registryText -split "`r?`n" | Where-Object { $_ -ne '' })
Say ("Snapshot {0}: {1} tables, schema {2}, dump {3:N1} MB" -f $snapshot.Id, $fingerprint.tables.Count, $fingerprint.schema_version, ((Get-Item -LiteralPath $dumpFile).Length / 1MB))

# Every model profile must be served by the bundled Ollama, otherwise the package could not run offline.
$profiles = @($registryLines | Where-Object { $_.StartsWith('P|') } | ForEach-Object {
        $p = $_.Split('|'); [pscustomobject]@{ Adapter = $p[1]; Endpoint = $p[2]; Key = $p[3]; Model = $p[4]; Capabilities = $p[5] } })
$nonLocal = @($profiles | Where-Object { $_.Adapter -ne 'ollama_local' -or $_.Endpoint -notmatch '^http://(127\.0\.0\.1|localhost):\d+/' })
if ($nonLocal.Count -gt 0) { throw ("Profiles that are not local Ollama (cannot run offline): " + (($nonLocal | ForEach-Object { $_.Key }) -join ', ')) }
$modelNames = @($profiles | ForEach-Object { $_.Model } | Select-Object -Unique)
Say ("Local models used by the registry: " + ($modelNames -join ', '))

# ---- 2. source documents -------------------------------------------------------------------------
Say 'Checking that every document the database references exists in the document store...'
$missingDocs = Test-DocumentReferences $sourceConn $SourceDocumentStore
if ($missingDocs.Count -gt 0) { throw ("Document store is missing files referenced by the database: " + (($missingDocs | Select-Object -First 5) -join ', ')) }
Say 'Copying source documents (originals, sources)...'
$docTarget = Join-Path $package 'data\documents'
foreach ($folder in 'originals', 'sources') {
    if (Test-Path -LiteralPath (Join-Path $SourceDocumentStore $folder)) { Copy-Tree (Join-Path $SourceDocumentStore $folder) (Join-Path $docTarget $folder) }
}
$docCheck = Test-DocumentStore $docTarget
if ($docCheck.Mismatched.Count -gt 0) { throw ("Copied documents differ from their SHA-256 names: " + ($docCheck.Mismatched -join ', ')) }
if ($docCheck.Unexpected.Count -gt 0) { throw ("Document store has files that are not named by SHA-256: " + ($docCheck.Unexpected -join ', ')) }
Say "Documents: $($docCheck.Files) files, every SHA-256 equals its file name."

# ---- 3. web app ----------------------------------------------------------------------------------
if (-not $SkipWebBuild) {
    foreach ($tool in $nodeExe, $pnpmCjs) { if (-not (Test-Path -LiteralPath $tool)) { throw "Missing build tool: $tool" } }
    Say 'Building the web app...'
    $oldPath = $env:PATH
    $env:PATH = (Split-Path $nodeExe) + ';' + $env:PATH
    try {
        Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
        $rc = Invoke-Tool -Exe $nodeExe -Arguments @($pnpmCjs, '--dir', $frontendDir, 'build') -OutFile (Join-Path $work 'web-build.out.txt') -ErrFile (Join-Path $work 'web-build.err.txt') -TimeoutSeconds 1200
        if ($rc -ne 0) { throw "Web build failed; see $(Join-Path $work 'web-build.out.txt')" }
    } finally { $env:PATH = $oldPath }
}
if (-not (Test-Path -LiteralPath (Join-Path $distDir 'index.html'))) { throw "No built web app at $distDir." }
Say 'Copying the web app...'
Copy-Tree $distDir (Join-Path $package 'app\web') @() @('*.map', 'config.example.json')

# ---- 4. backend ----------------------------------------------------------------------------------
Say 'Copying the backend...'
Copy-Tree (Join-Path $repo 'backend\app') (Join-Path $package 'app\backend\app') @('__pycache__')

# ---- 5. runtimes ---------------------------------------------------------------------------------
Say 'Copying Python...'
Copy-Tree $pythonHome (Join-Path $package 'runtime\python') `
(@('__pycache__', 'include', 'libs', 'tcl', 'Scripts', 'test', 'idlelib', 'turtledemo', 'tkinter', 'site-packages', 'ensurepip')) `
(@('*.pyc', '_tkinter.pyd', 'tcl*.dll', 'tk*.dll', 'pythonw.exe'))
Say 'Copying Python packages (backend dependencies only)...'
Copy-Tree $sitePackages (Join-Path $package 'runtime\site-packages') `
(@('__pycache__', 'mypy', 'mypyc', 'mypy-*.dist-info', 'mypy_extensions*', '_pytest', 'pytest', 'pytest-*.dist-info',
        'pytest_asyncio*', 'pluggy*', 'iniconfig*', 'ruff', 'ruff-*.dist-info', 'pip', 'pip-*.dist-info', 'setuptools*', 'wheel*',
        'pkg_resources', '_distutils_hack', 'vietnamese_evidence_agent*')) `
(@('*.pyc', '_virtualenv.pth', '_virtualenv.py', 'distutils-precedence.pth', 'direct_url.json', 'ruff.exe', '*.pth'))

Say 'Copying PostgreSQL + pgvector...'
Copy-Tree $pgHome (Join-Path $package 'runtime\postgresql') @('include', 'doc', 'symbols', 'pgAdmin 4', 'installer') @('*.pdb', 'wx*.dll', 'stackbuilder.exe')
foreach ($dll in 'vcruntime140.dll', 'vcruntime140_1.dll') {
    $from = Join-Path $pythonHome $dll
    if (-not (Test-Path -LiteralPath $from)) { throw "Cannot bundle $dll (not next to the development Python)." }
    Copy-Item -LiteralPath $from -Destination (Join-Path $package 'runtime\postgresql\bin') -Force
}
$msvcp = Join-Path $env:SystemRoot 'System32\msvcp140.dll'
if (-not (Test-Path -LiteralPath $msvcp)) { throw 'msvcp140.dll (needed by PostgreSQL ICU) not found on this machine; install the VC++ redistributable once on the build machine.' }
Copy-Item -LiteralPath $msvcp -Destination (Join-Path $package 'runtime\postgresql\bin') -Force

Say 'Copying Ollama runtime (CPU, CUDA and Vulkan back ends)...'
Copy-Tree $ollamaSource (Join-Path $package 'runtime\ollama')

Say 'Copying Tesseract OCR (vie, eng, osd)...'
Copy-Tree $tessSource (Join-Path $package 'runtime\tesseract') @('doc', 'script') `
(@('ambiguous_words.exe', 'classifier_tester.exe', 'cntraining.exe', 'combine_lang_model.exe', 'combine_tessdata.exe', 'dawg2wordlist.exe',
        'lstmeval.exe', 'lstmtraining.exe', 'merge_unicharsets.exe', 'mftraining.exe', 'set_unicharset_properties.exe', 'shapeclustering.exe',
        'tesseract-uninstall.exe', 'text2image.exe', 'unicharset_extractor.exe', 'winpath.exe', 'wordlist2dawg.exe', '*.html', '*.jar',
        'enm.traineddata', 'equ.traineddata', 'lat.traineddata'))

Say 'Copying local AI models (Ollama store: manifests + weights)...'
Copy-Tree $modelsSource (Join-Path $package 'models\ollama')

# ---- 6. launcher, config, guides -----------------------------------------------------------------
Say 'Writing launcher, configuration and guide...'
foreach ($file in 'Start-Server.bat', 'Stop-Server.bat', 'Backup-Data.bat', 'Restore-Data.bat') { Write-TextAsset (Join-Path $templates $file) (Join-Path $package $file) $false }
foreach ($file in 'Allow-LAN-Firewall.bat', 'Verify-Package.bat', 'Status.bat') { Write-TextAsset (Join-Path $templates "tools\$file") (Join-Path $package "tools\$file") $false }
foreach ($file in 'portable.ps1', 'portable-lib.ps1') { Write-TextAsset (Join-Path $templates "tools\$file") (Join-Path $package "tools\$file") $true }
Write-TextAsset (Join-Path $templates 'config\evidence.env') (Join-Path $package 'config\evidence.env') $true
Write-TextAsset (Join-Path $templates 'README.txt') (Join-Path $package 'README.txt') $true
foreach ($file in 'README.en.txt', 'HUONG_DAN_SU_DUNG.vi.md', 'USER_GUIDE.en.md') { Write-TextAsset (Join-Path $templates $file) (Join-Path $package $file) $true }
foreach ($dir in 'logs', 'run', 'backups', 'secrets') { New-Item -ItemType Directory -Force (Join-Path $package $dir) | Out-Null }
foreach ($dir in 'logs', 'run', 'backups', 'secrets') { Write-Utf8File (Join-Path $package "$dir\.keep") '' }

# ---- 7. checks on the staged package -------------------------------------------------------------------
Say 'Checking the staged package...'
$python = Join-Path $package 'runtime\python\python.exe'
$cleanEnv = @{ PYTHONPATH = ((Join-Path $package 'runtime\site-packages') + ';' + (Join-Path $package 'app\backend')); PYTHONNOUSERSITE = '1'
    PYTHONPYCACHEPREFIX = (Join-Path $work 'pycache-check'); DATABASE_URL = '' }
$rc = Invoke-Tool -Exe $python -Arguments @('-s', '-c', 'import app.main, asyncpg, fastapi, uvicorn, pypdfium2, httpx, yaml, pydantic, PIL, fpdf, olefile, defusedxml, multipart, httptools, websockets, sys; print("imports ok", sys.version.split()[0])') `
    -OutFile (Join-Path $work 'py-check.out.txt') -ErrFile (Join-Path $work 'py-check.err.txt') -Environment $cleanEnv -TimeoutSeconds 120
if ($rc -ne 0 -or (Read-TextOrEmpty (Join-Path $work 'py-check.out.txt')) -notmatch 'imports ok') { throw "Packaged Python cannot load the app: $(Read-TextOrEmpty (Join-Path $work 'py-check.err.txt'))" }
$pythonVersion = ((Read-TextOrEmpty (Join-Path $work 'py-check.out.txt')).Trim() -split '\s+')[-1]

function Get-ToolText([string]$Exe, [string[]]$Arguments, [string]$Name) {
    $null = Invoke-Tool -Exe $Exe -Arguments $Arguments -OutFile (Join-Path $work "$Name.out.txt") -ErrFile (Join-Path $work "$Name.err.txt") -TimeoutSeconds 60
    return ((Read-TextOrEmpty (Join-Path $work "$Name.out.txt")) + (Read-TextOrEmpty (Join-Path $work "$Name.err.txt"))).Trim()
}
$pgText = Get-ToolText (Join-Path $package 'runtime\postgresql\bin\postgres.exe') @('--version') 'pgver'
if ($pgText -notmatch 'PostgreSQL\)?\s+(\d+)\.(\d+)') { throw "Cannot run the packaged PostgreSQL: $pgText" }
$pgVersion = "$($Matches[1]).$($Matches[2])"; $pgMajor = $Matches[1]
$ollamaText = Get-ToolText (Join-Path $package 'runtime\ollama\ollama.exe') @('--version') 'ollamaver'
if ($ollamaText -notmatch '(?:ollama|client) version is ([\d\.]+)') { throw "Cannot run the packaged Ollama: $ollamaText" }
$ollamaVersion = $Matches[1]
$tessText = Get-ToolText (Join-Path $package 'runtime\tesseract\tesseract.exe') @('--version') 'tessver'
if ($tessText -notmatch 'tesseract v?([\d\.]+)') { throw "Cannot run the packaged Tesseract: $tessText" }
$tessVersion = $Matches[1]
$langText = Get-ToolText (Join-Path $package 'runtime\tesseract\tesseract.exe') @('--tessdata-dir', (Join-Path $package 'runtime\tesseract\tessdata'), '--list-langs') 'tesslangs'
foreach ($lang in 'vie', 'eng', 'osd') { if ($langText -notmatch "(?m)^$lang\s*$") { throw "Tesseract data '$lang' missing: $langText" } }
$pgvectorVersion = [string]$fingerprint.extensions['vector']
Say "Python $pythonVersion, PostgreSQL $pgVersion, pgvector $pgvectorVersion, Ollama $ollamaVersion, Tesseract $tessVersion (vie+eng+osd)"

# No development-machine path may be baked into text files shipped in the package.
$needles = @($erag, $repo, $pythonHome, $pgHome, $SourceDocumentStore, $ProgramsRoot.TrimEnd('\', '/')) | Where-Object { $_ } | Sort-Object -Unique
$textExt = '.ps1', '.bat', '.cmd', '.txt', '.env', '.py', '.json', '.cfg', '.toml', '.conf', '.html', '.js', '.css', '.sql', '.yaml', '.yml', '.md', '.sample', '.ini'
$leaks = @()
foreach ($file in Get-ChildItem -LiteralPath $package -Recurse -File | Where-Object { ($textExt -contains $_.Extension.ToLowerInvariant()) -and $_.Length -lt 5MB -and $_.FullName -notlike '*\models\*' -and $_.FullName -notlike '*\data\documents\*' }) {
    $content = [IO.File]::ReadAllText($file.FullName)
    foreach ($needle in $needles) {
        if ($content.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $leaks += "$($file.FullName.Substring($package.Length + 1)) (contains $needle)" }
    }
}
if ($leaks.Count -gt 0) { $leaks | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }; throw 'Package contains paths of the build machine.' }
# certifi\cacert.pem is the public CA bundle of the HTTP library, not a secret.
$secretLike = @(Get-ChildItem -LiteralPath $package -Recurse -File | Where-Object {
        $_.Name -match '(?i)(\.password|\.pem|\.key|id_ed25519|first-login|\.local)$' -and $_.FullName -notlike '*\site-packages\certifi\*' })
if ($secretLike.Count -gt 0) { throw ("Secret-looking files in package: " + (($secretLike | ForEach-Object { $_.FullName }) -join ', ')) }

# ---- 8. manifest and checksums -------------------------------------------------------------------------
$builtAt = (Get-Date).ToUniversalTime().ToString('o')
$seedManifest = [ordered]@{
    format = 1; created_at_utc = $builtAt; source_database = $SourceDatabase; dump_sha256 = (Get-FileSha256 $dumpFile)
    note = 'fingerprint = row count + md5 of every row text per table, rendered in UTC; verified after the first-start restore'
    fingerprint = $fingerprint
}
Write-Utf8File (Join-Path $seedDir 'seed-manifest.json') ($seedManifest | ConvertTo-Json -Depth 12)

Say 'Computing SHA-256 of every file (runtime, models, app, documents, seed)...'
$sums = New-Object System.Collections.Generic.List[string]
$dirStats = [ordered]@{}
$badBlobs = @()
$badDocs = @()
$files = Get-ChildItem -LiteralPath $package -Recurse -File | Sort-Object FullName
foreach ($file in $files) {
    $rel = $file.FullName.Substring($package.Length + 1)
    $top = ($rel -split '\\')[0]
    if ($rel -eq $markerName -or $rel -like 'config\*' -or $rel -like 'logs\*' -or $rel -like 'run\*' -or $rel -like 'backups\*' -or $rel -like 'secrets\*' -or $rel -eq 'MANIFEST.json' -or $rel -eq 'checksums.sha256') { continue }
    $hash = Get-FileSha256 $file.FullName
    $sums.Add("$hash  $rel")
    if ($rel -like 'models\ollama\blobs\sha256-*' -and $file.Name -ne ('sha256-' + $hash)) { $badBlobs += $rel }
    if ($rel -like 'data\documents\*' -and [IO.Path]::GetFileNameWithoutExtension($file.Name) -ne $hash) { $badDocs += $rel }
}
if ($badBlobs.Count -gt 0) { throw ("Model blobs whose SHA-256 differs from their name: " + ($badBlobs -join ', ')) }
if ($badDocs.Count -gt 0) { throw ("Documents whose SHA-256 differs from their name: " + ($badDocs -join ', ')) }
Write-Utf8File (Join-Path $package 'checksums.sha256') (($sums -join "`n") + "`n")

function Get-FolderStats([string]$Relative) {
    $items = @(Get-ChildItem -LiteralPath (Join-Path $package $Relative) -Recurse -File -ErrorAction SilentlyContinue)
    $total = ($items | Measure-Object Length -Sum).Sum
    return [ordered]@{ path = $Relative.Replace('\', '/'); files = $items.Count; size_bytes = [int64]$total }
}

$models = @()
foreach ($name in $modelNames) {
    $parts = $name.Split(':'); $repoName = $parts[0]; $tag = $(if ($parts.Count -gt 1) { $parts[1] } else { 'latest' })
    if ($repoName -notmatch '/') { $repoName = "library/$repoName" }
    $relManifest = "manifests/registry.ollama.ai/$repoName/$tag"
    $manifestFile = Join-Path $package ('models\ollama\' + $relManifest.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $manifestFile)) { throw "Ollama manifest for $name not found in the model store: $relManifest" }
    $mm = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $weights = @($mm.layers | Where-Object { $_.mediaType -eq 'application/vnd.ollama.image.model' })[0]
    $blobBytes = ([int64]$mm.config.size) + (($mm.layers | Measure-Object size -Sum).Sum)
    $isEmbedding = @($profiles | Where-Object { $_.Model -eq $name -and $_.Capabilities -match 'embedding' }).Count -gt 0
    $dims = 0
    if ($isEmbedding) {
        $row = @($registryLines | Where-Object { $_.StartsWith("I|$name|") } | Select-Object -First 1)
        if ($row.Count -gt 0) { $dims = [int]$row[0].Split('|')[2] }
    }
    $roles = @($profiles | Where-Object { $_.Model -eq $name } | ForEach-Object { $_.Capabilities.Trim('[', ']') -replace '"', '' } | Select-Object -Unique)
    $models += [ordered]@{
        name = $name; role = $(if ($isEmbedding) { 'embedding' } else { 'generate' }); capabilities = $roles; dimensions = $dims
        manifest = $relManifest; weights_sha256 = ([string]$weights.digest).Replace('sha256:', ''); size_bytes = $blobBytes
        profiles = @($profiles | Where-Object { $_.Model -eq $name } | ForEach-Object { $_.Key })
    }
}

$sitePackageList = @(Get-ChildItem -LiteralPath (Join-Path $package 'runtime\site-packages') -Directory -Filter '*.dist-info' | ForEach-Object { $_.Name -replace '\.dist-info$', '' } | Sort-Object)
$appVersion = ([regex]::Match((Get-Content -LiteralPath (Join-Path $repo 'backend\pyproject.toml') -Raw), '(?m)^version\s*=\s*"([^"]+)"')).Groups[1].Value
$tableRows = [ordered]@{}
foreach ($key in 'documents', 'document_versions', 'document_nodes', 'node_embeddings', 'embedding_indices', 'source_pages', 'users', 'audit_events', 'categories', 'model_profiles', 'providers', 'stage_routes') {
    if ($fingerprint.tables.Contains($key)) { $tableRows[$key] = $fingerprint.tables[$key].rows }
}
$manifest = [ordered]@{
    package    = [ordered]@{ name = $PackageName; version = "$appVersion+$((Get-Date).ToString('yyyyMMdd'))"; format = 2; built_at_utc = $builtAt
        platform = 'Windows x64 (Windows 10 / Server 2016 or newer)'; offline = $true
        entry_points = @('Start-Server.bat', 'Stop-Server.bat', 'Backup-Data.bat', 'Restore-Data.bat') }
    components = [ordered]@{
        python     = [ordered]@{ version = $pythonVersion; folder = Get-FolderStats 'runtime\python'; packages = $sitePackageList.Count; packages_folder = Get-FolderStats 'runtime\site-packages' }
        postgresql = [ordered]@{ version = $pgVersion; major = $pgMajor; folder = Get-FolderStats 'runtime\postgresql'; pgvector = $pgvectorVersion; extensions = $fingerprint.extensions }
        ollama     = [ordered]@{ version = $ollamaVersion; folder = Get-FolderStats 'runtime\ollama'; listens = '127.0.0.1 only' }
        tesseract  = [ordered]@{ version = $tessVersion; languages = @('vie', 'eng', 'osd'); folder = Get-FolderStats 'runtime\tesseract' }
        backend    = [ordered]@{ version = $appVersion; folder = Get-FolderStats 'app\backend' }
        web        = [ordered]@{ folder = Get-FolderStats 'app\web' }
    }
    models     = $models
    ai_registry = [ordered]@{
        profiles = @($profiles | ForEach-Object { [ordered]@{ key = $_.Key; model = $_.Model; adapter = $_.Adapter; capabilities = $_.Capabilities } })
        routes   = @($registryLines | Where-Object { $_.StartsWith('R|') } | ForEach-Object { $r = $_.Split('|'); [ordered]@{ mode = $r[1]; stage = $r[2]; profile = $r[3] } })
        embedding_indices = @($registryLines | Where-Object { $_.StartsWith('I|') } | ForEach-Object { $r = $_.Split('|'); [ordered]@{ model = $r[1]; dimensions = [int]$r[2]; active = ($r[3] -eq 't'); status = $r[4]; nodes = [int]$r[5] } })
        note     = 'Provider endpoints are rewritten to the bundled Ollama port on first start. No API key or token is stored in the database.'
    }
    data       = [ordered]@{
        source_database = $SourceDatabase
        schema_version  = $fingerprint.schema_version
        rows            = $tableRows
        accounts        = @($registryLines | Where-Object { $_.StartsWith('U|') } | ForEach-Object { $u = $_.Split('|'); [ordered]@{ username = $u[1]; roles = $u[2] } })
        documents_store = [ordered]@{ folder = Get-FolderStats 'data\documents'; sha256_equals_file_name = $true }
        seed            = [ordered]@{ dump = 'seed/evidence-rag.dump'; sha256 = (Get-FileSha256 $dumpFile); size_bytes = (Get-Item -LiteralPath $dumpFile).Length
            excluded_table_data = @('auth_sessions (login sessions are never shipped)') }
    }
    excluded   = @('source code of tests, dev tools, caches, mypy/ruff/pytest', 'Qwen3-Reranker cross-encoder model and its PyTorch environment (optional, off by default: EVIDENCE_RERANK_BACKEND=llm)',
        'Node.js / pnpm / Rust / Tauri build tools', 'development backups, logs, secrets, API keys, login sessions', 'PostgreSQL headers, docs, pgAdmin, stack builder')
    checksums  = [ordered]@{ file = 'checksums.sha256'; files = $sums.Count; algorithm = 'SHA-256'; excludes = 'config/, logs/, run/, backups/, secrets/ (changeable at run time)' }
    totals     = [ordered]@{ files = $files.Count; size_bytes = [int64](($files | Measure-Object Length -Sum).Sum) }
}
Write-Utf8File (Join-Path $package 'MANIFEST.json') ($manifest | ConvertTo-Json -Depth 12)

Remove-Item -LiteralPath (Join-Path $package $markerName) -Force
Write-Utf8File (Join-Path $package $markerName) 'build complete'

$report = [ordered]@{
    built_at_utc = $builtAt; package = $package; manifest_totals = $manifest.totals
    source = [ordered]@{ database = $SourceDatabase; document_store_files = $docCheck.Files; snapshot = $snapshot.Id; rows = $tableRows }
    models = $models | ForEach-Object { [ordered]@{ name = $_.name; weights_sha256 = $_.weights_sha256; size_bytes = $_.size_bytes } }
    fingerprint = $fingerprint
}
Write-Utf8File (Join-Path $outputRoot "$PackageName.build-report.json") ($report | ConvertTo-Json -Depth 12)

if ($Zip) {
    Say 'Compressing (models are already compressed; this takes a few minutes)...'
    $zipPath = $package + '.zip'
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($package, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $true)
    $zipHash = Get-FileSha256 $zipPath
    Write-Utf8File ($zipPath + '.sha256') ("$zipHash  $PackageName.zip`n")
    Say ("Zip: {0} ({1:N0} MB) sha256 {2}" -f $zipPath, ((Get-Item -LiteralPath $zipPath).Length / 1MB), $zipHash)
}
Say ("Package ready: {0}  ({1} files, {2:N0} MB) in {3:N1} minutes" -f $package, $files.Count, ($manifest.totals.size_bytes / 1MB), ((Get-Date) - $startedAt).TotalMinutes)
