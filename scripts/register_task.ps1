# Đăng ký Task Scheduler. Chạy MỘT LẦN:
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
# Ba tác vụ:
#   1. BaoTotLanh-HangNgay   6:00 + khi đăng nhập Windows: lấy tin, tách ứng viên, mở trang duyệt
#   2. BaoTotLanh-TuXuatBan  giờ hẹn (config review.auto_publish.hour): chưa duyệt thì tự xuất bản
#   3. BaoTotLanh-KiemTra    thứ hai 7:00: kiểm tra sức khỏe nguồn
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Py = Join-Path $Root ".venv\Scripts\python.exe"

# Đọc giờ tự xuất bản từ config (mặc định 7:30)
$autoHour = & $Py -c "import yaml;c=yaml.safe_load(open(r'$Root\config\newspaper.yaml',encoding='utf-8'));a=c.get('review',{}).get('auto_publish',{});print(a.get('hour','07:30') if a.get('enabled') else '')"
$autoHour = "$autoHour".Trim()

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

function Register($name, $script, $triggers, $desc) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Description $desc | Out-Null
    Write-Host "Đã đăng ký $name"
}

# 1. Hàng ngày: 6:00 + khi đăng nhập (trễ 2 phút). Kịch bản tự bỏ qua nếu hôm nay đã có.
$t1 = New-ScheduledTaskTrigger -Daily -At 6:00AM
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$t2.Delay = "PT2M"
Register "BaoTotLanh-HangNgay" (Join-Path $Root "scripts\run_daily.ps1") @($t1, $t2) "LEVEL UP: lấy tin, tách ứng viên, mở trang duyệt"

# 2. Tự xuất bản nếu chưa duyệt (chỉ khi bật trong config)
if ($autoHour) {
    $t3 = New-ScheduledTaskTrigger -Daily -At $autoHour
    $t4 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $t4.Delay = "PT12M"   # sau tác vụ 1 đủ lâu để có ứng viên
    Register "BaoTotLanh-TuXuatBan" (Join-Path $Root "scripts\auto_publish.ps1") @($t3, $t4) "LEVEL UP: tự xuất bản bài điểm cao nếu cha mẹ chưa duyệt"
} else {
    Unregister-ScheduledTask -TaskName "BaoTotLanh-TuXuatBan" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tự xuất bản đang TẮT (review.auto_publish.enabled: false)"
}

# 3. Kiểm tra nguồn: thứ hai 7:00
$t5 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7:00AM
Register "BaoTotLanh-KiemTra" (Join-Path $Root "scripts\selfcheck.ps1") @($t5) "LEVEL UP: kiểm tra feed và bộ tách hàng tuần"

Write-Host "`nChạy thử ngay:  Start-ScheduledTask -TaskName BaoTotLanh-HangNgay"
