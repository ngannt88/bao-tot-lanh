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
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') bắt đầu ===" | Add-Content $log

$today = Get-Date -Format 'yyyy-MM-dd'
$candFile = Join-Path $Root "data\candidates\$today.json"
$issueFile = Join-Path $Root "docs\data\issues\$today.json"

if (Test-Path $issueFile) {
    "Số báo hôm nay đã xuất bản, không làm gì." | Add-Content $log
    exit 0
}

if (-not (Test-Path $candFile)) {
    # Chờ mạng tối đa 5 phút (máy vừa mở)
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet) { $ok = $true; break }
        Start-Sleep -Seconds 10
    }
    if (-not $ok) { "Không có mạng, bỏ qua." | Add-Content $log; exit 1 }
    & $Py (Join-Path $Root "pipeline\run_daily.py") 2>&1 | Add-Content $log
    "pipeline exit=$LASTEXITCODE" | Add-Content $log
} else {
    "Ứng viên hôm nay đã có, chỉ mở trang duyệt." | Add-Content $log
}

# Bật máy chủ duyệt nếu chưa chạy, rồi mở trình duyệt tới trang duyệt
$listening = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath $Py -ArgumentList "`"$(Join-Path $Root 'pipeline\review_server.py')`"" -WindowStyle Hidden -WorkingDirectory $Root
    Start-Sleep -Seconds 2
    "đã bật máy chủ duyệt" | Add-Content $log
}
Start-Process "http://localhost:8765/duyet.html"
"=== xong ===" | Add-Content $log
