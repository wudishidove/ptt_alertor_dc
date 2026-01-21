package discord

import (
	"fmt"
	"regexp"
	"strings"

	log "github.com/Ptt-Alertor/logrus"
	"github.com/Ptt-Alertor/ptt-alertor/command"
	"github.com/Ptt-Alertor/ptt-alertor/models"
	"github.com/Ptt-Alertor/ptt-alertor/myutil"
	"github.com/bwmarrin/discordgo"
)

const maxCharacters = 2000

// 在 init() 中的 Discord 連接已在 notify.go 中初始化

// HandleReady 處理 Discord Bot 準備就緒的事件
func HandleReady(s *discordgo.Session, event *discordgo.Ready) {
	log.WithFields(log.Fields{
		"BotName":    event.User.Username,
		"SessionID":  event.SessionID,
		"GuildCount": len(event.Guilds),
	}).Info("Discord Bot 已準備就緒！")

	// 更新 Bot 的狀態
	err := s.UpdateGameStatus(0, "監控 PTT 中...")
	if err != nil {
		log.WithError(err).Error("更新 Discord Bot 狀態失敗")
	}
}

// HandleMessage 處理來自 Discord 的訊息
func HandleMessage(session *discordgo.Session, m *discordgo.MessageCreate) {
	// 忽略自己發出的訊息
	if m.Author.ID == session.State.User.ID {
		return
	}

	// 忽略其他機器人的訊息，避免彼此干擾
	if m.Author.Bot {
		return
	}

	var responseText string
	userID := m.Author.ID
	channelID := m.ChannelID
	guildID := ""
	accountKey := discordAccountKey(channelID)

	// 檢查是否為伺服器頻道
	if m.GuildID != "" {
		guildID = m.GuildID
	}

	// 判斷帳戶類型：私人訊息還是伺服器頻道
	accountType := accountTypeUser
	if guildID != "" {
		accountType = accountTypeGuild
	}

	text := strings.TrimSpace(m.Content)

	// 設定接收通知的頻道
	if strings.EqualFold(text, "notify") {
		err := SaveUserChannel(userID, channelID, accountType, guildID)
		if err != nil {
			session.ChannelMessageSend(channelID, "設定通知頻道失敗，請稍後再試。")
			return
		}
		session.ChannelMessageSend(channelID, "已設定此頻道接收 PTT 最新文章通知！")
		return
	}

	// 確認使用者是否設定接收通知的頻道
	// Check if bot is mentioned (only relevant for guild channels)
	isBotMentioned := false
	if accountType == accountTypeGuild {
		for _, user := range m.Mentions {
			if user.ID == session.State.User.ID {
				isBotMentioned = true
				break
			}
		}
	}

	// 檢查使用者是否需要設定訊息
	if !CheckDiscordChannelExist(channelID) {
		// 只在私人訊息或在公開頻道被提及時發送設定訊息
		if accountType == accountTypeUser || isBotMentioned {
			session.ChannelMessageSend(channelID, getDiscordNotifySetupMessage(accountType))
		}
		// 如果頻道未設定，則直接返回，因為後續指令需要設定頻道
		return
	}

	// 如果 text 為空（例如只有空白），則不處理
	if text == "" {
		return
	}

	// 批次刪除確認
	if match, _ := regexp.MatchString("^(刪除|刪除作者)+\\s.*\\*+", text); match {
		SendConfirmMessage(session, channelID, text)
		return
	}

	responseText = command.HandleCommand(text, accountKey, accountType == accountTypeUser)

	if responseText == "" {
		return
	}

	// 分割超過最大字元數的訊息
	for _, msg := range myutil.SplitTextByLineBreak(responseText, maxCharacters) {
		session.ChannelMessageSend(channelID, msg)
	}
}

// getDiscordNotifySetupMessage 取得設定通知的提示訊息
func getDiscordNotifySetupMessage(accountType string) string {
	var targetName string
	if accountType == accountTypeGuild {
		targetName = "此頻道"
	} else {
		targetName = "私人訊息"
	}

	return fmt.Sprintf(`歡迎使用 Ptt Alertor。
請輸入「notify」來設定 %s 接收 PTT 最新文章通知。
`, targetName)
}

// HandleJoin 處理加入伺服器事件
func HandleJoin(session *discordgo.Session, event *discordgo.GuildCreate) {
	// 當機器人被加入新伺服器時觸發
	log.WithFields(log.Fields{
		"GuildID":   event.Guild.ID,
		"GuildName": event.Guild.Name,
	}).Info("Discord Bot joined a new guild")
}

// HandleLeave 處理離開伺服器事件
func HandleLeave(session *discordgo.Session, event *discordgo.GuildDelete) {
	// 當機器人被踢出伺服器時觸發
	log.WithFields(log.Fields{
		"GuildID": event.Guild.ID,
	}).Info("Discord Bot left a guild")

	// 停用該伺服器所有使用者的通知
	allUsers := models.User().All()
	for _, u := range allUsers {
		channelID := u.Profile.DiscordChannelID()
		if channelID == "" {
			continue
		}
		if u.Profile.DiscordGuildID() != event.Guild.ID {
			continue
		}
		log.WithFields(log.Fields{
			"UserID":    u.Profile.Account,
			"GuildID":   event.Guild.ID,
			"ChannelID": channelID,
		}).Info("Disabling user due to bot leaving guild")
		u.Enable = false
		if err := u.Update(); err != nil {
			log.WithError(err).WithFields(log.Fields{
				"UserID": u.Profile.Account,
			}).Error("Failed to disable user during HandleLeave")
		}
	}
}

const (
	accountTypeUser  = "user"
	accountTypeGuild = "guild"
)

// SendMessage 發送 Discord 訊息
func SendMessage(channelID string, message string) {
	if discordSession == nil {
		log.Error("Discord 會話未初始化")
		return
	}

	_, err := discordSession.ChannelMessageSend(channelID, message)
	if err != nil {
		log.WithFields(log.Fields{
			"ChannelID": channelID,
			"Error":     err.Error(),
		}).Error("Discord Send Message Failed")
	} else {
		log.WithFields(log.Fields{
			"ChannelID": channelID,
		}).Info("Discord Message Sent")
	}
}

// SendConfirmMessage 發送確認訊息
func SendConfirmMessage(session *discordgo.Session, channelID string, command string) {
	message := fmt.Sprintf("確定%s？請回覆「是」或「否」", command)
	session.ChannelMessageSend(channelID, message)
}

// BroadcastMessage 廣播訊息給多個頻道
func BroadcastMessage(channelIDs []string, message string) {
	if discordSession == nil {
		log.Error("Discord 會話未初始化")
		return
	}

	for _, channelID := range channelIDs {
		SendMessage(channelID, message)
	}
}
