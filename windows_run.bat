@echo off
REM 設定編碼為 UTF-8
chcp 65001

REM ====== 環境變數設定 ======
REM Redis 設定
set REDIS_HOST=localhost
set REDIS_PORT=6379

REM Discord Bot 設定
set DISCORD_TOKEN=""

REM line Bot 設定
set LINE_CLIENT_SECRET=0
set LINE_CHANNEL_SECRET=YOUR_LINE_CHANNEL_SECRET
set LINE_CHANNEL_ACCESSTOKEN=YOUR_LINE_CHANNEL_ACCESSTOKEN

REM Telegram Bot 設定
set TELEGRAM_TOKEN=0

REM 基本認證設定
set AUTH_USER=admin
set AUTH_PW=password

REM 應用程式設定
set APP_HOST=http://localhost:9090
set BOARD_HIGH=gossiping,beauty,c_chat

REM ====== 更新相依套件 ======
echo 正在更新相依套件...
go mod tidy

REM ====== 檢查 Redis 是否運行 ======
echo 檢查 Redis 服務狀態...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo Redis 未運行，正在啟動 Redis...
    start /B redis-server
    timeout /t 2 /nobreak >nul
)

REM ====== 啟動應用程式 ======
echo 正在啟動 PTT Alertor...
echo 應用程式將在 http://localhost:9090 運行
echo 按 Ctrl+C 可以停止程式

REM 運行應用程式
go run main.go

REM 如果程式意外結束，等待使用者按鍵
pause
