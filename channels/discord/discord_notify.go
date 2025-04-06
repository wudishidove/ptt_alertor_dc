package discord

import (
	"encoding/json"
	"fmt"
	"io/ioutil"

	log "github.com/Ptt-Alertor/logrus"
	"github.com/bwmarrin/discordgo"

	"github.com/Ptt-Alertor/ptt-alertor/models"
)

type Config struct {
	DiscordToken string `json:"DISCORD_TOKEN"`
}

var (
	config         Config
	discordSession *discordgo.Session
)

func init() {
	configFile, err := ioutil.ReadFile("channels/discord/config.json")
	if err != nil {
		log.WithError(err).Error("讀取 Discord 配置文件失敗")
		return
	}

	err = json.Unmarshal(configFile, &config)
	if err != nil {
		log.WithError(err).Error("解析 Discord 配置文件失敗")
		return
	}

	// 初始化 Discord 連接
	session, err := discordgo.New("Bot " + config.DiscordToken)
	if err != nil {
		log.WithError(err).Error("創建 Discord 連接失敗")
		return
	}

	discordSession = session

	// 註冊事件處理器
	discordSession.AddHandler(HandleMessage)
	discordSession.AddHandler(HandleJoin)
	discordSession.AddHandler(HandleLeave)
	discordSession.AddHandler(HandleReady) // 添加 Ready 事件處理器

	// 開始連接
	err = discordSession.Open()
	if err != nil {
		log.WithError(err).Error("連接 Discord 失敗")
		return
	}

	log.Info("Discord 機器人已連接")
}

// SaveUserChannel 儲存使用者的 Discord 頻道 ID
func SaveUserChannel(userID string, channelID string) error {
	u := models.User().Find(userID)

	// 如果用戶不存在，創建新用戶
	if u.Profile.Account == "" {
		u.Profile.Account = userID
		u.Profile.Type = "discord"
		u.Profile.DiscordChannelID = channelID // 在創建時就設定 Discord 頻道 ID
		u.Enable = true

		// 保存新用戶
		if err := u.Save(); err != nil {
			log.WithError(err).Error("創建新用戶失敗")
			return err
		}
		return nil // 如果是新用戶，創建成功後直接返回
	}

	// 如果用戶已存在，更新 Discord 頻道 ID
	u.Profile.DiscordChannelID = channelID
	if err := u.Update(); err != nil {
		log.WithError(err).Error("更新使用者 Discord 頻道失敗")
		return err
	}
	return nil
}

// CheckDiscordChannelExist 檢查用戶是否已設定 Discord 頻道
func CheckDiscordChannelExist(userID string) bool {
	u := models.User().Find(userID)
	if u.Profile.DiscordChannelID == "" {
		return false
	}
	return true
}

// Notify 發送 Discord 通知
func Notify(channelID string, message string) error {
	if discordSession == nil {
		err := fmt.Errorf("Discord 會話未初始化")
		log.WithError(err).Error("Discord 通知失敗")
		return err
	}

	_, err := discordSession.ChannelMessageSend(channelID, message)
	if err != nil {
		log.WithFields(log.Fields{
			"channelID": channelID,
			"error":     err.Error(),
		}).Error("Discord 通知失敗")
		return err
	}

	return nil
}

// Close 關閉 Discord 連接
func Close() {
	if discordSession != nil {
		discordSession.Close()
	}
}
