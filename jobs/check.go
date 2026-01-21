package jobs

import (
	"crypto/md5"
	"encoding/hex"
	"sync"
	"time"

	log "github.com/Ptt-Alertor/logrus"

	"github.com/Ptt-Alertor/ptt-alertor/channels/discord"
	"github.com/Ptt-Alertor/ptt-alertor/channels/line"
	"github.com/Ptt-Alertor/ptt-alertor/channels/mail"
	"github.com/Ptt-Alertor/ptt-alertor/channels/messenger"
	"github.com/Ptt-Alertor/ptt-alertor/channels/telegram"
	"github.com/Ptt-Alertor/ptt-alertor/models/counter"
)

const workers = 300

var ckCh = make(chan check)

// 添加一個通知去重的緩存，以防止短時間內相同通知多次發送
var (
	// msgCache 保存已發送通知的哈希值，防止重複
	msgCache = make(map[string]time.Time)
	// msgCacheMutex 保護msgCache的併發訪問
	msgCacheMutex sync.Mutex
	// msgCacheExpire 設置緩存過期時間（5分鐘）
	msgCacheExpire = 5 * time.Minute
)

// 檢查通知是否已經發送過
func isMessageSent(c check) bool {
	// 使用通知的內容、用戶ID和平台創建一個唯一哈希
	content := c.String()
	cr := c.Self()
	channelID := cr.Profile.DiscordChannelID()
	key := cr.Profile.Account + "_" + channelID + "_" + content
	hash := md5.Sum([]byte(key))
	hashStr := hex.EncodeToString(hash[:])

	msgCacheMutex.Lock()
	defer msgCacheMutex.Unlock()

	// 清理過期的緩存
	now := time.Now()
	for k, v := range msgCache {
		if now.Sub(v) > msgCacheExpire {
			delete(msgCache, k)
		}
	}

	// 檢查是否已發送過
	if _, exists := msgCache[hashStr]; exists {
		log.WithFields(log.Fields{
			"account": cr.Profile.Account,
			"board":   cr.board,
			"type":    cr.subType,
			"word":    cr.word,
		}).Warn("通知已在短時間內發送過，忽略此次發送")
		return true
	}

	// 添加到已發送列表
	msgCache[hashStr] = now
	return false
}

func init() {
	for i := 0; i < workers; i++ {
		go messageWorker(ckCh)
	}
}

func messageWorker(ckCh chan check) {
	for {
		ck := <-ckCh
		sendMessage(ck)
	}
}

type check interface {
	String() string
	Self() Checker
	Stop()
	Run()
}

func sendMessage(c check) {
	// 先檢查是否在短時間內已經發送過相同的通知
	if isMessageSent(c) {
		return
	}

	cr := c.Self()
	account := cr.Profile.Account
	channelID := cr.Profile.DiscordChannelID()
	var platform string

	if cr.Profile.Line != "" && cr.Profile.LineAccessToken == "" {
		platform = "line"
		log.WithFields(log.Fields{
			"account":  account,
			"platform": platform,
			"board":    cr.board,
			"type":     cr.subType,
			"word":     cr.word,
		}).Warn("Message Sent without LINE Notify Connection")
		return
	}
	if cr.Profile.Email != "" {
		platform = "mail"
		sendMail(c)
	}
	if cr.Profile.LineAccessToken != "" {
		platform = "line"
		sendLineNotify(c)
	}
	if cr.Profile.Messenger != "" {
		platform = "messenger"
		sendMessenger(c)
	}
	if cr.Profile.Telegram != "" {
		platform = "telegram"
		sendTelegram(c)
	}
	if channelID != "" {
		platform = "discord"
		sendDiscord(c)
	}
	counter.IncrAlert()
	log.WithFields(log.Fields{
		"account":  account,
		"platform": platform,
		"board":    cr.board,
		"type":     cr.subType,
		"word":     cr.word,
	}).Info("Message Sent")
}

func sendMail(c check) {
	cr := c.Self()
	m := new(mail.Mail)
	m.Title.BoardName = cr.board
	m.Title.Keyword = cr.keyword
	m.Body.Articles = cr.articles
	m.Receiver = cr.Profile.Email
	m.Send()
}

func sendLine(c check) {
	cr := c.Self()
	line.PushTextMessage(cr.Profile.Line, c.String())
}

func sendLineNotify(c check) {
	cr := c.Self()
	line.Notify(cr.Profile.LineAccessToken, c.String())
}

func sendMessenger(c check) {
	cr := c.Self()
	m := messenger.New()
	m.SendTextMessage(cr.Profile.Messenger, c.String())
}

func sendTelegram(c check) {
	cr := c.Self()
	telegram.SendTextMessage(cr.Profile.TelegramChat, c.String())
}

func sendDiscord(c check) {
	cr := c.Self()
	channelID := cr.Profile.DiscordChannelID()
	content := c.String()
	contentPreview := content
	if len(content) > 50 {
		contentPreview = content[:50] + "..."
	}

	log.WithFields(log.Fields{
		"account":         cr.Profile.Account,
		"channelID":       channelID,
		"board":           cr.board,
		"subType":         cr.subType,
		"word":            cr.word,
		"content_preview": contentPreview,
	}).Info("準備發送 Discord 通知")

	discord.Notify(channelID, content)
}
