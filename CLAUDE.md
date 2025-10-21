# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ptt-Alertor is a multi-platform notification system for PTT (Taiwan's largest bulletin board system). It monitors PTT boards for new articles matching user-defined criteria (keywords, authors, push counts) and sends notifications via Discord, LINE, Telegram, Messenger, or email.

## Build and Run

### Local Development (Windows)
```bash
# Run with file-based user storage (recommended for local dev)
windows_run.bat
```

The batch script:
- Sets `USER_STORE=file` to avoid Redis data loss on sleep/shutdown
- Starts Redis with AOF persistence if needed
- Runs `go mod tidy` to update dependencies
- Launches the app on port 9090

### Local Development (Unix)
```bash
# Set environment variables
export USER_STORE=file
export REDIS_ENDPOINT=localhost
export REDIS_PORT=6379
export AUTH_USER=admin
export AUTH_PW=password

# Run
go mod tidy
go run main.go
```

### Docker Build
```bash
docker build -t ptt-alertor .
```

### Testing
```bash
# Run all tests with coverage
go test -race -tags test -coverprofile=coverage.txt -covermode=atomic ./...
```

## Architecture

### Core Components

**1. Monitoring Jobs (`jobs/`)**
- `checker.go`: Main keyword/author matching checker, scans boards periodically
- `pushsumchecker.go`: Monitors articles reaching specific push/boo thresholds
- `commentchecker.go`: Tracks new comments on subscribed articles
- `pttmonitor.go`: Monitors PTT availability
- `recovery.go`: Recovers monitoring state from last heartbeat

All checkers send matched results to a channel (`ckCh`) where workers route to appropriate platforms.

**2. Platform Routing (`jobs/check.go`)**
- `sendMessage()`: Routes notifications based on user profile fields:
  - `Profile.DiscordChannelID` → Discord
  - `Profile.LineAccessToken` → LINE Notify
  - `Profile.Messenger` → Messenger
  - `Profile.Telegram` → Telegram
  - `Profile.Email` → Email
- Implements 5-minute deduplication using MD5 hash of `account + channelID + content`

**3. Channel Integrations (`channels/`)**
Each platform has its own package:
- `discord/`: discordgo-based integration
- `line/`: LINE Bot SDK + LINE Notify
- `telegram/`: Telegram Bot API
- `messenger/`: Facebook Messenger webhook
- `mail/`: Mailgun email sending

**4. Command Processing (`command/command.go`)**
Handles Chinese text commands:
- `新增 <board> <keywords>`: Subscribe to keywords
- `刪除 <board> <keywords>`: Unsubscribe from keywords
- `新增作者 <board> <authors>`: Subscribe to authors
- `新增推文數 <board> <count>`: Subscribe to push count threshold
- `新增推文 <url>`: Track comments on article
- `清單`: List subscriptions
- `排行`: Show top keywords/authors

**5. Storage Abstraction (`models/`)**
- `models.go`: Factory pattern selecting storage driver
  - `USER_STORE=redis` (default): User data in Redis
  - `USER_STORE=file`: User data in `storage/users/*.json`
- `user/`: User profiles and subscriptions
- `board/`: Board metadata and article cache
- `article/`: Article content cache

### Discord Integration Deep Dive

**Initialization (`channels/discord/discord_notify.go`)**
- Reads `channels/discord/config.json` for `DISCORD_TOKEN`
- Creates `discordgo.Session` and registers event handlers in `init()`
- Automatically connects when `jobs/check.go` imports the package

**Event Handling (`channels/discord/discord.go`)**
- `HandleReady`: Sets bot status to "監控 PTT 中..."
- `HandleMessage`:
  - `notify` command → `SaveUserChannel()` binds user to current channel
  - Other text → delegates to `command.HandleCommand()`
  - Auto-splits messages >2000 chars
- `HandleJoin`: Logs server joins
- `HandleLeave`: Disables all users bound to channels in the removed server

**User Binding**
- First-time users say "notify" in DM or channel
- `SaveUserChannel(userID, channelID)` creates/updates profile:
  - `Account = userID`
  - `Type = "discord"`
  - `DiscordChannelID = channelID`
  - `Enable = true`

**Notification Flow**
1. Checker finds matching article → creates check object
2. Sends to `ckCh` channel
3. Worker calls `sendMessage()` → routes by profile
4. `sendDiscord()` → `discord.Notify(channelID, content)`
5. Message split into 2000-char chunks if needed

