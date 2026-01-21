package discord

import (
	"encoding/json"
	"fmt"
	"io/ioutil"

	log "github.com/Ptt-Alertor/logrus"
	"github.com/bwmarrin/discordgo"

	"github.com/Ptt-Alertor/ptt-alertor/models"
	"github.com/Ptt-Alertor/ptt-alertor/models/author"
	"github.com/Ptt-Alertor/ptt-alertor/models/keyword"
	"github.com/Ptt-Alertor/ptt-alertor/models/pushsum"
	"github.com/Ptt-Alertor/ptt-alertor/models/subscription"
	"github.com/Ptt-Alertor/ptt-alertor/models/user"
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

// SaveUserChannel 儲存使用者與頻道對應
func SaveUserChannel(userID, channelID, channelType, guildID string) error {
	account := discordAccountKey(channelID)
	u := models.User().Find(account)
	isNewAccount := u.Profile.Account == ""

	if isNewAccount {
		migrated, err := migrateLegacyDiscordUser(userID, account)
		if err != nil {
			return err
		}
		if migrated != nil {
			u = *migrated
		} else {
			u.Profile.Account = account
			u.Profile.Type = "discord"
		}
	}

	u.Enable = true
	u.Profile.Type = "discord"
	u.Profile.Discord = &user.DiscordIdentity{
		UserID:      userID,
		ChannelID:   channelID,
		ChannelType: channelType,
		GuildID:     guildID,
	}

	var err error
	if isNewAccount {
		err = u.Save()
	} else {
		err = u.Update()
	}
	if err != nil {
		log.WithError(err).Error("儲存 Discord 頻道資訊失敗")
	}
	return err
}

// CheckDiscordChannelExist 檢查用戶是否已設定 Discord 頻道
func CheckDiscordChannelExist(channelID string) bool {
	account := discordAccountKey(channelID)
	u := models.User().Find(account)
	return u.Profile.Account != ""
}

// Notify 發送 Discord 通知
func Notify(channelID string, message string) error {
	if discordSession == nil {
		err := fmt.Errorf("Discord 會話未初始化")
		log.WithError(err).Error("Discord 通知失敗")
		return err
	}

	messagePreview := message
	if len(message) > 50 {
		messagePreview = message[:50] + "..."
	}

	log.WithFields(log.Fields{
		"channelID":       channelID,
		"message_length":  len(message),
		"message_preview": messagePreview,
	}).Info("嘗試發送 Discord 通知")

	_, err := discordSession.ChannelMessageSend(channelID, message)
	if err != nil {
		log.WithFields(log.Fields{
			"channelID": channelID,
			"error":     err.Error(),
		}).Error("Discord 通知失敗")
		return err
	}

	log.WithFields(log.Fields{
		"channelID": channelID,
	}).Info("Discord 通知發送成功")

	return nil
}

// Close 關閉 Discord 連接
func Close() {
	if discordSession != nil {
		discordSession.Close()
	}
}

const discordAccountPrefix = "discord-"

func discordAccountKey(channelID string) string {
	return discordAccountPrefix + channelID
}

func migrateLegacyDiscordUser(userID, newAccount string) (*user.User, error) {
	if userID == "" || userID == newAccount {
		return nil, nil
	}

	legacy := models.User().Find(userID)
	if legacy.Profile.Account == "" {
		return nil, nil
	}

	oldAccount := legacy.Profile.Account
	newUser := legacy
	transferDiscordSubscriptions(oldAccount, newAccount, newUser.Subscribes)
	newUser.Profile.Account = newAccount
	disableLegacyDiscordAccount(oldAccount)
	return &newUser, nil
}

func transferDiscordSubscriptions(oldAccount, newAccount string, subs subscription.Subscriptions) {
	if oldAccount == "" || newAccount == "" || oldAccount == newAccount {
		return
	}

	for _, sub := range subs {
		if len(sub.Keywords) > 0 {
			if err := keyword.AddSubscriber(sub.Board, newAccount); err != nil {
				log.WithError(err).Warn("migrate keyword subscriber failed")
			}
			if err := keyword.RemoveSubscriber(sub.Board, oldAccount); err != nil {
				log.WithError(err).Warn("cleanup keyword subscriber failed")
			}
		}
		if len(sub.Authors) > 0 {
			if err := author.AddSubscriber(sub.Board, newAccount); err != nil {
				log.WithError(err).Warn("migrate author subscriber failed")
			}
			if err := author.RemoveSubscriber(sub.Board, oldAccount); err != nil {
				log.WithError(err).Warn("cleanup author subscriber failed")
			}
		}
		if len(sub.Articles) > 0 {
			for _, code := range sub.Articles {
				a := models.Article()
				a.Code = code
				if err := a.AddSubscriber(newAccount); err != nil {
					log.WithError(err).Warn("migrate article subscriber failed")
				}
				if err := a.RemoveSubscriber(oldAccount); err != nil {
					log.WithError(err).Warn("cleanup article subscriber failed")
				}
			}
		}
		if sub.PushSum != subscription.EmptyPushSum {
			if !pushsum.Exist(sub.Board) {
				if err := pushsum.Add(sub.Board); err != nil {
					log.WithError(err).Warn("add pushsum board failed during migrate")
				}
			}
			if err := pushsum.AddSubscriber(sub.Board, newAccount); err != nil {
				log.WithError(err).Warn("migrate pushsum subscriber failed")
			}
			if err := pushsum.RemoveSubscriber(sub.Board, oldAccount); err != nil {
				log.WithError(err).Warn("cleanup pushsum subscriber failed")
			}
			if err := pushsum.DelDiffList(oldAccount, sub.Board, "up"); err != nil {
				log.WithError(err).Warn("cleanup pushsum up diff failed")
			}
			if err := pushsum.DelDiffList(oldAccount, sub.Board, "down"); err != nil {
				log.WithError(err).Warn("cleanup pushsum down diff failed")
			}
		}
	}
}

func disableLegacyDiscordAccount(account string) {
	legacy := models.User().Find(account)
	if legacy.Profile.Account == "" {
		return
	}
	legacy.Enable = false
	legacy.Subscribes = nil
	legacy.Profile.Discord = nil
	if err := legacy.Update(); err != nil {
		log.WithError(err).WithField("account", account).Warn("disable legacy Discord account failed")
	}
}
