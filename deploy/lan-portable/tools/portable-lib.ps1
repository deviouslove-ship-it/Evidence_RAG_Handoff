# Evidence RAG - shared helpers for the LAN portable launcher and the package builder.
# Functions only: dot-sourcing this file has no side effects. Keep it Windows PowerShell 5.1 compatible.

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function ConvertTo-ArgText([string]$Value) {
    if ($Value -eq '') { return '""' }
    if ($Value -match '[\s"]') {
        $escaped = $Value -replace '(\\*)"', '$1$1\"'
        $escaped = $escaped -replace '(\\+)$', '$1$1'
        return '"' + $escaped + '"'
    }
    return $Value
}

function Write-Utf8File([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $script:Utf8NoBom)
}

# Runs a program hidden with stdout/stderr redirected to files and waits for it. Never uses
# "Start-Process -Wait": a database server started by the tool would keep that wait open.
# Environment values are applied to this process for the duration of the call only.
function Invoke-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$OutFile,
        [Parameter(Mandatory = $true)][string]$ErrFile,
        [hashtable]$Environment = @{},
        [int]$TimeoutSeconds = 600,
        [string]$WorkingDirectory = ''
    )
    $saved = @{}
    foreach ($key in @($Environment.Keys)) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
    }
    try {
        $splat = @{
            FilePath = $Exe; WindowStyle = 'Hidden'; PassThru = $true
            RedirectStandardOutput = $OutFile; RedirectStandardError = $ErrFile
        }
        if ($Arguments.Count -gt 0) { $splat.ArgumentList = (($Arguments | ForEach-Object { ConvertTo-ArgText $_ }) -join ' ') }
        if ($WorkingDirectory) { $splat.WorkingDirectory = $WorkingDirectory }
        $proc = Start-Process @splat
        $null = $proc.Handle
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch { }
            throw "Tien trinh $([IO.Path]::GetFileName($Exe)) vuot qua thoi gian cho ($TimeoutSeconds giay)."
        }
        return $proc.ExitCode
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
}

function Read-TextOrEmpty([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $text) { return '' }
    return [string]$text
}

