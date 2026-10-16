"""Settings from environment / .env. Secrets never leave this module unredacted."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE, # comments). Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


SECRET_NAMES = (
    "X_BEARER_TOKEN", "BITQUERY_TOKEN", "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN",
    "REDDIT_CLIENT_SECRET", "SOLANA_RPC_URL", "DASHBOARD_TOKEN",
)


@dataclass
class Settings:
    db_path: Path
    solana_rpc_url: str
    x_bearer_token: str | None
    x_queries: list[str]
    bitquery_token: str | None
    anthropic_api_key: str | None
    analyst_model: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    reddit_client_id: str | None
    reddit_client_secret: str | None
    reddit_subreddits: list[str]
    dashboard_host: str
    dashboard_port: int
    dashboard_token: str | None
    # scheduler intervals (seconds); 0 disables a job
    intervals: dict[str, int] = field(default_factory=dict)
    report_times_utc: list[str] = field(default_factory=list)
    alert_score_delta: float = 15.0
    alert_cooldown_min: int = 120
    max_tracked_tokens: int = 600
    x_daily_read_budget: int = 1000
    x_max_results: int = 25

    def secret_values(self) -> list[str]:
        vals = [self.x_bearer_token, self.bitquery_token, self.anthropic_api_key,
                self.telegram_bot_token, self.reddit_client_secret, self.dashboard_token]
        # an RPC URL often embeds an API key in its path or query
        if self.solana_rpc_url and self.solana_rpc_url != DEFAULT_RPC:
            vals.append(self.solana_rpc_url)
        return [v for v in vals if v and len(v) >= 6]

    def redact(self, text: str) -> str:
        if not text:
            return text
        for v in self.secret_values():
            text = text.replace(v, "***")
        # api-key-looking query params, bot tokens in URLs
        text = re.sub(r"(api[-_]?key=)[^&\s]+", r"\1***", text, flags=re.I)
        text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", text)
        return text

    def public_view(self) -> dict:
        """What the API may show: which integrations are configured, never values."""
        return {
            "x_api": bool(self.x_bearer_token),
            "bitquery": bool(self.bitquery_token),
            "anthropic_analyst": bool(self.anthropic_api_key),
            "analyst_model": self.analyst_model if self.anthropic_api_key else None,
            "telegram": bool(self.telegram_bot_token and self.telegram_chat_id),
            "reddit_oauth": bool(self.reddit_client_id and self.reddit_client_secret),
            "solana_rpc": "public" if self.solana_rpc_url == DEFAULT_RPC else "custom",
            "x_queries": self.x_queries,
            "x_daily_read_budget": self.x_daily_read_budget,
            "reddit_subreddits": self.reddit_subreddits,
            "intervals_s": self.intervals,
            "report_times_utc": self.report_times_utc,
        }


DEFAULT_RPC = "https://api.mainnet-beta.solana.com"

DEFAULT_X_QUERIES = [
    "(pump.fun OR pumpfun) -is:retweet lang:en",
    "(memecoin OR \"meme coin\") solana -is:retweet lang:en",
    "(\"new meta\" OR narrative) (sol OR solana OR memecoin) -is:retweet",
]


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or ROOT / ".env")
    e = os.environ.get
    split = lambda s: [x.strip() for x in s.split("|") if x.strip()]  # noqa: E731
    return Settings(
        db_path=Path(e("RADAR_DB", str(ROOT / "data" / "radar.db"))),
        solana_rpc_url=e("SOLANA_RPC_URL") or DEFAULT_RPC,
        x_bearer_token=e("X_BEARER_TOKEN") or None,
        x_queries=split(e("X_QUERIES", "")) or DEFAULT_X_QUERIES,
        bitquery_token=e("BITQUERY_TOKEN") or None,
        anthropic_api_key=e("ANTHROPIC_API_KEY") or None,
        analyst_model=e("ANALYST_MODEL", "claude-opus-5-5"),
        telegram_bot_token=e("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=e("TELEGRAM_CHAT_ID") or None,
        reddit_client_id=e("REDDIT_CLIENT_ID") or None,
        reddit_client_secret=e("REDDIT_CLIENT_SECRET") or None,
        reddit_subreddits=split(e("REDDIT_SUBREDDITS", "solana|SolanaMemeCoins|memecoins|CryptoMoonShots")),
        dashboard_host=e("DASHBOARD_HOST", "127.0.0.1"),
        dashboard_port=_int("DASHBOARD_PORT", 8787),
        dashboard_token=e("DASHBOARD_TOKEN") or None,
        intervals={
            "launches": _int("EVERY_LAUNCHES_S", 180),     # GeckoTerminal new pools (9 calls)
            "active": _int("EVERY_ACTIVE_S", 300),         # pump-fun top pools (4 calls)
            "refresh": _int("EVERY_REFRESH_S", 300),       # tracked token stats (<=10 calls)
            "curves": _int("EVERY_CURVES_S", 300),         # bonding-curve state via RPC
            "attention": _int("EVERY_ATTENTION_S", 600),   # DexScreener boosts/profiles
            "macro": _int("EVERY_MACRO_S", 3600),          # DefiLlama launchpad volume
            "social": _int("EVERY_SOCIAL_S", 1800),        # X / Reddit (X is billed per post read)
            "analyze": _int("EVERY_ANALYZE_S", 600),       # metas + scores + alerts
            "outcomes": _int("EVERY_OUTCOMES_S", 1800),    # label matured tokens
        },
        report_times_utc=split(e("REPORT_TIMES_UTC", "08:00|20:00")),
        alert_score_delta=_float("ALERT_SCORE_DELTA", 15.0),
        alert_cooldown_min=_int("ALERT_COOLDOWN_MIN", 120),
        max_tracked_tokens=_int("MAX_TRACKED_TOKENS", 600),
        x_daily_read_budget=_int("X_DAILY_READ_BUDGET", 1000),
        x_max_results=_int("X_MAX_RESULTS", 25),
    )
