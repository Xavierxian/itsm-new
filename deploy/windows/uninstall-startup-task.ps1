param(
    [string]$TaskName = "ITSM-Production"
)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
Write-Host "Scheduled task removed: $TaskName"
