# Kiểm tra sức khỏe nguồn hàng tuần. Task Scheduler gọi sáng thứ hai. Báo Windows nếu có nguồn hỏng.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$log = Join-Path $Root "data\logs\selfcheck.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Add-Content -Encoding UTF8 $log
$out = & $Py (Join-Path $Root "pipeline\selfcheck.py") 2>&1
$out | Add-Content -Encoding UTF8 $log
$code = $LASTEXITCODE
$summary = ($out | Select-String "nguồn ổn" | Select-Object -Last 1).ToString()
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $xml.GetElementsByTagName("text")
    $t.Item(0).AppendChild($xml.CreateTextNode($(if ($code -eq 0) { "LEVEL UP: nguồn tin ổn" } else { "LEVEL UP: có nguồn hỏng" }))) | Out-Null
    $t.Item(1).AppendChild($xml.CreateTextNode($summary)) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("LEVEL UP").Show([Windows.UI.Notifications.ToastNotification]::new($xml))
} catch {}
exit $code
