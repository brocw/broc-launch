"""
TOML configuration loader for broc-launch.

Config file: ~/.config/broc-launch/config.toml
All fields are optional; missing sections/keys fall back to defaults.
"""
import re
import tomllib
import urllib.parse
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


_VALID_MODIFIERS = frozenset({"Ctrl", "Alt", "Shift", "Super", "Meta", "Hyper"})
_KEY_RE = re.compile(r'^[A-Za-z0-9_]+$')

_WIDTH_MIN = 100
_WIDTH_MAX = 7680   # 8K horizontal


def _validate(cfg: Config) -> None:
    """Raise ValueError if any config value would cause runtime errors."""
    # --- hotkey.binding ---
    binding = cfg.hotkey.binding
    parts = binding.split("+")
    key = parts[-1]
    modifiers = parts[:-1]

    bad_mods = [m for m in modifiers if m not in _VALID_MODIFIERS]
    if bad_mods:
        raise ValueError(
            f"[hotkey] binding {binding!r}: unknown modifier(s) {bad_mods}; "
            f"valid modifiers: {sorted(_VALID_MODIFIERS)}"
        )
    if not key or not _KEY_RE.match(key):
        raise ValueError(
            f"[hotkey] binding {binding!r}: key name {key!r} must be non-empty "
            f"and contain only letters, digits, or underscores"
        )

    # --- search URLs ---
    for field, url in (
        ("search_url", cfg.search.search_url),
        ("llm_url",    cfg.search.llm_url),
    ):
        if "{query}" not in url:
            raise ValueError(
                f"[search] {field} {url!r}: must contain a {{query}} placeholder"
            )
        parsed = urllib.parse.urlparse(url.replace("{query}", "placeholder"))
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"[search] {field} {url!r}: scheme must be http or https, "
                f"got {parsed.scheme!r}"
            )
        if not parsed.netloc:
            raise ValueError(f"[search] {field} {url!r}: missing host")

    # --- window.width ---
    width = cfg.window.width
    if isinstance(width, bool) or not isinstance(width, int):
        raise ValueError(f"[window] width must be an integer, got {width!r}")
    if not (_WIDTH_MIN <= width <= _WIDTH_MAX):
        raise ValueError(
            f"[window] width {width} is out of range "
            f"({_WIDTH_MIN}–{_WIDTH_MAX})"
        )


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

    cfg = Config(
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
    _validate(cfg)
    return cfg
