$ErrorActionPreference = "Stop"

$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
}
finally {
    if ($null -ne $rng) { $rng.Dispose() }
}

# 48 random bytes -> 64 URL-safe Base64 characters (384 bits of entropy).
$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')

if ($token.Length -lt 32 -or $token -match '^A+$') {
    throw "Secure IRAS_API_TOKEN generation failed. No token was emitted."
}

Write-Host ""
Write-Host "Generated IRAS_API_TOKEN:"
Write-Host ""
Write-Host $token
Write-Host ""
Write-Host "Put this same token in:"
Write-Host "  1. Render -> Environment -> IRAS_API_TOKEN"
Write-Host "  2. IRAS Android/Windows/Web client settings"
Write-Host ""
Write-Host "Do NOT use your OpenRouter key as the client token."
