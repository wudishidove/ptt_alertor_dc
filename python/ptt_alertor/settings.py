from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    discord_token: str
    auth_user: str
    auth_pw: str
    web_host: str = "127.0.0.1"
    web_port: int = 9090
    high_boards: list[str] = field(default_factory=list)

    # All polling intervals in seconds. Default 60s is a deliberately
    # conservative "1 poll per minute" rhythm — friendly to PTT and plenty
    # for new-article detection latency in practice.
    poll_interval_high: float = 60.0
    poll_interval_normal: float = 60.0
    poll_interval_offpeak: float = 60.0
    pushsum_poll_interval: float = 60.0
    comment_poll_interval: float = 60.0
    pushsum_lookback_hours: int = 48
    recovery_max_days: int = 7
    dedup_ttl_seconds: int = 300

    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    log_dir: Path = field(default_factory=lambda: LOG_DIR)


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. "
            "Put it in .env or as an environment variable."
        )

    return Settings(
        discord_token=token,
        auth_user=os.environ.get("AUTH_USER", "admin"),
        auth_pw=os.environ.get("AUTH_PW", ""),
        web_host=os.environ.get("WEB_HOST", "127.0.0.1"),
        web_port=int(os.environ.get("WEB_PORT", "9090")),
        high_boards=_split_csv(os.environ.get("BOARD_HIGH")),
    )


def ensure_dirs(settings: Settings) -> None:
    (settings.data_dir / "users").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "boards").mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
