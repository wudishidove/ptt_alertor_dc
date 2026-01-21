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
	"github.com/Ptt-Alertor/ptt-alertor/ptt/web"
	"github.com/garyburd/redigo/redis"
)

const maxRecoveryDays = 7
const recoveryPageDelay = 500 * time.Millisecond

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
// It crawls PTT board pages backwards until reaching the heartbeat time or 7-day limit.
// It MUST run before any job that overwrites board articles snapshot (e.g., Fetcher).
func RecoverFromLastHeartbeat() {
	last := mostRecentHeartbeat()
	if last.IsZero() {
		log.Warn("No last heartbeat found, skip recovery")
		return
	}

	// Check if recovery is needed (if heartbeat is very recent, skip deep crawl)
	timeSinceHeartbeat := time.Since(last)
	loc := time.FixedZone("CST", 8*60*60)
	log.WithFields(log.Fields{
		"since":    last.In(loc).Format(time.RFC3339),
		"duration": timeSinceHeartbeat.Round(time.Minute).String(),
	}).Info("Start recovery from last heartbeat")

	// Get saved article IDs for each board to avoid duplicates
	boards := models.Board().All()
	for _, bd := range boards {
		// Get saved articles to determine baseline
		savedArticles := bd.GetArticles()
		savedMaxID := int64(0)
		for _, a := range savedArticles {
			if int64(a.ID) > savedMaxID {
				savedMaxID = int64(a.ID)
			}
		}

		// Fetch all articles since heartbeat (crawls multiple pages if needed)
		allArticles := fetchArticlesSinceHeartbeat(bd.Name, last)
		if len(allArticles) == 0 {
			log.WithField("board", bd.Name).Info("No articles found during recovery")
			continue
		}

		// Filter out articles we've already seen (ID <= savedMaxID)
		newArticles := make(article.Articles, 0)
		latestArticles := make(article.Articles, 0) // For updating baseline
		for _, a := range allArticles {
			if int64(a.ID) > savedMaxID {
				newArticles = append(newArticles, a)
			}
			// Keep track of latest articles for baseline update
			latestArticles = append(latestArticles, a)
		}

		if len(newArticles) == 0 {
			log.WithField("board", bd.Name).Info("No new articles after filtering")
			// Still update baseline with latest articles
			if len(latestArticles) > 0 {
				bd.Articles = latestArticles
				if err := bd.Save(); err != nil {
					log.WithField("board", bd.Name).WithError(err).Warn("Save board snapshot failed")
				}
			}
			continue
		}

		log.WithFields(log.Fields{
			"board":       bd.Name,
			"newArticles": len(newArticles),
		}).Info("Found new articles for recovery")

		// Send keyword-based notifications for new articles
		sendBackfillForKeywords(bd.Name, newArticles)
		// Send author-based notifications for new articles
		sendBackfillForAuthors(bd.Name, newArticles)

		// Move baseline forward to avoid duplicate sends when live checker starts
		// Use only the most recent page's articles as baseline (to match normal operation)
		bd.WithNewArticles()
		if len(bd.OnlineArticles) > 0 {
			bd.Articles = bd.OnlineArticles
		} else if len(latestArticles) > 0 {
			bd.Articles = latestArticles
		}
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

// fetchArticlesSinceHeartbeat fetches articles from PTT board pages going backwards
// until it finds articles older than the heartbeat time or 7 days limit.
// Returns all articles that are newer than the heartbeat time.
func fetchArticlesSinceHeartbeat(boardName string, heartbeat time.Time) article.Articles {
	// Calculate cutoff time (heartbeat or 7 days ago, whichever is more recent)
	sevenDaysAgo := time.Now().Add(-maxRecoveryDays * 24 * time.Hour)
	cutoffTime := heartbeat
	if sevenDaysAgo.After(heartbeat) {
		cutoffTime = sevenDaysAgo
		log.WithFields(log.Fields{
			"board":     boardName,
			"heartbeat": heartbeat,
			"cutoff":    sevenDaysAgo,
		}).Info("Heartbeat older than 7 days, using 7-day limit")
	}
	cutoffTimestamp := cutoffTime.Unix()

	// Get current page number
	currentPage, err := web.CurrentPage(boardName)
	if err != nil {
		log.WithField("board", boardName).WithError(err).Warn("Failed to get current page, falling back to single page")
		articles, _ := web.FetchArticles(boardName, -1)
		return articles
	}

	allArticles := make(article.Articles, 0)
	pagesProcessed := 0
	maxPages := 100 // Safety limit to prevent infinite loops

	log.WithFields(log.Fields{
		"board":       boardName,
		"currentPage": currentPage,
		"cutoffTime":  cutoffTime.In(time.FixedZone("CST", 8*60*60)).Format(time.RFC3339),
	}).Info("Starting recovery crawl")

	// Crawl from current page backwards
	for page := currentPage; page >= 1 && pagesProcessed < maxPages; page-- {
		time.Sleep(recoveryPageDelay) // Be nice to PTT servers

		articles, err := web.FetchArticles(boardName, page)
		if err != nil {
			log.WithFields(log.Fields{
				"board": boardName,
				"page":  page,
			}).WithError(err).Warn("Failed to fetch page, stopping crawl")
			break
		}

		if len(articles) == 0 {
			break
		}

		// Find the oldest article timestamp on this page
		oldestTimestamp := int64(0)
		for _, a := range articles {
			if a.ID > 0 {
				ts := int64(a.ID)
				if oldestTimestamp == 0 || ts < oldestTimestamp {
					oldestTimestamp = ts
				}
				// Only add articles newer than cutoff
				if ts > cutoffTimestamp {
					allArticles = append(allArticles, a)
				}
			}
		}

		pagesProcessed++

		// If the oldest article on this page is older than cutoff, we're done
		if oldestTimestamp > 0 && oldestTimestamp <= cutoffTimestamp {
			log.WithFields(log.Fields{
				"board":         boardName,
				"pagesProcessed": pagesProcessed,
				"articlesFound": len(allArticles),
			}).Info("Reached cutoff time, stopping crawl")
			break
		}

		// Log progress every 10 pages
		if pagesProcessed%10 == 0 {
			log.WithFields(log.Fields{
				"board":         boardName,
				"pagesProcessed": pagesProcessed,
				"articlesFound": len(allArticles),
			}).Info("Recovery crawl progress")
		}
	}

	log.WithFields(log.Fields{
		"board":          boardName,
		"totalPages":     pagesProcessed,
		"totalArticles":  len(allArticles),
	}).Info("Recovery crawl completed")

	return allArticles
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
