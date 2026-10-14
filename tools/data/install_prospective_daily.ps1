<#
StockScope S17 opt-in local weekday 07:00 schedule (Windows / Asia/Seoul).

No scheduled task is installed by a Git pull. Run THIS SCRIPT explicitly.
Run locally under your Windows signed-in user, not as an elevated service.
PC must be on and user signed in at execution time. Missed runs do not backfill.
#>
param(
    [switch]$Remove,
    [ValidateSet('KOSPI','KOSDAQ','ALL')]
    [string]$Scope = 'KOSPI'
)
$ErrorActionPreference = 'Stop'
$taskName = 'StockScope-Prospective-Daily'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host 'StockScope prospective schedule removed.'
    exit 0
}
$zone = (Get-TimeZone).Id
if ($zone -ne 'Korea Standard Time') {
    throw 'Task registration requires Windows timezone Korea Standard Time; actual KST daily guard also applies.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$script = Join-Path $root 'tools\data\prospective_daily.py'
if (-not (Test-Path $python)) {
    throw 'Local StockScope .venv not found. Run setup.ps1 before scheduling.'
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "$taskName exists; remove it explicitly before creating a replacement."
}
$arg = ('"{0}" --scope {1}' -f $script, $Scope)
$action = New-ScheduledTaskAction -Execute $python -Argument $arg -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '07:00'
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable:$false -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Read-only freshness preflight, local Scanner capture and outcome observation. No catch-up/backfill.' -ErrorAction Stop | Out-Null
Write-Host "Installed ${taskName}: 07:00 Korea Standard Time Monday-Friday (signed-in user only)."
Write-Host "Results: $root\data\prospective_daily"
Write-Host 'Stop: powershell -File tools\data\install_prospective_daily.ps1 -Remove'
