from ptt_alertor.matching import (
    hits_threshold,
    match_any_keyword,
    match_author,
    match_keyword,
)


class TestSimpleKeyword:
    def test_substring_match(self):
        assert match_keyword("[新聞] 金城武代言新片", "金城武")

    def test_substring_case_insensitive(self):
        assert match_keyword("[News] iPhone 16 Pro Released", "iphone")

    def test_no_match(self):
        assert not match_keyword("[新聞] 結衣婚禮", "金城武")


class TestAndKeyword:
    def test_all_present(self):
        assert match_keyword("[新聞] 金城武 與 結衣 同框", "金城武&結衣")

    def test_one_missing(self):
        assert not match_keyword("[新聞] 金城武獨家專訪", "金城武&結衣")

    def test_three_parts(self):
        assert match_keyword("[公告] alpha beta gamma", "alpha&beta&gamma")
        assert not match_keyword("[公告] alpha beta only", "alpha&beta&gamma")


class TestRegexpKeyword:
    def test_anchor(self):
        assert match_keyword("[新聞] 標題", "regexp:^\\[新聞\\]")

    def test_no_anchor_match(self):
        assert not match_keyword("[公告] 標題", "regexp:^\\[新聞\\]")

    def test_invalid_regex_returns_false(self):
        assert not match_keyword("anything", "regexp:[unclosed")


class TestExcludeKeyword:
    def test_excluded(self):
        assert not match_keyword("[徵求] 室友", "!徵")

    def test_passed(self):
        assert match_keyword("[新聞] 室友", "!徵")


class TestMatchAny:
    def test_returns_first_hit(self):
        assert match_any_keyword("[新聞] 金城武", ["結衣", "金城武"]) == "金城武"

    def test_no_match_returns_none(self):
        assert match_any_keyword("[新聞] X", ["A", "B"]) is None


class TestAuthor:
    def test_case_insensitive(self):
        assert match_author("OBOV", "obov")

    def test_distinct(self):
        assert not match_author("ffaarr", "obov")


class TestPushsumThreshold:
    def test_above_up(self):
        assert hits_threshold(50, up=30, down=0)

    def test_below_up(self):
        assert not hits_threshold(20, up=30, down=0)

    def test_below_down(self):
        assert hits_threshold(-50, up=0, down=-30)

    def test_above_down(self):
        assert not hits_threshold(-10, up=0, down=-30)

    def test_no_subscription(self):
        assert not hits_threshold(50, up=0, down=0)

    def test_both_thresholds(self):
        assert hits_threshold(99, up=50, down=-50)
        assert hits_threshold(-99, up=50, down=-50)
        assert not hits_threshold(0, up=50, down=-50)
