$ErrorActionPreference = "SilentlyContinue"
$TaskName = "IRAS Remote Windows Agent"
Stop-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
iras --remote-disarm
Write-Host "IRAS remote startup task removed and laptop remote policy disarmed." -ForegroundColor Green
