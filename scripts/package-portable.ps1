<#
.SYNOPSIS
  Builds a clean, relocatable Evidence RAG package: copy the folder to any 64-bit Windows machine
  and run start.cmd. Nothing in the package refers to this machine's paths or IP addresses.

.PARAMETER ProgramsRoot
  Folder that contains EvidenceRAG\ (the development toolchain). Defaults to $env:EVIDENCE_PROGRAMS_ROOT.
.PARAMETER PackageDirectory
  Folder to create (must not exist; use -Force to replace a previous package built by this script).
.PARAMETER SkipBuild
  Reuse the current frontend\dist instead of rebuilding the web app.
.PARAMETER Zip
  Also write <PackageDirectory>.zip next to it.
#>
param(
    [string]$ProgramsRoot = $env:EVIDENCE_PROGRAMS_ROOT,
    [Parameter(Mandatory = $true)][string]$PackageDirectory,
    [switch]$SkipBuild,
    [switch]$Force,
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ProgramsRoot)) { throw 'Set EVIDENCE_PROGRAMS_ROOT or pass -ProgramsRoot.' }
$erag = Join-Path ([IO.Path]::GetFullPath($ProgramsRoot).TrimEnd('\', '/')) 'EvidenceRAG'
$package = [IO.Path]::GetFullPath($PackageDirectory).TrimEnd('\', '/')
$marker = Join-Path $package 'PORTABLE-MANIFEST.json'

# ---- locate the toolchain pieces (nothing hard-coded: derived from ProgramsRoot) ----
$venv = Join-Path $erag 'backend-venv'
$sitePackages = Join-Path $venv 'Lib\site-packages'
$venvCfg = Join-Path $venv 'pyvenv.cfg'
if (-not (Test-Path -LiteralPath $venvCfg)) { throw "Backend environment not found: $venv" }
$homeLine = Select-String -LiteralPath $venvCfg -Pattern '^\s*home\s*=' | Select-Object -First 1
if (-not $homeLine) { throw 'pyvenv.cfg has no home entry.' }
$pythonHome = ($homeLine.Line -replace '^\s*home\s*=\s*', '').Trim()
if (-not (Test-Path -LiteralPath (Join-Path $pythonHome 'python.exe'))) { throw "Base Python not found: $pythonHome" }
$pgRoots = @(Get-ChildItem -LiteralPath (Join-Path $erag 'postgresql') -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\pg_ctl.exe') })
if ($pgRoots.Count -ne 1) { throw "Expected exactly one PostgreSQL under $(Join-Path $erag 'postgresql'), found $($pgRoots.Count)." }
$pgHome = $pgRoots[0].FullName
$nodeExe = Join-Path $erag 'runtimes\node\node.exe'
$pnpmCjs = Join-Path $erag 'tools\pnpm\node_modules\pnpm\bin\pnpm.cjs'
$frontendDir = Join-Path $projectRoot 'frontend'
$distDir = Join-Path $frontendDir 'dist'
$templates = Join-Path $projectRoot 'deploy\portable'

# ---- target folder ----
if (Test-Path -LiteralPath $package) {
    if (-not $Force) { throw "Package folder exists: ${package} (use -Force to replace a package built by this script)." }
    if (-not (Test-Path -LiteralPath $marker)) { throw "Refusing to delete ${package} - it is not a package built by this script (no PORTABLE-MANIFEST.json)." }
    Remove-Item -LiteralPath $package -Recurse -Force
}
if ($package.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $projectRoot.StartsWith($package, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a package folder outside the source repository.'
}

function Copy-Tree([string]$Source, [string]$Target, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @()) {
    $opts = @('/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
    if ($ExcludeDirs.Count -gt 0) { $opts += '/XD'; $opts += $ExcludeDirs }
    if ($ExcludeFiles.Count -gt 0) { $opts += '/XF'; $opts += $ExcludeFiles }
    & robocopy.exe $Source $Target @opts | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $Source" }
    $global:LASTEXITCODE = 0
}

# ---- 1. web app ----
if (-not $SkipBuild) {
    foreach ($tool in $nodeExe, $pnpmCjs) { if (-not (Test-Path -LiteralPath $tool)) { throw "Missing build tool: $tool" } }
    Write-Host 'Building the web app...'
    Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
    & $nodeExe $pnpmCjs --dir $frontendDir build 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed. Run it by hand to see the errors.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $distDir 'index.html'))) { throw "No built web app at $distDir." }

New-Item -ItemType Directory -Force $package | Out-Null
# Written first so that a failed build can be replaced with -Force.
[IO.File]::WriteAllText($marker, '{ "status": "incomplete build" }', (New-Object Text.UTF8Encoding($false)))

Write-Host 'Copying the web app...'
Copy-Tree $distDir (Join-Path $package 'web') @() @('*.map', 'config.example.json')

# ---- 2. backend source (no tests, no caches) ----
Write-Host 'Copying the backend...'
Copy-Tree (Join-Path $projectRoot 'backend\app') (Join-Path $package 'app\backend\app') @('__pycache__')
New-Item -ItemType Directory -Force (Join-Path $package 'app\scripts') | Out-Null
foreach ($script in 'seed_local_runtime.py', 'import_official_corpus.py', 'rebuild_node_tree.py') {
    Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\$script") -Destination (Join-Path $package 'app\scripts')
}

# ---- 3. Python: relocatable base interpreter + the backend's packages (the venv itself is not relocatable) ----
Write-Host 'Copying Python...'
Copy-Tree $pythonHome (Join-Path $package 'runtime\python') `
    @('__pycache__', 'include', 'libs', 'tcl', 'Scripts', 'test', 'idlelib', 'turtledemo', 'tkinter', 'site-packages', 'ensurepip') `
    @('*.pyc', '_tkinter.pyd', 'tcl*.dll', 'tk*.dll')
Write-Host 'Copying Python packages...'
Copy-Tree $sitePackages (Join-Path $package 'runtime\site-packages') `
    @('__pycache__', 'mypy', 'mypyc', 'mypy-*.dist-info', 'mypy_extensions*', '_pytest', 'pytest', 'pytest-*.dist-info',
        'pytest_asyncio*', 'pluggy*', 'iniconfig*', 'ruff', 'ruff-*.dist-info', 'pip', 'pip-*.dist-info',
        'setuptools*', 'wheel*', 'pkg_resources', '_distutils_hack') `
    @('*.pyc', '_virtualenv.pth', '_virtualenv.py', 'distutils-precedence.pth', 'direct_url.json', 'ruff.exe')

# ---- 4. PostgreSQL (+ the VC++ runtime DLLs it needs, so nothing has to be installed) ----
Write-Host 'Copying PostgreSQL...'
Copy-Tree $pgHome (Join-Path $package 'runtime\postgresql') @('include', 'doc', 'symbols', 'pgAdmin 4', 'installer') @('*.pdb', 'wx*.dll', 'stackbuilder.exe')
foreach ($dll in 'vcruntime140.dll', 'vcruntime140_1.dll') {
    $from = Join-Path $pythonHome $dll
    if (Test-Path -LiteralPath $from) { Copy-Item -LiteralPath $from -Destination (Join-Path $package 'runtime\postgresql\bin') -Force }
}

# ---- 5. launcher, settings, guide ----
Write-Host 'Writing the launcher...'
foreach ($file in 'evidence.ps1', 'start.cmd', 'stop.cmd', 'status.cmd', 'open-firewall.cmd', 'close-firewall.cmd') {
    Copy-Item -LiteralPath (Join-Path $templates $file) -Destination $package
}
New-Item -ItemType Directory -Force (Join-Path $package 'config') | Out-Null
Copy-Item -LiteralPath (Join-Path $templates 'config\evidence.env') -Destination (Join-Path $package 'config')
# README.txt contains Vietnamese: write it with a BOM so Notepad on any machine shows it correctly.
$readme = [IO.File]::ReadAllText((Join-Path $templates 'README.txt'), [Text.Encoding]::UTF8)
[IO.File]::WriteAllText((Join-Path $package 'README.txt'), $readme, (New-Object Text.UTF8Encoding($true)))

# ---- 6. checks: nothing from this machine, and the packaged interpreter can load the app ----
Write-Host 'Checking the package...'
$needles = @($erag, $projectRoot, $pythonHome, $pgHome, 'backend-venv') | Where-Object { $_ } | Sort-Object -Unique
# Text and config files only. Compiled binaries may carry build-time source paths in assert
# messages (for example pgvector's vector.dll); those are never used to locate anything.
$textExt = '.ps1', '.cmd', '.txt', '.env', '.py', '.json', '.cfg', '.toml', '.conf', '.html', '.js', '.css', '.sql', '.pth', '.yaml', '.yml', '.md', '.sample', '.bat', '.ini'
$textFiles = Get-ChildItem -LiteralPath $package -Recurse -File | Where-Object { $textExt -contains $_.Extension.ToLowerInvariant() }
$leaks = @()
foreach ($needle in $needles) {
    $leaks += $textFiles |
        Select-String -SimpleMatch -Pattern $needle -List -ErrorAction SilentlyContinue |
        ForEach-Object { "{0}  (contains {1})" -f $_.Path.Substring($package.Length + 1), $needle }
}
if ($leaks.Count -gt 0) { $leaks | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }; throw 'Package refers to paths of this machine (listed above).' }

$python = Join-Path $package 'runtime\python\python.exe'
$saved = @{}
foreach ($name in 'PYTHONPATH', 'PYTHONNOUSERSITE', 'PYTHONPYCACHEPREFIX', 'DATABASE_URL') { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:PYTHONPATH = (Join-Path $package 'runtime\site-packages') + ';' + (Join-Path $package 'app\backend')
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONPYCACHEPREFIX = Join-Path ([IO.Path]::GetTempPath()) ('evidence-pkg-check-' + [guid]::NewGuid().ToString('N'))
    $check = & $python -s -c "import app.main, asyncpg, fastapi, uvicorn, pypdfium2, httpx, yaml, pydantic; print('imports ok')" 2>&1
    if ("$check" -notmatch 'imports ok') { throw "Packaged Python cannot load the app: $check" }
} finally {
    if ($env:PYTHONPYCACHEPREFIX -and $env:PYTHONPYCACHEPREFIX -like '*evidence-pkg-check-*') { Remove-Item -LiteralPath $env:PYTHONPYCACHEPREFIX -Recurse -Force -ErrorAction SilentlyContinue }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}

# ---- 7. manifest ----
$pyVersion = (& $python --version 2>&1 | Out-String).Trim()
$pgVersion = (& (Join-Path $package 'runtime\postgresql\bin\postgres.exe') --version 2>&1 | Out-String).Trim()
$appVersion = ([regex]::Match((Get-Content -LiteralPath (Join-Path $projectRoot 'backend\pyproject.toml') -Raw), '(?m)^version\s*=\s*"([^"]+)"')).Groups[1].Value
$measure = Get-ChildItem -LiteralPath $package -Recurse -File | Measure-Object Length -Sum
$manifest = [ordered]@{
    package_format = 1
    built_at       = (Get-Date).ToUniversalTime().ToString('o')
    app_version    = $appVersion
    python         = $pyVersion
    postgresql     = $pgVersion
    files          = $measure.Count
    size_mb        = [math]::Round($measure.Sum / 1MB, 1)
    contains       = 'clean package: no database, no documents, no accounts, no secrets; first start creates them'
}
[IO.File]::WriteAllText($marker, ($manifest | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))

if ($Zip) {
    Write-Host 'Compressing...'
    $zipPath = $package + '.zip'
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($package, $zipPath, [IO.Compression.CompressionLevel]::Optimal, $true)
    Write-Host ("Zip: {0} ({1:N0} MB)" -f $zipPath, ((Get-Item -LiteralPath $zipPath).Length / 1MB))
}
Write-Host ("Package ready: {0}  ({1} files, {2} MB)" -f $package, $measure.Count, $manifest.size_mb)
Write-Host 'Copy that folder to any 64-bit Windows machine and run start.cmd.'
