# AGENT - PTT Alertor Windows 批次啟動分析

## 1. 專案概要
PTT Alertor 以 Go 建置持續抓取 PTT 各看板文章並依使用者訂閱條件推送至 LINE、Discord、Telegram、Messenger、Email 等管道。`main.go` 配置 HTTP API、靜態頁面與 WebSocket，並在啟動時載入多個排程與監控工作，確保重啟後可以續傳遺漏通知。

## 2. 目錄與模組重點
- `main.go`：設定環境變數、HTTP 路由、Basic Auth、gops agent 以及啟動/關閉流程。
- `windows_run.bat`、`windows.py`：Windows 啟動腳本與系統匣包裝；前者負責設定環境與執行 `go run main.go`，後者可在 Windows 系統匣啟動批次檔。
- `controllers/`+`public/`：靜態網頁與 API 控制器 (Line/Docs/Boards/Users/WebSocket 等)。
- `jobs/`：看板巡檢、通知派送、排程 (Top、PushSum、CacheCleaner、Recovery、Generator、Fetcher、Migrate 等)。
- `channels/`：不同推播平台的封裝 (line、telegram、discord、messenger、mail)。
- `models/`+`storage/`：資料存取層，支援 Redis 或檔案儲存；`storage/heartbeat.txt` 亦用於復原。
- `ptt/`：HTTP/RSS/WEB 爬蟲模組，處理 over18 cookie、頁面解析與推文數計算。
- 其他：`shorturl/` 生成 /redirect/{checksum}，`myutil/` 共用工具，`testing/` 測試資料。

## 3. Windows 執行前置需求與流程 (windows_run.bat)
### 前置需求
1. 安裝 Go 1.21+ (go.mod 指定 go 1.21 並使用 toolchain go1.22.0)，確保 `go` 與 `git` 可在 PowerShell 中使用。
2. 安裝 Redis for Windows，並讓 `redis-server.exe`、`redis-cli.exe` 位於 PATH (批次檔會直接呼叫)。
3. 確認可連上 https://www.ptt.cc 以及 LINE/Discord/Telegram 等外部服務，並準備各平台權杖。
4. 首次使用可將 `storage/` 與 `redis-data/` 資料夾加入備份，以保留使用者與心跳資料。

### 執行流程概述
1. `chcp 65001` 將主控台設定為 UTF-8，避免中文字亂碼。
2. 預設環境變數：
   - `USER_STORE=file` 讓使用者資料寫入 `storage/users`，避免因 Redis 重啟而遺失。
   - Redis 連線 (`REDIS_ENDPOINT`, `REDIS_PORT`)；可按需改成遠端 URI。
   - 各 Bot 權杖與基本認證 (`DISCORD_TOKEN`, `LINE_CLIENT_SECRET/SECRET/ACCESSTOKEN`, `TELEGRAM_TOKEN`, `AUTH_USER/AUTH_PW`)。
   - Web/通知設定 (`APP_HOST`、`BOARD_HIGH`)，預設 `http://localhost:9090` 及 `gossiping,beauty,c_chat`。
3. `go mod tidy` 下載並同步模組，需可存取 Go Proxy/Git。
4. 檢查 Redis：
   - 建立 `%~dp0\redis-data` 供 `--appendonly yes` 持久化。
   - `redis-cli ping` 失敗時以 `redis-server --dir redis-data --appendonly yes --save 60 1` 啟動後台服務。
5. 顯示服務啟動提示後執行 `go run main.go`，HTTP 伺服器監聽 `http://localhost:9090`、gops agent 在 `:6060`。批次檔會在程式結束時 `pause`，方便查看錯誤。
6. 若要以 GUI/系統匣啟動，可執行 `windows.py` (需 Python、pystray、Pillow)，它只會在背景呼叫相同批次檔。

## 4. HTTP / 靜態頁面
- `main.go` 註冊 Boards/Keyword/Author/PushSum/Articles API 以及 `/ws` WebSocket，未匹配路由則由 `public/` 靜態檔案處理。
- `/broadcast` 與 `/users/*` 走 Basic Auth (`AUTH_USER`/`AUTH_PW`)，適合後台批次或自建管理工具使用。
- 模板由 `controllers/index.go` 結合 `public/tpls` 載入，並透過 `APP_WS_HOST`、`S3_DOMAIN`、計數器資料顯示前端儀表板。

