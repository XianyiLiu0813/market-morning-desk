"""Central configuration loader.

Loads config/settings.yaml (+ themes/watchlist/assets/sources) and overlays
environment variables. This is the single place the rest of the codebase
reads configuration from - nothing else should call `yaml.safe_load` on its
own, so the app stays code-free to reconfigure.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required config file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    raw: Dict[str, Any]
    themes_raw: Dict[str, Any]
    watchlist_raw: Dict[str, Any]
    assets_raw: Dict[str, Any]
    sources_raw: Dict[str, Any]

    timezone: str = "Asia/Singapore"
    email_time: str = "07:45"
    top_news: int = 5
    macro_stories: int = 3
    company_radar: int = 5
    trade_ideas_max: int = 3
    terminology_terms: int = 5
    educational_mode: bool = True
    yesterday_review: bool = True
    mock_mode: bool = True
    min_story_score: float = 1.5
    scoring_weights: Dict[str, float] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    llm_provider: str = "mock"
    llm_model: str = "claude-sonnet-5"
    llm_max_output_tokens: int = 4096
    llm_temperature: float = 0.2
    email_provider: str = "mock"
    email_subject_prefix: str = "AI Market Morning Desk"
    db_path: str = "data/market_morning_desk.db"
    log_level: str = "INFO"
    log_dir: str = "logs"

    @property
    def themes(self) -> List[Dict[str, Any]]:
        return self.themes_raw.get("themes", [])

    @property
    def watchlist(self) -> Dict[str, Any]:
        return self.watchlist_raw.get("watchlist", {})

    @property
    def asset_groups(self) -> List[Dict[str, Any]]:
        return self.assets_raw.get("groups", [])

    @property
    def source_tiers(self) -> Dict[int, Any]:
        return self.sources_raw.get("tiers", {})

    def validate(self) -> List[str]:
        """Return a list of human-readable warnings (non-fatal issues)."""
        warnings: List[str] = []
        total_weight = sum(self.scoring_weights.values()) if self.scoring_weights else 0.0
        if self.scoring_weights and abs(total_weight - 1.0) > 0.01:
            warnings.append(
                f"scoring_weights in settings.yaml sum to {total_weight:.3f}, expected 1.0 "
                "(scores will be normalized at runtime)."
            )
        if self.trade_ideas_max > 3:
            warnings.append(
                "trade_ideas_max > 3 violates Principle 5 (max 3 trade setups); clamping to 3."
            )
            self.trade_ideas_max = 3
        return warnings


def load_settings() -> Settings:
    raw = _load_yaml("settings.yaml")
    themes_raw = _load_yaml("themes.yaml")
    watchlist_raw = _load_yaml("watchlist.yaml")
    assets_raw = _load_yaml("assets.yaml")
    sources_raw = _load_yaml("sources.yaml")

    sched = raw.get("email_time", "07:45")
    weights = raw.get("scoring_weights", {}) or {}
    quality = raw.get("quality", {}) or {}
    llm_cfg = raw.get("llm", {}) or {}
    email_cfg = raw.get("email", {}) or {}
    db_cfg = raw.get("database", {}) or {}
    log_cfg = raw.get("logging", {}) or {}

    settings = Settings(
        raw=raw,
        themes_raw=themes_raw,
        watchlist_raw=watchlist_raw,
        assets_raw=assets_raw,
        sources_raw=sources_raw,
        timezone=raw.get("timezone", "Asia/Singapore"),
        email_time=sched,
        top_news=int(raw.get("top_news", 5)),
        macro_stories=int(raw.get("macro_stories", 3)),
        company_radar=int(raw.get("company_radar", 5)),
        trade_ideas_max=int(raw.get("trade_ideas_max", 3)),
        terminology_terms=int(raw.get("terminology_terms", 5)),
        educational_mode=bool(raw.get("educational_mode", True)),
        yesterday_review=bool(raw.get("yesterday_review", True)),
        mock_mode=_env_bool("MOCK_MODE", bool(raw.get("mock_mode", True))),
        min_story_score=float(raw.get("min_story_score", 1.5)),
        scoring_weights=weights,
        quality=quality,
        llm_provider=os.environ.get("LLM_PROVIDER", llm_cfg.get("provider", "mock")),
        llm_model=os.environ.get("LLM_MODEL", llm_cfg.get("model", "claude-sonnet-5")),
        llm_max_output_tokens=int(llm_cfg.get("max_output_tokens", 4096)),
        llm_temperature=float(llm_cfg.get("temperature", 0.2)),
        email_provider=os.environ.get("EMAIL_PROVIDER", email_cfg.get("provider", "mock")),
        email_subject_prefix=email_cfg.get("subject_prefix", "AI Market Morning Desk"),
        db_path=os.environ.get("DATABASE_PATH", db_cfg.get("path", "data/market_morning_desk.db")),
        log_level=os.environ.get("LOG_LEVEL", log_cfg.get("level", "INFO")),
        log_dir=log_cfg.get("dir", "logs"),
    )
    return settings


_settings_singleton: Optional[Settings] = None


def get_settings(force_reload: bool = False) -> Settings:
    global _settings_singleton
    if _settings_singleton is None or force_reload:
        _settings_singleton = load_settings()
    return _settings_singleton
