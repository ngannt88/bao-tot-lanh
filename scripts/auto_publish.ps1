# Đến giờ hẹn mà cha mẹ chưa duyệt → tự xuất bản các bài điểm AI cao nhất.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$log = Join-Path $Root "data\logs\scheduler.log"
$today = Get-Date -Format 'yyyy-MM-dd'
$candFile = Join-Path $Root "data\candidates\$today.json"
# chờ tối đa 10 phút cho tác vụ lấy tin xong (khi cả hai cùng chạy lúc đăng nhập)
for ($i = 0; $i -lt 60 -and -not (Test-Path $candFile); $i++) { Start-Sleep -Seconds 10 }
"=== $(Get-Date -Format 'HH:mm') tự xuất bản ===" | Add-Content $log
& $Py (Join-Path $Root "pipeline\publish.py") --auto 2>&1 | Add-Content $log
exit $LASTEXITCODE