## 5. 背景排程與啟動序
- `startJobs()` 啟動：`StartHeartbeat()`、`Checker`、`PushSumChecker`、`CommentChecker`、`PttMonitor` 以及 cron (`@hourly` 的 `Top`、`@every 48h` 的 `PushSumKeyReplacer`)。
- `init()` 於伺服器啟動前立即執行 `RecoverFromLastHeartbeat()`、`PushSumKeyReplacer`、`MigrateBoard/DB`、`Top`、`CacheCleaner`、`Generator`、`Fetcher`、`CategoryCleaner` 以建立初始快照與索引。
- `jobs/recovery.go` 會每分鐘寫入 Redis 與 `storage/heartbeat.txt`，重啟時讀取最後心跳時間並回補離線期間的文章通知。

## 6. 監控與通知管線
- `jobs/checker.go` 依 `BOARD_HIGH` 及資料庫全部看板輪詢 `ptt/web` 爬蟲，偵測 `NewArticles` 後交給關鍵字/作者檢查並寫回 Redis snapshot。
- `ptt/web/crawler.go` 直接解析 https://www.ptt.cc HTML，包含 over18 Cookie、推文數、作者、日期等欄位；為避免 404 會自動跟進 `passR18`。
- 當觸發通知時，`jobs/check.go` 的 300 個 worker 會從 `ckCh` 讀取事件，進行 5 分鐘重複檢查後分別呼叫 line/telegram/discord/mail/messenger 推播，同時累計 `counter`。
- `jobs/commentchecker.go`、`pushsumchecker.go`、`broadcaster.go` 等輔助模組會把留言變動、推文異常或廣播指令寫入同一個 `ckCh`，確保訊息走相同管線。

## 7. 資料儲存與復原策略
- Redis：`connections/redis.go` 透過 `REDIS_ENDPOINT:REDIS_PORT` 建立連線並作為快取、Pub/Sub、心跳記錄與版面快照儲存來源。
- 使用者：`models/models.go` 依 `USER_STORE` 選擇 `user.File` (寫入 `storage/users/*.json`、`storage/channel_users`) 或 `user.Redis`。
- 心跳備援：`jobs/recovery.go` 同步寫入 `storage/heartbeat.txt`，若 Redis 資料遺失仍能回補。
- 自帶的 `storage/users_backup` 可視為手動備份，可定期複製。

## 8. 對外訊息管道與權杖
- LINE：`channels/line/line.go` 與 `channels/line/notify.go` 需要 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESSTOKEN` 及 `APP_HOST` (產生 `/line/notify/callback` URL)。
- Telegram：`channels/telegram/telegram.go` 使用 `TELEGRAM_TOKEN` 和 `APP_HOST` 組成 webhook 路徑 `/telegram/{TOKEN}`。
- Discord：`channels/discord` 需 `DISCORD_TOKEN`，支援個人或 Guild 頻道，並在 `HandleLeave` 時停用失效使用者。
- Messenger/Email：`channels/messenger`、`channels/mail` 依照各自 SDK/SMTP 設定發送。
- `shorturl` 與 `APP_HOST` 結合提供 `/redirect/:checksum`，方便在通知中附上縮網址。

## 9. Windows 操作建議
1. 首次執行前編輯 `windows_run.bat`，填入真實的權杖與帳密；必要時可把敏感資訊抽出成獨立 `.env`，再在批次檔 `call`。
2. 若 `redis-server` 不在 PATH，可在批次檔開頭 `set PATH=%PATH%;C:\path\to\redis` 或直接指定絕對路徑。
3. 服務需要長期啟動時，建議使用 PowerShell `Start-Process` 或排程工作排定登入自動執行；系統匣方案可透過 `windows.py`。
4. `storage/` 與 `redis-data/` 位於 OneDrive，同步時請留意避免被鎖定；建議定期備份或改成本機非同步資料夾。
5. 若要對外提供 webhook/前端，將 `APP_HOST` 改為實際可被 LINE/Telegram 等服務回呼的 HTTPS 網域，並同步更新反向代理或 Ngrok 設定。
