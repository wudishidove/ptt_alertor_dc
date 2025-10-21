package jobs

import (
	"time"

	"strings"

	"io/ioutil"
	"os"
	"path/filepath"

	log "github.com/Ptt-Alertor/logrus"
	"github.com/Ptt-Alertor/ptt-alertor/connections"
	"github.com/Ptt-Alertor/ptt-alertor/models"
	"github.com/Ptt-Alertor/ptt-alertor/models/article"
	"github.com/Ptt-Alertor/ptt-alertor/models/author"
	"github.com/Ptt-Alertor/ptt-alertor/models/keyword"
	"github.com/garyburd/redigo/redis"
)

const heartbeatKey = "system:last_heartbeat"
const heartbeatFile = "storage/heartbeat.txt"

// StartHeartbeat writes a timestamp every minute to persistent storage.
func StartHeartbeat() {
	go func() {
		writeHeartbeat()
		ticker := time.NewTicker(1 * time.Minute)
		defer ticker.Stop()
		for t := range ticker.C {
			writeHeartbeatWithTime(t)
		}
	}()
}

func writeHeartbeat() {
	writeHeartbeatWithTime(time.Now())
}

func writeHeartbeatWithTime(t time.Time) {
	conn := connections.Redis()
	defer conn.Close()
	_, err := conn.Do("SET", heartbeatKey, t.UTC().Format(time.RFC3339))
	if err != nil {
		log.WithError(err).Error("Write heartbeat failed")
	}
	// file fallback
	if err := writeHeartbeatFile(t); err != nil {
		log.WithError(err).Warn("Write heartbeat file failed")
	}
	log.WithField("time", t.UTC().Format(time.RFC3339)).Info("Heartbeat saved")
}

// RecoverFromLastHeartbeat backfills missed events (keywords/authors) since last recorded heartbeat.
// It MUST run before any job that overwrites board articles snapshot (e.g., Fetcher).
func RecoverFromLastHeartbeat() {
	last := mostRecentHeartbeat()
	if last.IsZero() {
		log.Warn("No last heartbeat found, skip recovery")
		return
	}

	log.WithField("since", last.In(time.FixedZone("CST", 8*60*60)).Format(time.RFC3339)).Info("Start recovery from last heartbeat")

	boards := models.Board().All()
	for _, bd := range boards {
		// Compute new articles by comparing saved snapshot and online snapshot
		bd.WithNewArticles()

		// If first-time or no new articles
		firstTime := bd.NewArticles == nil
		if len(bd.NewArticles) == 0 {
			// Still move baseline forward when we have online articles
			if firstTime && len(bd.OnlineArticles) > 0 {
				bd.Articles = bd.OnlineArticles
				if err := bd.Save(); err != nil {
					log.WithField("board", bd.Name).WithError(err).Warn("Save board snapshot (create) failed")
				}
			}
			continue
		}

		// Filter bd.NewArticles by day cutoff (PTT article list only provides MM/DD). This may include same-day older items.
		filtered := filterArticlesByDateSince(bd.NewArticles, last)
		if len(filtered) == 0 {
			// Move baseline and continue
			bd.Articles = bd.OnlineArticles
			if err := bd.Save(); err != nil {
				log.WithField("board", bd.Name).WithError(err).Warn("Save board snapshot failed")
			}
			continue
		}

		// Send keyword-based notifications for filtered articles
		sendBackfillForKeywords(bd.Name, filtered)
		// Send author-based notifications for filtered articles
		sendBackfillForAuthors(bd.Name, filtered)

		// Move baseline forward to avoid duplicate sends when live checker starts
		bd.Articles = bd.OnlineArticles
		if err := bd.Save(); err != nil {
			log.WithField("board", bd.Name).WithError(err).Warn("Save board snapshot (after backfill) failed")
		}
	}

	log.Info("Recovery finished")
}

