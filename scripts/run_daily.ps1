# Chạy số báo hôm nay rồi đẩy lên GitHub Pages. Được Task Scheduler gọi mỗi sáng.
# Chạy tay:  powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$log = Join-Path $Root "data\logs\scheduler.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') bắt đầu ===" | Add-Content $log

# Chờ mạng tối đa 5 phút (máy vừa mở)
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet) { $ok = $true; break }
    Start-Sleep -Seconds 10
}
if (-not $ok) { "Không có mạng, bỏ qua." | Add-Content $log; exit 1 }

& "$Root\.venv\Scripts\python.exe" "$Root\pipeline\run_daily.py" 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
"pipeline exit=$code" | Add-Content $log

# Đẩy lên GitHub nếu có thay đổi trong docs/data
if (Test-Path (Join-Path $Root ".git")) {
    git add docs/data 2>&1 | Add-Content $log
    $changed = git status --porcelain docs/data
    if ($changed) {
        git commit -m ("Số báo " + (Get-Date -Format 'yyyy-MM-dd')) 2>&1 | Add-Content $log
        git push 2>&1 | Add-Content $log
        "đã đẩy lên GitHub" | Add-Content $log
    } else {
        "không có số báo mới để đẩy" | Add-Content $log
    }
}
"=== xong ===" | Add-Content $log
exit $code
