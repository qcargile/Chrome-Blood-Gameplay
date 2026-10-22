param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$RequestSha256,
    [Parameter(Mandatory = $true)][string]$InstanceRoot
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstanceRoot)
$request = $null

try {
    $requestPath = Join-Path $root 'cb-collection-request.json'
    $inputStream = [IO.File]::Open($requestPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $inputHasher = [Security.Cryptography.SHA256]::Create()
    try {
        if ($inputStream.Length -le 0 -or $inputStream.Length -gt 16MB) { throw 'collection.vfs-request-bound' }
        $requestBytes = New-Object byte[] ([int]$inputStream.Length)
        $offset = 0
        while ($offset -lt $requestBytes.Length) {
            $read = $inputStream.Read($requestBytes, $offset, $requestBytes.Length - $offset)
            if ($read -eq 0) { throw 'collection.vfs-request-truncated' }
            $offset += $read
        }
        $requestHash = [BitConverter]::ToString($inputHasher.ComputeHash($requestBytes)).Replace('-', '').ToLowerInvariant()
        if ($requestHash -ne $RequestSha256) { throw 'collection.vfs-request-hash' }
        $request = [Text.Encoding]::UTF8.GetString($requestBytes).TrimStart([char]0xFEFF) | ConvertFrom-Json
    } finally {
        $inputHasher.Dispose()
        $inputStream.Dispose()
    }
    if ($request.schemaVersion -ne 1 -or [IO.Path]::GetFullPath($request.instanceRoot) -ne $root) { throw 'collection.vfs-request-binding' }

    $files = @()
    foreach ($expected in @($request.effectiveFiles)) {
        $path = Join-Path $request.gameRoot $expected.path.Replace('/', [IO.Path]::DirectorySeparatorChar)
        if (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'collection.vfs-effective-reparse' }
        $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try {
            $length = $stream.Length
            $hash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
        } finally {
            $hasher.Dispose()
            $stream.Dispose()
        }
        if ($hash -ne $expected.sha256 -or $length -ne $expected.bytes) { throw 'collection.vfs-effective-file' }
        $files += [ordered]@{path=$expected.path;bytes=$length;sha256=$hash;winner=$expected.winner}
    }

    $absent = @()
    foreach ($relative in @($request.absentFiles)) {
        $path = Join-Path $request.gameRoot $relative.Replace('/', [IO.Path]::DirectorySeparatorChar)
        if (Test-Path -LiteralPath $path) { throw 'collection.vfs-optional-file-present' }
        $absent += $relative
    }

    $result = [ordered]@{
        schemaVersion = 1
        status = 'verified'
        operationId = $request.operationId
        requestSha256 = $RequestSha256
        files = $files
        absentFiles = $absent
    }
    [IO.File]::WriteAllText((Join-Path $root 'cb-collection-vfs.json'), ($result | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
} catch {
    $message = $_.Exception.Message
    if ($message.Length -gt 512) { $message = $message.Substring(0, 512) }
    $failure = [ordered]@{
        schemaVersion = 1
        status = 'failed'
        operationId = if ($null -ne $request) { $request.operationId } else { '' }
        requestSha256 = $RequestSha256
        files = @()
        absentFiles = @()
        failureType = $_.Exception.GetType().Name
        failure = $message
        line = $_.InvocationInfo.ScriptLineNumber
    }
    [IO.File]::WriteAllText((Join-Path $root 'cb-collection-vfs.json'), ($failure | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
    exit 1
}
