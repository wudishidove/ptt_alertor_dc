## Discord 介面整合說明（Ptt Alertor）

本文說明本專案的 Discord Bot 介面如何與 PTT 監控與通知系統整合，包含架構、初始化、訊息/指令處理、使用者綁定與通知發送、廣播與注意事項。

### 架構總覽

- 核心監控
  - `jobs/checker.go`：定期檢查各 PTT 看板是否有新文章，依使用者訂閱（關鍵字/作者/推文數/推文追蹤）產生待發送訊息。
  - `jobs/pushsumchecker.go`、`jobs/commentchecker.go`：處理推噓文與推文追蹤等特殊情境。
  - 產生的通知物件會送到內部通道 `ckCh`，由 worker 呼叫各平台發送。

- 平台路由與發送
  - `jobs/check.go`：根據使用者 `Profile` 判斷平台；若有 `Profile.DiscordChannelID` 則走 Discord，呼叫 `channels/discord.Notify` 發送。
  - 同檔案含「通知去重」機制，5 分鐘內相同內容不重複發送。

- Discord 介面
  - `channels/discord/discord_notify.go`：初始化 `discordgo` 連線、讀取 Token、註冊事件（Ready/Message/Join/Leave）、提供 `Notify` 發送函式與 `SaveUserChannel` 綁定頻道。
  - `channels/discord/discord.go`：事件處理。支援 `notify` 綁定通知頻道、一般中文指令（委派至 `command.HandleCommand`）、訊息切段（避免超過 2000 字元）。

- 指令解析
  - `command/command.go`：處理「新增/刪除（關鍵字/作者/推文數/推文追蹤）」、`指令`、`清單`、`排行`、`推文清單`、`清理推文` 等，並回傳字串由 Discord 送出。

- 廣播
  - `controllers/broadcast.go`、`jobs/broadcaster.go`：以 `POST /broadcast` 發送平台清單與內容，系統會對所有使用者逐一發送；Discord 以使用者的 `DiscordChannelID` 投遞。

### 初始化與連線（Discord）

- 設定檔：`channels/discord/config.json`
  - 格式：`{"DISCORD_TOKEN": "<你的 Discord Bot Token>"}`
  - 系統啟動時由 `channels/discord/discord_notify.go` 的 `init()` 讀取 Token，建立 `discordgo.Session`，註冊事件，並 `Open()` 連線。

- 啟動時機
  - `jobs/check.go` 匯入 `channels/discord` 以使用 `Notify`，使其 `init()` 隨程式啟動一併初始化 Discord 連線。

### 訊息與指令處理流程

1. 事件來源：`discordgo` 觸發 `HandleMessage`（`channels/discord/discord.go`）。
2. 前置過濾：忽略自己與其他 Bot 的訊息。
3. 各種場景分支：
   - 綁定通知頻道：使用者輸入 `notify` → 呼叫 `SaveUserChannel(userID, channelID)`，將此頻道記錄到使用者 `Profile.DiscordChannelID`。
   - 尚未綁定：在私訊或公頻有「提及 Bot」時，回傳導引訊息，提示輸入 `notify` 完成綁定。
   - 一般指令：其他文字由 `command.HandleCommand(text, accountID, isDM)` 處理，將結果分段（上限 2000 字元）後回覆。
   - 刪除確認：符合 `^(刪除|刪除作者)\s.*\*+` 的批次刪除格式時，回覆確認訊息。

4. 其他事件：
   - `HandleReady`：登入成功後設定 Bot 狀態為「監控 PTT 中...」。
   - `HandleJoin`：被加入伺服器時記錄。
   - `HandleLeave`：Bot 離開某伺服器時，掃描所有已綁定該伺服器頻道的使用者並停用（`Enable=false`）。

### 使用者綁定模型

- `models/user/user.go` 的 `Profile` 結構包含 `DiscordChannelID`。
- `SaveUserChannel(userID, channelID)`：
  - 若使用者不存在：建立帳號（`Account=userID`、`Type=discord`、`DiscordChannelID=channelID`、`Enable=true`）。
  - 若存在：更新 `DiscordChannelID`。

### 通知產生與發送（Discord）

1. 監控工作發現事件：
   - `Checker` 將符合條件的文章與上下文（關鍵字/作者/推文數/推文追蹤）封裝為字串（`Checker.String()`）。
   - 透過 channel `c.ch <- cker` 推送至 `ckCh`。

