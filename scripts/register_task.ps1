# Đăng ký Task Scheduler: chạy mỗi sáng 6:00, và chạy bù khi mở máy nếu lỡ giờ.
# Chạy MỘT LẦN:  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TaskName = "BaoTotLanh-HangNgay"
$Script = Join-Path $Root "scripts\run_daily.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
# Hai mốc kích hoạt: 6:00 sáng, và mỗi lần đăng nhập Windows (trễ 2 phút cho mạng lên).
# Kịch bản tự bỏ qua nếu số báo hôm nay đã có, nên mở máy nhiều lần cũng chỉ chạy một lần.
$t1 = New-ScheduledTaskTrigger -Daily -At 6:00AM
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$t2.Delay = "PT2M"
$trigger = @($t1, $t2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Báo Tốt Lành: thu thập, lọc, viết lại và đẩy số báo mỗi sáng" | Out-Null
Write-Host "Đã đăng ký '$TaskName': 6:00 mỗi ngày, chạy bù nếu máy tắt lúc đó."
Write-Host "Chạy thử ngay:  Start-ScheduledTask -TaskName $TaskName"