function Get-FileSha256([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = New-Object IO.FileStream($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite, 1048576)
    try {
        $buffer = New-Object byte[] 1048576
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) { $null = $sha.TransformBlock($buffer, 0, $read, $null, 0) }
        $null = $sha.TransformFinalBlock($buffer, 0, 0)
        return ([BitConverter]::ToString($sha.Hash) -replace '-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose(); $sha.Dispose()
    }
}

# ---- PostgreSQL helpers -------------------------------------------------------------------
# $Conn = @{ Psql=...; Host=...; Port=...; User=...; Password=...; Database=...; WorkDir=... }

function Invoke-Psql {
    param([hashtable]$Conn, [string[]]$Statements = @(), [string]$File = '', [string]$Database = '', [int]$TimeoutSeconds = 600, [string]$Tag = 'psql')
    $db = if ($Database) { $Database } else { $Conn.Database }
    $arguments = @('-X', '-q', '-At', '-v', 'ON_ERROR_STOP=1', '-h', $Conn.Host, '-p', "$($Conn.Port)", '-U', $Conn.User, '-d', $db)
    foreach ($statement in $Statements) { $arguments += @('-c', $statement) }
    if ($File) { $arguments += @('-f', $File) }
    $out = Join-Path $Conn.WorkDir "$Tag.out.txt"
    $err = Join-Path $Conn.WorkDir "$Tag.err.txt"
    $rc = Invoke-Tool -Exe $Conn.Psql -Arguments $arguments -OutFile $out -ErrFile $err `
        -Environment @{ PGPASSWORD = $Conn.Password; PGCLIENTENCODING = 'UTF8' } -TimeoutSeconds $TimeoutSeconds
    $text = Read-TextOrEmpty $out
    if ($rc -ne 0) {
        $errText = (Read-TextOrEmpty $err).Trim()
        throw "psql loi (ma $rc): $errText"
    }
    return $text
}

# Exports a snapshot from a session that stays open until Close-DbSnapshot, so pg_dump and the
# fingerprint queries describe exactly the same state of a database that is in use.
function Open-DbSnapshot([hashtable]$Conn) {
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Conn.Psql
    $psi.Arguments = "-X -q -At -h $($Conn.Host) -p $($Conn.Port) -U $($Conn.User) -d $($Conn.Database)"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['PGPASSWORD'] = $Conn.Password
    $psi.EnvironmentVariables['PGCLIENTENCODING'] = 'UTF8'
    $proc = [Diagnostics.Process]::Start($psi)
    $proc.StandardInput.WriteLine('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;')
    $proc.StandardInput.WriteLine('SELECT pg_export_snapshot();')
    $proc.StandardInput.Flush()
    $task = $proc.StandardOutput.ReadLineAsync()
    if (-not $task.Wait(30000) -or [string]::IsNullOrWhiteSpace($task.Result)) {
        try { $proc.Kill() } catch { }
        throw 'Khong tao duoc anh chup (snapshot) nhat quan cua co so du lieu.'
    }
    return [pscustomobject]@{ Id = $task.Result.Trim(); Process = $proc }
}

function Close-DbSnapshot($Snapshot) {
    if ($null -eq $Snapshot) { return }
    try {
        if (-not $Snapshot.Process.HasExited) {
            $Snapshot.Process.StandardInput.WriteLine('COMMIT;')
            $Snapshot.Process.StandardInput.WriteLine('\q')
            $Snapshot.Process.StandardInput.Flush()
            if (-not $Snapshot.Process.WaitForExit(5000)) { $Snapshot.Process.Kill() }
        }
    } catch { }
}

# Content fingerprint of every public table (row count + md5 over all row texts). Rows are
# rendered in UTC with fixed date/interval styles so the result does not depend on the machine.
function Get-DbFingerprint {
    param([hashtable]$Conn, [string]$SnapshotId = '', [string[]]$SkipTables = @('auth_sessions'))
    $names = @((Invoke-Psql $Conn @("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1") -Tag 'fp-tables') -split "`r?`n" |
            Where-Object { $_ -ne '' })
    $lines = @('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;')
    if ($SnapshotId) { $lines += "SET TRANSACTION SNAPSHOT '$SnapshotId';" }
    $lines += @("SET timezone = 'UTC';", "SET datestyle = 'ISO, MDY';", "SET intervalstyle = 'postgres';", 'SET extra_float_digits = 1;')
    foreach ($name in $names) {
        if ($SkipTables -contains $name) { continue }
        if ($name -notmatch '^[a-z_][a-z0-9_]*$') { throw "Ten bang khong hop le: $name" }
        $lines += "SELECT 'T|$name|' || count(*) || '|' || coalesce(md5(string_agg(h, '' ORDER BY h)), '') FROM (SELECT md5(t::text) AS h FROM public.$name t) s;"
    }
    $lines += "SELECT 'M|' || coalesce(max(name), '') FROM public.schema_migrations;"
    $lines += "SELECT 'E|' || extname || '|' || extversion FROM pg_extension WHERE extname IN ('vector', 'pgcrypto') ORDER BY extname;"
    $lines += 'COMMIT;'
    $file = Join-Path $Conn.WorkDir 'fingerprint.sql'
    Write-Utf8File $file (($lines -join "`n") + "`n")
    $output = Invoke-Psql $Conn -File $file -Tag 'fp-run' -TimeoutSeconds 1800
    $tables = [ordered]@{}
    $schema = ''
    $extensions = [ordered]@{}
    foreach ($line in ($output -split "`r?`n")) {
        if ($line.StartsWith('T|')) {
            $parts = $line.Split('|')
            $tables[$parts[1]] = [ordered]@{ rows = [int64]$parts[2]; md5 = $parts[3] }
        } elseif ($line.StartsWith('M|')) {
            $schema = $line.Substring(2)
        } elseif ($line.StartsWith('E|')) {
            $parts = $line.Split('|')
            $extensions[$parts[1]] = $parts[2]
        }
    }
    foreach ($skipped in $SkipTables) { if ($names -contains $skipped) { $tables[$skipped] = [ordered]@{ rows = 0; md5 = 'excluded' } } }
    return [ordered]@{ schema_version = $schema; extensions = $extensions; tables = $tables }
}

function ConvertTo-TableMap($Tables) {
    $map = @{}
    if ($Tables -is [System.Collections.IDictionary]) {
        foreach ($key in $Tables.Keys) { $map[$key] = $Tables[$key] }
    } else {
        foreach ($property in $Tables.PSObject.Properties) { $map[$property.Name] = $property.Value }
    }
    return $map
}

function Compare-DbFingerprint($Expected, $Actual, [string[]]$IgnoreTables = @()) {
    $problems = New-Object System.Collections.Generic.List[string]
    if ("$($Expected.schema_version)" -ne "$($Actual.schema_version)") {
        $problems.Add("phien ban schema khac nhau: $($Expected.schema_version) / $($Actual.schema_version)")
    }
    $expectedTables = ConvertTo-TableMap $Expected.tables
    $actualTables = ConvertTo-TableMap $Actual.tables
    foreach ($name in $expectedTables.Keys) {
        if ($IgnoreTables -contains $name) { continue }
        if (-not $actualTables.ContainsKey($name)) { $problems.Add("thieu bang $name"); continue }
        if ([int64]$expectedTables[$name].rows -ne [int64]$actualTables[$name].rows) {
            $problems.Add("bang ${name}: $($expectedTables[$name].rows) dong (goc) / $($actualTables[$name].rows) dong (sau khoi phuc)")
        } elseif ("$($expectedTables[$name].md5)" -ne "$($actualTables[$name].md5)") {
            $problems.Add("bang ${name}: noi dung khac nhau (md5)")
        }
    }
    foreach ($name in $actualTables.Keys) {
        if (-not $expectedTables.ContainsKey($name) -and ($IgnoreTables -notcontains $name)) { $problems.Add("bang thua $name") }
    }
    return , $problems.ToArray()
}

# Files the database points to (original PDF of every version, and the Word/TXT source when there is one).
function Test-DocumentReferences($Conn, [string]$StoreRoot) {
    $missing = New-Object System.Collections.Generic.List[string]
    $rows = (Invoke-Psql $Conn @("SELECT original_file_path || '|' || coalesce(source_file_sha256, '') || '|' || source_format FROM document_versions") -Tag 'psql-docs') -split "`r?`n" | Where-Object { $_ -ne '' }
    foreach ($row in $rows) {
        $parts = $row.Split('|')
        if (-not (Test-Path -LiteralPath (Join-Path $StoreRoot ($parts[0] -replace '/', '\')))) { $missing.Add($parts[0]) }
        if ($parts[1] -and $parts[2] -ne 'pdf') {
            $src = 'sources\' + $parts[1] + '.' + $parts[2]
            if (-not (Test-Path -LiteralPath (Join-Path $StoreRoot $src))) { $missing.Add($src) }
        }
    }
    return , $missing.ToArray()
}

# A content-addressed store: every file is named after the SHA-256 of its bytes.
function Test-DocumentStore([string]$StoreRoot) {
    $bad = New-Object System.Collections.Generic.List[string]
    $unexpected = New-Object System.Collections.Generic.List[string]
    $count = 0
    foreach ($folder in 'originals', 'sources') {
        $dir = Join-Path $StoreRoot $folder
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        foreach ($file in Get-ChildItem -LiteralPath $dir -File) {
            $stem = [IO.Path]::GetFileNameWithoutExtension($file.Name)
            if ($stem -notmatch '^[0-9a-f]{64}$') { $unexpected.Add("$folder\$($file.Name)"); continue }
            $count++
            if ((Get-FileSha256 $file.FullName) -ne $stem) { $bad.Add("$folder\$($file.Name)") }
        }
    }
    return [pscustomobject]@{ Files = $count; Mismatched = $bad.ToArray(); Unexpected = $unexpected.ToArray() }
}
