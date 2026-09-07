# Restore normal sleep/lid-close after crawl (reasonable defaults).
#   powershell -ExecutionPolicy Bypass -File scripts\disable_crawl_power.ps1

# Lid close -> Sleep (1)
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_BUTTONS LIDACTION 1
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_BUTTONS LIDACTION 1

# Sleep after 30 min (AC), 15 min (battery) — adjust to taste
powercfg /CHANGE standby-timeout-ac 30
powercfg /CHANGE standby-timeout-dc 15
powercfg /CHANGE hibernate-timeout-ac 0
powercfg /CHANGE hibernate-timeout-dc 0

powercfg /SETACTIVE SCHEME_CURRENT

Write-Host "Power settings restored to normal sleep behavior." -ForegroundColor Green