2. 平台路由與去重：
   - `jobs/check.go/sendMessage` 接收後，先做 5 分鐘內內容去重（以 `Account + DiscordChannelID + content` 的 MD5 當 key）。
   - 依 `Profile` 決定平台；若有 `DiscordChannelID` 則呼叫 `sendDiscord`。

3. 發送：
   - `sendDiscord` → `discord.Notify(channelID, content)` → `discordgo.Session.ChannelMessageSend`。

4. 內容格式：
   - 關鍵字/作者等情境會產出：
     - 首行：`<word>@<board>`
     - 第二行起：`看板：<board>; <類型><word>`
     - 後續：每篇文章標題與連結（多篇以空行分隔）。

### 廣播（系統管理介面）

- `POST /broadcast`（Basic Auth）
  - Body：`{"platforms": ["discord", ...], "content": "..."}`
  - 由 `jobs/broadcaster.go` 逐一帶入每位使用者的 `Profile`，透過相同的 `ckCh` 與 `sendMessage` 流程發送。

### 常用使用步驟（使用者角度）

1. 管理員在 Discord 開發者後台建立 Bot，將 Bot 加入伺服器，並賦予「傳送訊息」權限。
2. 部署服務，設定 `channels/discord/config.json` 的 `DISCORD_TOKEN`。
3. 在私訊或指定伺服器頻道中對 Bot 輸入：`notify`（完成綁定）。
4. 輸入：`指令` 以檢視可用指令。
5. 例如訂閱：`新增 pc_shopping 情報,特價` 或 `新增作者 gossiping ffaarr`。
6. 之後有符合條件的新文章會自動推播到綁定頻道。

### 重要限制與注意事項

- 訊息長度：Discord 單則訊息上限 2000 字元；系統會自動切段。
- 去重機制：5 分鐘內相同內容不重複發送，避免洗頻。
- 離開伺服器：Bot 被移出伺服器時，綁定該伺服器頻道的使用者會被自動停用。
- Token 管理：`channels/discord/config.json` 不建議直接提交實際 Token，建議改為讀取環境變數或在部署時以 Secrets 管理。

### 資料持久化與「使用者記憶被清空」問題

- 問題描述：若使用 Redis 儲存使用者（預設），本機 Windows、睡眠/關機後、或 Redis 服務未持久化時，可能導致 `user:*` key 在幾週後被清空，出現「已建好的追蹤清單被清空」狀況。
- 解法一（推薦，本機/開發環境）：切換使用者儲存至檔案系統。
  - 設定環境變數 `USER_STORE=file` 後重啟服務。
  - 程式會改用 `storage/users/*.json` 儲存使用者資料，避免 Redis 清空造成遺失。
  - 相關程式：`models/models.go` 會依 `USER_STORE` 在 `redis` 與 `file` 之間切換。
- 解法二（正式環境）：保證 Redis 永續化
  - 啟用 RDB/AOF，確保 Redis 進程重啟後資料可回復。
  - 避免在系統維護腳本中執行 `FLUSH*`/大面積 `DEL`。
  - 注意 `jobs/cachecleaner.go` 只會清理 boards/keyword/author/pushsum/article 的快取與訂閱索引，不會清除 `user:*` key。

### 開發者導覽（關鍵檔案）

- Discord：
  - `channels/discord/discord_notify.go`：連線、事件註冊、`SaveUserChannel`、`Notify`。
  - `channels/discord/discord.go`：`HandleReady`、`HandleMessage`、`HandleJoin`、`HandleLeave`、切段與提示訊息。
- 監控與通知：
  - `jobs/checker.go`：掃描看板與組裝通知內容。
  - `jobs/check.go`：平台路由、去重、實際呼叫各平台發送。
  - `jobs/pushsumchecker.go`、`jobs/commentchecker.go`：推噓文/推文追蹤情境。
- 指令：
  - `command/command.go`：中文指令解析與回覆內容產生。
- 廣播：
  - `controllers/broadcast.go`、`jobs/broadcaster.go`。

### 本地快速啟動（摘要）

1. 取得 Discord Bot Token 並填入 `channels/discord/config.json`。
2. 其他平台（Line/Messenger/Telegram）可留空；不影響 Discord 運作。
3. 啟動服務（例如 `go run main.go`）。
4. 於 Discord 私訊或伺服器頻道輸入 `notify` 完成綁定後即可測試指令與接收通知。

---

若需進一步調整（例如改由環境變數載入 Token、或新增 Slash Commands），可在 `channels/discord` 中擴充初始化與事件處理邏輯，並維持 `jobs/check.go` 的 `Notify` 發送介面不變以確保相容。


