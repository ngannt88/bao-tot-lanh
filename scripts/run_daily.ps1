# Mỗi sáng: lấy tin, lọc, tách nguyên văn ứng viên, rồi mở trang duyệt cho cha mẹ.
# Task Scheduler gọi lúc 6:00 và khi đăng nhập Windows. Chạy tay:
#   powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$log = Join-Path $Root "data\logs\scheduler.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') bắt đầu ===" | Add-Content -Encoding UTF8 $log

function Notify($title, $msg) {
    # Thông báo Windows, không cần cài thêm gì
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $t = $xml.GetElementsByTagName("text")
        $t.Item(0).AppendChild($xml.CreateTextNode($title)) | Out-Null
        $t.Item(1).AppendChild($xml.CreateTextNode($msg)) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("LEVEL UP").Show($toast)
    } catch { "notify lỗi: $_" | Add-Content -Encoding UTF8 $log }
}

# Không chạy trước 5 giờ sáng: trigger "khi đăng nhập" có thể kích lúc 3 giờ sáng,
# lúc đó máy thường sắp ngủ lại và tiến trình bị cắt giữa chừng.
$hourNow = [int](Get-Date -Format 'HH')
if ($hourNow -lt 5) {
    "Mới $hourNow giờ, chưa tới 5:00 — bỏ qua lần chạy này." | Add-Content -Encoding UTF8 $log
    exit 0
}

$today = Get-Date -Format 'yyyy-MM-dd'
$candFile = Join-Path $Root "data\candidates\$today.json"
$issueFile = Join-Path $Root "docs\data\issues\$today.json"

if (Test-Path $issueFile) {
    "Số báo hôm nay đã xuất bản, không làm gì." | Add-Content -Encoding UTF8 $log
    exit 0
}

if (-not (Test-Path $candFile)) {
    # Chờ mạng tối đa 5 phút (máy vừa mở)
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet) { $ok = $true; break }
        Start-Sleep -Seconds 10
    }
    if (-not $ok) { "Không có mạng, bỏ qua." | Add-Content -Encoding UTF8 $log; exit 1 }
    & $Py (Join-Path $Root "pipeline\run_daily.py") 2>&1 | Add-Content -Encoding UTF8 $log
    $code = $LASTEXITCODE
    "pipeline exit=$code" | Add-Content -Encoding UTF8 $log
    if ($code -ne 0 -or -not (Test-Path $candFile)) {
        Notify "LEVEL UP: lỗi lấy tin sáng nay" "Xem data\logs\scheduler.log"
        exit 1
    }
    Notify "LEVEL UP: có ứng viên mới" "Mở trang duyệt để chọn bài cho con"
} else {
    "Ứng viên hôm nay đã có, chỉ mở trang duyệt." | Add-Content -Encoding UTF8 $log
}

# Bật máy chủ duyệt nếu chưa chạy, rồi mở trình duyệt tới trang duyệt
$listening = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath $Py -ArgumentList "`"$(Join-Path $Root 'pipeline\review_server.py')`"" -WindowStyle Hidden -WorkingDirectory $Root
    Start-Sleep -Seconds 2
    "đã bật máy chủ duyệt" | Add-Content -Encoding UTF8 $log
}
Start-Process "http://localhost:8765/duyet.html"
"=== xong ===" | Add-Content -Encoding UTF8 $log