func readLastHeartbeat() time.Time {
	conn := connections.Redis()
	defer conn.Close()
	val, err := redis.String(conn.Do("GET", heartbeatKey))
	if err != nil || strings.TrimSpace(val) == "" {
		if err != nil && err != redis.ErrNil {
			log.WithError(err).Warn("Read last heartbeat failed")
		}
		return time.Time{}
	}
	// Parse stored RFC3339 in UTC
	t, err := time.Parse(time.RFC3339, val)
	if err != nil {
		log.WithError(err).Warn("Parse last heartbeat failed")
		return time.Time{}
	}
	return t
}

// writeHeartbeatFile writes UTC RFC3339 time to storage/heartbeat.txt
func writeHeartbeatFile(t time.Time) error {
	dir := filepath.Dir(heartbeatFile)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return err
		}
	}
	return ioutil.WriteFile(heartbeatFile, []byte(t.UTC().Format(time.RFC3339)), 0644)
}

func readHeartbeatFile() time.Time {
	b, err := ioutil.ReadFile(heartbeatFile)
	if err != nil {
		return time.Time{}
	}
	s := strings.TrimSpace(string(b))
	if s == "" {
		return time.Time{}
	}
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return time.Time{}
	}
	return t
}

// mostRecentHeartbeat returns the newer one from Redis and file fallback
func mostRecentHeartbeat() time.Time {
	r := readLastHeartbeat()
	f := readHeartbeatFile()
	if r.IsZero() {
		return f
	}
	if f.After(r) {
		return f
	}
	return r
}

func filterArticlesByDateSince(articles article.Articles, since time.Time) article.Articles {
	loc := time.FixedZone("CST", 8*60*60)
	cutoff := since.In(loc).Truncate(24 * time.Hour)
	filtered := make(article.Articles, 0, len(articles))
	for _, a := range articles {
		// Article.Date is like "1/02" (MM/DD)
		t, err := time.ParseInLocation("1/02", a.Date, loc)
		if err != nil {
			continue
		}
		now := time.Now().In(loc)
		if t.Month() > now.Month() {
			t = t.AddDate(now.Year()-1, 0, 0)
		} else {
			t = t.AddDate(now.Year(), 0, 0)
		}
		if !t.Before(cutoff) {
			filtered = append(filtered, a)
		}
	}
	return filtered
}

func sendBackfillForKeywords(boardName string, newArticles article.Articles) {
	accounts := keyword.Subscribers(boardName)
	for _, account := range accounts {
		u := models.User().Find(account)
		if !u.Enable {
			continue
		}
		for _, sub := range u.Subscribes {
			if sub.Board != boardName {
				continue
			}
			for _, kw := range sub.Keywords {
				kArticles := make(article.Articles, 0)
				for _, na := range newArticles {
					if na.MatchKeyword(kw) {
						na.Author = ""
						kArticles = append(kArticles, na)
					}
				}
				if len(kArticles) == 0 {
					continue
				}
				c := Checker{
					board:    sub.Board,
					keyword:  kw,
					articles: kArticles,
					subType:  "keyword",
					word:     kw,
					Profile:  u.Profile,
				}
				// Enqueue to message workers
				ckCh <- c
			}
		}
	}
}

func sendBackfillForAuthors(boardName string, newArticles article.Articles) {
	accounts := author.Subscribers(boardName)
	for _, account := range accounts {
		u := models.User().Find(account)
		if !u.Enable {
			continue
		}
		for _, sub := range u.Subscribes {
			if sub.Board != boardName {
				continue
			}
			for _, au := range sub.Authors {
				aArticles := make(article.Articles, 0)
				for _, na := range newArticles {
					if strings.EqualFold(na.Author, au) {
						aArticles = append(aArticles, na)
					}
				}
				if len(aArticles) == 0 {
					continue
				}
				c := Checker{
					board:    sub.Board,
					author:   au,
					articles: aArticles,
					subType:  "author",
					word:     au,
					Profile:  u.Profile,
				}
				ckCh <- c
			}
		}
	}
}
