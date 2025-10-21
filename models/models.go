package models

import (
	"os"
	"strings"

	"github.com/Ptt-Alertor/ptt-alertor/models/article"
	"github.com/Ptt-Alertor/ptt-alertor/models/board"
	"github.com/Ptt-Alertor/ptt-alertor/models/user"
)

var User = func() *user.User {
	// 使用環境變數 USER_STORE 選擇使用者儲存驅動："redis" 或 "file"
	// 預設使用 redis；若本機或 Windows 環境曾遇到 Redis 資料遺失，可改為 file。
	store := strings.ToLower(os.Getenv("USER_STORE"))
	if store == "file" {
		return user.NewUser(new(user.File))
	}
	return user.NewUser(new(user.Redis))
}
var Article = func() *article.Article {
	return article.NewArticle(new(article.Redis))
}
var Board = func() *board.Board {
	return board.NewBoard(new(board.Redis), new(board.Redis))
}
