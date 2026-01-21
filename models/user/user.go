package user

import (
	"errors"
	"time"

	"github.com/Ptt-Alertor/ptt-alertor/models/subscription"
)

type User struct {
	Enable     bool      `json:"enable"`
	CreateTime time.Time `json:"createTime"`
	UpdateTime time.Time `json:"updateTime"`
	Profile    `json:"Profile"`
	Subscribes subscription.Subscriptions
	drive      Driver
}

type Profile struct {
	Account          string `json:"account"`
	Type             string `json:"type,omitempty"`
	Email            string `json:"email"`
	Line             string `json:"line"`
	LineAccessToken  string `json:"lineAccessToken"`
	Messenger        string `json:"messenger"`
	Telegram         string `json:"telegram"`
	TelegramChat     int64  `json:"telegramChat"`
	Discord          *DiscordIdentity `json:"discord,omitempty"`
	// LegacyDiscordChannelID is kept for backward compatibility with old JSON data.
	LegacyDiscordChannelID string `json:"discordChannelID,omitempty"`
}

type Driver interface {
	List() (accounts []string)
	Exist(account string) bool
	Save(account string, user interface{}) error
	Update(account string, user interface{}) error
	Find(account string, user *User)
}

var ErrAccountEmpty = errors.New("account can not be empty")

func NewUser(drive Driver) *User {
	return &User{
		drive: drive,
	}
}

func (u User) All() (us []*User) {
	accounts := u.drive.List()
	for _, account := range accounts {
		user := u.Find(account)
		us = append(us, &user)
	}
	return us
}

func (u User) Save() error {

	if u.drive.Exist(u.Profile.Account) {
		return errors.New("user already exist")
	}

	if u.Profile.Account == "" {
		return ErrAccountEmpty
	}

	if u.Profile.Email == "" && u.Profile.Line == "" && u.Profile.Messenger == "" && u.Profile.Telegram == "" && u.Profile.DiscordChannelID() == "" {
		return errors.New("one of Email, Line, Messenger, Telegram or Discord have to be filled")
	}
	u.CreateTime = time.Now()
	u.UpdateTime = time.Now()

	return u.drive.Save(u.Profile.Account, u)
}

func (u User) Update() error {

	if !u.drive.Exist(u.Profile.Account) {
		return errors.New("user not exist")
	}

	if u.Profile.Account == "" {
		return ErrAccountEmpty
	}

	u.UpdateTime = time.Now()
	return u.drive.Update(u.Profile.Account, u)
}

func (u User) Find(account string) User {
	u.drive.Find(account, &u)
	u.Profile.normalizeDiscord()
	return u
}

// DiscordIdentity stores Discord specific routing metadata.
type DiscordIdentity struct {
	UserID      string `json:"userId"`
	ChannelID   string `json:"channelId"`
	ChannelType string `json:"channelType"`
	GuildID     string `json:"guildId,omitempty"`
}

func (p *Profile) normalizeDiscord() {
	if p.Discord == nil && p.LegacyDiscordChannelID != "" {
		p.Discord = &DiscordIdentity{
			ChannelID:   p.LegacyDiscordChannelID,
			ChannelType: "legacy",
		}
		p.LegacyDiscordChannelID = ""
	}
}

func (p Profile) DiscordChannelID() string {
	if p.Discord != nil && p.Discord.ChannelID != "" {
		return p.Discord.ChannelID
	}
	return p.LegacyDiscordChannelID
}

func (p Profile) DiscordGuildID() string {
	if p.Discord != nil {
		return p.Discord.GuildID
	}
	return ""
}
