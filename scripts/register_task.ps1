# Đăng ký Task Scheduler: chạy mỗi sáng 6:00, và chạy bù khi mở máy nếu lỡ giờ.
# Chạy MỘT LẦN:  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TaskName = "BaoTotLanh-HangNgay"
$Script = Join-Path $Root "scripts\run_daily.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Báo Tốt Lành: thu thập, lọc, viết lại và đẩy số báo mỗi sáng" | Out-Null
Write-Host "Đã đăng ký '$TaskName': 6:00 mỗi ngày, chạy bù nếu máy tắt lúc đó."
Write-Host "Chạy thử ngay:  Start-ScheduledTask -TaskName $TaskName"
