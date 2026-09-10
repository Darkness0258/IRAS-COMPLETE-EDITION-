$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')

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
