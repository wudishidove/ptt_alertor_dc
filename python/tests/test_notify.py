import time

from ptt_alertor.notify import Deduper, split_message


class TestSplitter:
    def test_short_passthrough(self):
        assert split_message("hello") == ["hello"]

    def test_split_on_newline(self):
        text = "\n".join(["a" * 500] * 5)
        chunks = split_message(text, limit=1000)
        assert all(len(c) <= 1000 for c in chunks)
        assert "\n".join(chunks).replace("\n\n", "\n").startswith("a" * 500)

    def test_hard_split_long_line(self):
        text = "x" * 3500
        chunks = split_message(text, limit=2000)
        assert len(chunks) == 2
        assert chunks[0] == "x" * 2000
        assert chunks[1] == "x" * 1500

    def test_boundary_2000(self):
        text = "y" * 2000
        chunks = split_message(text, limit=2000)
        assert chunks == ["y" * 2000]


class TestDeduper:
    def test_first_send_not_duplicate(self):
        d = Deduper(ttl_seconds=5)
        assert d.is_duplicate("u1", "c1", "hello") is False

    def test_second_send_is_duplicate(self):
        d = Deduper(ttl_seconds=5)
        d.is_duplicate("u1", "c1", "hello")
        assert d.is_duplicate("u1", "c1", "hello") is True

    def test_different_account_not_dup(self):
        d = Deduper(ttl_seconds=5)
        d.is_duplicate("u1", "c1", "hello")
        assert d.is_duplicate("u2", "c1", "hello") is False

    def test_expiry(self, monkeypatch):
        d = Deduper(ttl_seconds=1)
        base = [time.monotonic()]
        monkeypatch.setattr(time, "monotonic", lambda: base[0])
        d.is_duplicate("u1", "c1", "hi")
        base[0] += 2
        assert d.is_duplicate("u1", "c1", "hi") is False
