# PTT Alertor (Python · Discord-only)

PTT 文章通知 bot。重寫自原 Go 版本，僅保留 Discord 對口，跑在 macOS 背景。

## Features
- 關鍵字訂閱（支援 `kw1&kw2` AND、`regexp:` 正則、`!` 排除）
- 作者訂閱
- 推噓文數監控（`新增推文數 / 新增噓文數`）
- 推文追蹤（`新增推文 <url>`）
- 開機後自動回抓 7 天，補送錯過的通知
- 5 分鐘 MD5 通知去重
- Discord 訊息 2000 字自動切段
- 管理員後台（Basic Auth）：使用者列表 / 統計 / 廣播

## Requirements
- Python 3.11+（建議用系統內建的 3.13）
- macOS（部署使用 LaunchAgent；Linux 也能跑，部署方式自理）

## Quick start

> 所有指令都假設你在 `python/` 目錄底下執行：`cd path/to/ptt_alertor_dc/python`

```bash
# 1) 安裝相依
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2) 設定 token / 帳密
cp .env.example .env
# 編輯 .env，填入 DISCORD_TOKEN、AUTH_PW

# 3) 本機跑跑看
.venv/bin/python -m ptt_alertor
```

接著：
- **私訊 bot** → 直接輸入 `notify`，再用 `指令` 看可用指令
- **在伺服器頻道** → 必須 @ tag bot，例如 `@PttAlertor 指令`
  （沒開 MESSAGE_CONTENT 特權 intent，伺服器內非 @mention 訊息看不到內容，是刻意設計）

## Discord 指令

| 指令 | 說明 |
|---|---|
| `notify` | 綁定通知到目前頻道（首次必輸入） |
| `指令` | 顯示可用指令 |
| `清單` | 顯示自己的訂閱 |
| `新增 看板1,看板2 關鍵字1,關鍵字2` | 新增關鍵字（可複合 `&`、正則 `regexp:`、排除 `!`） |
| `刪除 看板 關鍵字\|*` | 刪除關鍵字 |
| `新增作者 看板 作者` / `刪除作者 看板 作者\|*` | 作者訂閱 |
| `新增推文數 看板 N` / `新增噓文數 看板 N` | 推/噓文數閾值（0~100；0 = 取消） |
| `新增推文 https://www.ptt.cc/bbs/.../M.xxx.A.xxx.html` | 追蹤單篇文章新留言 |
| `刪除推文 <url>` | 取消文章追蹤 |

## 管理員後台

啟動後預設 listen 在 `127.0.0.1:9090`。改 `.env` 的 `WEB_HOST` / `WEB_PORT` 可調整。

| 端點 | 認證 | 用途 |
|---|---|---|
| `GET /` | 公開 | 系統狀態 |
| `GET /boards` | 公開 | 監控中的看板列表 |
| `GET /users` | Basic Auth | 使用者列表 + 統計（HTML） |
| `GET /users/{account}` | Basic Auth | 單一使用者 JSON |
| `POST /users` | Basic Auth | 建立使用者 |
| `PUT /users/{account}` | Basic Auth | 更新使用者 |
| `POST /broadcast` | Basic Auth | 群發 Discord 訊息 |

範例：
```bash
curl -u admin:yourpw http://127.0.0.1:9090/users
curl -u admin:yourpw -X POST http://127.0.0.1:9090/broadcast \
  -H 'Content-Type: application/json' \
  -d '{"content": "系統公告：今晚 23:00 維護"}'
```

## Mac 背景運作 (LaunchAgent)

```bash
bash deploy/install.sh
```

腳本會：
1. 把 `deploy/com.user.pttalertor.plist` 模板渲染上目前路徑
2. 複製到 `~/Library/LaunchAgents/`
3. 透過 `launchctl load -w` 啟用

`KeepAlive` 會在 crash 時自動重啟（30 秒節流）；登入時自動啟動。Logs 在 `logs/stdout.log` / `logs/stderr.log`。

停止：
```bash
bash deploy/uninstall.sh
```

## 資料儲存

純檔案 JSON，路徑 `data/`：
- `data/users/<channelID>.json` — 每個 user 一檔
- `data/boards/<board>.json` — 看板文章 baseline
- `data/article_subs.json` — 推文追蹤反查
- `data/pushsum_subs.json` — 推噓文監控反查
- `data/heartbeat.json` — 上次心跳時戳（recovery 用）

## 開發

```bash
.venv/bin/python -m pytest -q
```

## 從 Go 版本移植的設計

- 移除 Redis / DynamoDB / PostgreSQL；用「記憶體 dict + write-through JSON」取代
- 移除 LINE / Telegram / Messenger / Mail
- 移除 Web 前台、ranking / top、shorturl、各平台 OAuth
- 保留：所有 PTT 訂閱類型、5 分鐘去重、7 天 recovery、管理員後台 + 廣播

## Troubleshooting

- **bot 不回應**：檢查 `logs/stderr.log`、`Bot Ready` 是否出現
- **使用者沒收到通知**：確認 `data/users/<channelID>.json` 存在且 `enable=true`
- **Bot 在伺服器內收不到訊息**：這是正常的，刻意不啟用 `MESSAGE_CONTENT` 特權 intent。請使用者改用 @mention 或私訊
- 若想改成「免 @mention 也能讀」：到 Developer Portal → Bot → 開啟 `MESSAGE CONTENT INTENT`，然後修改 [bot/client.py](ptt_alertor/bot/client.py) 加回 `intents.message_content = True`
- **PTT 看板 fetch 一直失敗**：可能站台暫時掛掉；KeepAlive 不會處理這種非 crash 的錯，bot 自己會重試

## License

繼承原 Go 專案授權（見 [LICENSE](LICENSE)）。