**Important Limitation**: Bot being removed from a server automatically disables all users in that server's channels (see `HandleLeave` in `channels/discord/discord.go`).

### Data Persistence Concerns

**Problem**: Redis data may be lost on Windows sleep/shutdown or if Redis isn't configured for persistence, causing user subscriptions to disappear.

**Solutions**:
1. **Development/Local** (recommended): Set `USER_STORE=file`
   - Stores user data in `storage/users/*.json`
   - Survives Redis restarts/flushes
   - Set in `windows_run.bat` or export as env var

2. **Production**: Enable Redis persistence
   - Enable RDB snapshots and/or AOF
   - Never run `FLUSHALL`/`FLUSHDB` in production
   - Note: `jobs/cachecleaner.go` only clears board/article cache, not `user:*` keys

## Key Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `USER_STORE` | User storage driver (`redis`/`file`) | `file` |
| `REDIS_ENDPOINT` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `AUTH_USER` | Basic auth username for `/users` API | `admin` |
| `AUTH_PW` | Basic auth password | `password` |
| `APP_HOST` | Public URL for redirects | `http://localhost:9090` |
| `BOARD_HIGH` | High-priority boards (faster scan) | `gossiping,beauty` |

Platform-specific tokens (read from JSON config or env vars):
- Discord: `channels/discord/config.json` → `DISCORD_TOKEN`
- LINE: `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESSTOKEN`
- Telegram: `TELEGRAM_TOKEN`
- Messenger: Set via platform-specific setup

## Application Lifecycle

**Initialization (`main.go:init()`)**
- `RecoverFromLastHeartbeat()`: Restores monitoring state
- `NewMigrateDB()`, `NewMigrateBoard()`: Schema/data migrations
- `NewGenerator()`, `NewFetcher()`: Pre-populate cache
- `NewCacheCleaner()`, `NewCategoryCleaner()`: Cleanup stale data

**Runtime (`main.go:startJobs()`)**
- Starts continuous checkers: `Checker`, `PushSumChecker`, `CommentChecker`, `PttMonitor`
- Cron jobs:
  - `@hourly`: Top keywords/authors ranking
  - `@every 48h`: Push sum key replacer

**Graceful Shutdown**
- Listens for `os.Interrupt`
- 5-second timeout for HTTP server shutdown
- Jobs continue running until process termination

## API Endpoints

**Public**
- `GET /`: Homepage
- `GET /boards`: List tracked boards
- `GET /boards/{board}/articles`: Articles in board
- `GET /articles`: All recent articles
- `GET /top`: Top keywords/authors

**Authenticated** (Basic Auth with `AUTH_USER`/`AUTH_PW`)
- `GET /users`: List all users
- `GET /users/{account}`: Get user profile
- `POST /users`: Create user with subscriptions
- `PUT /users/{account}`: Update user subscriptions
- `POST /broadcast`: Send broadcast to all users (platform filter supported)

**Platform Webhooks**
- `POST /line/callback`: LINE Bot webhook
- `POST /messenger/webhook`: Messenger webhook
- `POST /telegram/{token}`: Telegram webhook
- `POST /discord/*`: Not used (Discord uses gateway connection)

## Testing Strategy

- Tag integration tests with `// +build test` build tag
- Use `miniredis` for Redis mocking in tests
- Run tests: `go test -tags test ./...`
- CI runs on PR and deploy via `.github/workflows/`

## Common Patterns

**Adding a new platform integration**:
1. Create package in `channels/{platform}/`
2. Implement connection/webhook handler
3. Add `Notify(userID, content)` function
4. Import in `jobs/check.go`
5. Add routing logic in `sendMessage()` based on new profile field
6. Update `models/user/user.go` profile struct with platform ID field

**Adding a new subscription type**:
1. Add command handler in `command/command.go`
2. Create checker in `jobs/` implementing `check` interface
3. Start checker in `main.go:startJobs()`
4. Update `models/subscription/` with new subscription type

**Debugging notification issues**:
- Check logs for "Message Sent" with account/platform/board/type/word fields
- Verify 5-minute deduplication isn't blocking (see `jobs/check.go:isMessageSent`)
- For Discord: Ensure user ran "notify" and `DiscordChannelID` is set
- Check platform-specific token/config validity
