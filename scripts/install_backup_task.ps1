# Registers a daily Windows Scheduled Task that backs up the reputation Postgres DB.
# It runs scripts/backup_db.sh via git-bash. Per-user task (no admin elevation required).
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1 -Time "03:15"
#
# Remove it with:  Unregister-ScheduledTask -TaskName KoobReputationDbBackup -Confirm:$false
param(
  [string]$Time = "02:30",
  [string]$TaskName = "KoobReputationDbBackup"
)
$ErrorActionPreference = "Stop"

$repo  = Split-Path -Parent $PSScriptRoot
$bash  = "C:\Program Files\Git\bin\bash.exe"
$script = Join-Path $repo "scripts\backup_db.sh"

if (-not (Test-Path $bash))   { throw "git-bash not found at $bash (install Git for Windows or edit this path)" }
if (-not (Test-Path $script)) { throw "backup script not found at $script" }

# git-bash accepts a Windows path argument and converts it internally.
$action   = New-ScheduledTaskAction -Execute $bash -Argument "`"$script`""
$trigger  = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "Daily gzip pg_dump backup of the reputation Postgres DB (scripts/backup_db.sh)" -Force | Out-Null

Write-Host "Registered Scheduled Task '$TaskName' to run daily at $Time."
Write-Host "Run it now to test:  Start-ScheduledTask -TaskName $TaskName"
