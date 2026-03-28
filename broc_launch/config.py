"""
TOML configuration loader for broc-launch.

Config file: ~/.config/broc-launch/config.toml
All fields are optional; missing sections/keys fall back to defaults.
"""
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "broc-launch" / "config.toml"


@dataclass
class HotkeyConfig:
    binding: str = "Super+Shift+Return"


@dataclass
class SearchConfig:
    search_url: str = "https://www.google.com/search?q={query}"
    llm_url: str = "https://claude.ai/new?q={query}"
    search_name: str = "Google"
    llm_name: str = "Claude"


@dataclass
class WindowConfig:
    width: int = 700


@dataclass
class Config:
    hotkey: HotkeyConfig
    search: SearchConfig
    window: WindowConfig


_DEFAULT_TOML = """\
[hotkey]
binding = "Super+Shift+Return"

[search]
search_url  = "https://www.google.com/search?q={query}"
llm_url     = "https://claude.ai/new?q={query}"
search_name = "Google"
llm_name    = "Claude"

[window]
width = 700
"""


def write() -> None:
    """Write the default config.toml to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(_DEFAULT_TOML, encoding="utf-8")


def load() -> Config:
    """Load config from disk, falling back to defaults for any missing values."""
    raw: dict = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as f:
            raw = tomllib.load(f)
    else:
        write()
        raw = tomllib.loads(_DEFAULT_TOML)

    h = raw.get("hotkey", {})
    s = raw.get("search", {})
    w = raw.get("window", {})

    return Config(
        hotkey=HotkeyConfig(
            binding=h.get("binding", HotkeyConfig.binding),
        ),
        search=SearchConfig(
            search_url=s.get("search_url", SearchConfig.search_url),
            llm_url=s.get("llm_url", SearchConfig.llm_url),
            search_name=s.get("search_name", SearchConfig.search_name),
            llm_name=s.get("llm_name", SearchConfig.llm_name),
        ),
        window=WindowConfig(
            width=w.get("width", WindowConfig.width),
        ),
    )
