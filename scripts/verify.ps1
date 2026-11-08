param(
    [string]$ProgramsRoot = $env:EVIDENCE_PROGRAMS_ROOT,
    [string]$ToolchainConfig,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
if ($env:CI -eq 'true' -and [string]::IsNullOrWhiteSpace($env:EVIDENCE_TEST_DATABASE_URL)) {
    throw 'CI must set EVIDENCE_TEST_DATABASE_URL; PostgreSQL integration tests may not be skipped.'
}
if ([string]::IsNullOrWhiteSpace($ProgramsRoot)) {
    throw 'Set EVIDENCE_PROGRAMS_ROOT or pass -ProgramsRoot. Global PATH fallback is disabled.'
}
if (-not [IO.Path]::IsPathRooted($ProgramsRoot) -or -not (Test-Path -LiteralPath $ProgramsRoot -PathType Container)) {
    throw 'ProgramsRoot must be an existing absolute directory.'
}
if (-not $ToolchainConfig) {
    $ToolchainConfig = Join-Path $taskProjectRoot 'configs/development-toolchain.json'
}
$taskConfig = Get-Content -LiteralPath $ToolchainConfig -Raw -Encoding UTF8 | ConvertFrom-Json
$taskProgramsPath = [IO.Path]::GetFullPath($ProgramsRoot).TrimEnd('\', '/')
$taskAllowedPrefix = $taskProgramsPath + [IO.Path]::DirectorySeparatorChar

function Resolve-TaskExecutable([string]$Name) {
    $taskRelative = [string]$taskConfig.executables.$Name
    if (-not $taskRelative -or [IO.Path]::IsPathRooted($taskRelative)) {
        throw ('Invalid relative tool path: {0}' -f $Name)
    }
    $taskExecutable = [IO.Path]::GetFullPath(
        (Join-Path (Join-Path $taskProgramsPath $taskConfig.root_subdirectory) $taskRelative)
    )
    if (-not $taskExecutable.StartsWith($taskAllowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Tool escapes ProgramsRoot: {0}' -f $Name)
    }
    if (-not (Test-Path -LiteralPath $taskExecutable -PathType Leaf)) {
        throw ('Missing tool under ProgramsRoot: {0}' -f $Name)
    }
    return $taskExecutable
}

$taskPython = Resolve-TaskExecutable 'python'
$taskNode = Resolve-TaskExecutable 'node'
$taskPnpm = Resolve-TaskExecutable 'pnpm'
$taskUv = Resolve-TaskExecutable 'uv'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $taskProjectRoot ('docs/evidence/verification-' + (Get-Date -Format 'yyyy-MM-dd-HHmmss'))
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$taskChecks = @(
    @{name='dependency-check'; exe=$taskUv; arguments=@('pip','check','--python',$taskPython)},
    @{name='backend-lint'; exe=$taskPython; arguments=@('-m','ruff','check','backend/app','backend/tests','scripts')},
    @{name='backend-typing'; exe=$taskPython; arguments=@('-m','mypy','--config-file','backend/pyproject.toml','backend/app')},
    @{name='backend-tests'; exe=$taskPython; arguments=@('-m','pytest','backend/tests','-q','--tb=short')},
    @{name='source-policy'; exe=$taskPython; arguments=@('scripts/validate_no_literal_runtime_paths.py')},
    @{name='migration-pairs'; exe=$taskPython; arguments=@('scripts/validate_migrations.py')},
    @{name='openapi'; exe=$taskPython; arguments=@('scripts/export_openapi.py','--check')},
    @{name='polarity-fixtures'; exe=$taskPython; arguments=@('evaluation/scripts/polarity_tests.py')},
    @{name='temporal-fixtures'; exe=$taskPython; arguments=@('evaluation/scripts/temporal_graph_tests.py')},
    @{name='frontend-lint'; exe=$taskNode; arguments=@($taskPnpm,'--dir','frontend','lint')},
    @{name='frontend-tests'; exe=$taskNode; arguments=@($taskPnpm,'--dir','frontend','test')},
    @{name='frontend-build'; exe=$taskNode; arguments=@($taskPnpm,'--dir','frontend','build')}
)
$taskOldPath = $env:PATH
$taskOldEncoding = $env:PYTHONIOENCODING
$taskResults = @()
Push-Location $taskProjectRoot
try {
    $env:PATH = (Split-Path $taskNode) + ';' + (Split-Path $taskPython) + ';' + $taskOldPath
    $env:PYTHONIOENCODING = 'utf-8'
    foreach ($taskCheck in $taskChecks) {
        $taskLogName = $taskCheck.name + '.txt'
        $taskArguments = $taskCheck.arguments
        # Windows PowerShell 5.1 turns native stderr into terminating errors under 'Stop'.
        $taskPreviousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $taskCheck.exe @taskArguments *> (Join-Path $OutputDirectory $taskLogName)
            $taskExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $taskPreviousPreference
        }
        $taskResults += [PSCustomObject]@{name=$taskCheck.name; exit_code=$taskExitCode; log=$taskLogName}
        Write-Host ('{0}: {1}' -f $taskCheck.name, $taskExitCode)
    }
} finally {
    Pop-Location
    $env:PATH = $taskOldPath
    $env:PYTHONIOENCODING = $taskOldEncoding
}
$taskResults | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'summary.json') -Encoding UTF8
if (@($taskResults | Where-Object { $_.exit_code -ne 0 }).Count -gt 0) {
    exit 1
}
