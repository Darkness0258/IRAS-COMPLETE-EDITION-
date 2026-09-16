param(
    [ValidateRange(32, 128)]
    [int]$ByteLength = 48,
    [switch]$CopyToClipboard
)

$ErrorActionPreference = "Stop"

$bytes = New-Object byte[] $ByteLength
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    # GetBytes(byte[]) is supported by Windows PowerShell 5.1/.NET Framework as
    # well as modern PowerShell. RandomNumberGenerator.Fill is not available on
    # every Windows PowerShell installation IRAS supports.
    $rng.GetBytes($bytes)
} finally {
    if ($null -ne $rng) {
        $rng.Dispose()
    }
}

$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 32) {
    throw "Failed to generate a strong IRAS_API_TOKEN."
}

# Guard against a broken RNG/runtime producing an obviously degenerate value.
$uniqueChars = @($token.ToCharArray() | Select-Object -Unique).Count
if ($uniqueChars -lt 12) {
    throw "Generated token failed the randomness sanity check. Run the script again."
}

if ($CopyToClipboard) {
    if (Get-Command Set-Clipboard -ErrorAction SilentlyContinue) {
        Set-Clipboard -Value $token
    } else {
        Write-Warning "Set-Clipboard is unavailable; token was not copied."
    }
}

Write-Host ""
Write-Host "Generated IRAS_API_TOKEN:"
Write-Host ""
Write-Host $token
Write-Host ""
Write-Host "Length: $($token.Length) characters"
if ($CopyToClipboard) {
    Write-Host "Copied to clipboard when Set-Clipboard is available."
}
Write-Host ""
Write-Host "Put this same token in:"
Write-Host "  1. Render -> Environment -> IRAS_API_TOKEN"
Write-Host "  2. Your local IRAS .env / client settings when required"
Write-Host ""
Write-Host "Do NOT use your OpenRouter key as the client token."
