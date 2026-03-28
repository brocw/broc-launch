# loft — Design Document

**Type:** Linux desktop utility (system tray daemon + popup window)
**Status:** Draft v2 — Wayland-native MVP

---

## 1. Overview

`loft` is a lightweight Linux desktop utility that lets you fire off a web search or an LLM query without leaving your current window. A global hotkey summons a floating, keyboard-focused popup. You type your query and dispatch it with `Enter` (Google) or `Shift+Enter` (claude.ai). The popup disappears the moment you submit or dismiss it.

This document targets **Wayland exclusively**. There is no X11 fallback path and no XWayland dependency. All protocols and libraries are chosen for native Wayland operation.

### Goals

- **Zero friction.** No mouse movement, no alt-tab. One hotkey, type, dispatch.
- **Invisible when idle.** Lives silently in the system tray. No persistent window.
- **Keyboard-first.** The popup should feel like a terminal: fast, textual, no decoration.
- **Wayland-native.** Uses proper Wayland protocols from day one — no XWayland crutch.
- **Configurable.** LLM provider URL, hotkey, and browser are all user-defined.

### Non-Goals

- No search history UI (v1)
- No web scraping or inline results
- No X11 support

---

## 2. Feature Specification

### 2.1 Core Behavior

| Trigger | Action |
|---|---|
| Global hotkey (default: `Super+Space`) | Toggle popup window open/focused |
| `Enter` | Open query in browser → Google Search |
| `Shift+Enter` | Open query in browser → claude.ai (configurable) |
| `Escape` | Dismiss popup, return focus to previous window |
| Click outside popup | Dismiss popup |
| Tray icon left-click | Toggle popup |
| Tray icon right-click | Context menu: Show, Preferences, Quit |

### 2.2 Popup Window

- Single-line text input, auto-focused on open
- No window title bar (undecorated overlay surface)
- Fixed width (~560px), auto-height
- Centered on the active monitor
- Rendered above all other windows via layer-shell (`overlay` layer)
- Does **not** appear in the taskbar/window switcher
- Input cleared on every dismiss

### 2.3 URL Construction

```
Google:   https://www.google.com/search?q={encoded_query}
LLM:      https://claude.ai/new?q={encoded_query}   ← configurable base URL
```

Both open via `xdg-open`, which respects `$BROWSER` and portal-based browser launching on Wayland.

> **Note on `?q=` pre-fill for claude.ai:** This parameter is not officially documented. Test before relying on it. If it doesn't work, the fallback is: write query to clipboard via `wl-copy`, then `xdg-open https://claude.ai/new`. The user pastes manually, or the page reads the clipboard automatically.

---

## 3. Wayland Protocol Stack

This is the core technical foundation. Each piece of X11 magic the old approach relied on has a proper Wayland replacement.

### 3.1 Global Hotkeys — `xdg-desktop-portal` GlobalShortcuts

The [GlobalShortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html) (`org.freedesktop.portal.GlobalShortcuts`) is the sanctioned Wayland mechanism for registering global keyboard shortcuts. The compositor mediates the binding — no raw input grabbing.

**Flow:**
1. App calls `CreateSession` on the portal
2. App calls `BindShortcuts` with a list of requested bindings
3. Compositor shows a one-time permission dialog (first run only)
4. Portal emits `Activated` / `Deactivated` signals over D-Bus when the hotkey fires

**Portal backend requirements (one of):**
- `xdg-desktop-portal-hyprland` — for Hyprland
- `xdg-desktop-portal-wlr` — for wlroots compositors (Sway, etc.)
- `xdg-desktop-portal-gnome` — for GNOME
- `xdg-desktop-portal-kde` — for KDE Plasma

The app itself is compositor-agnostic; it only speaks to the portal D-Bus interface.

**Python binding:** `dbus-python` or `dasbus` for the D-Bus calls. The portal interaction is a handful of async D-Bus method calls — manageable without a dedicated library.

### 3.2 Popup Window — `wlr-layer-shell` via `gtk4-layer-shell`

[`zwlr_layer_shell_v1`](https://wayland.app/protocols/wlr-layer-shell-unstable-v1) is the Wayland protocol for surfaces that sit outside the normal window stack — used by bars, launchers, notification daemons, and lock screens. It is exactly what `loft` needs.

`gtk4-layer-shell` wraps this protocol for GTK4 windows, providing a clean Python-accessible API.

**Key properties set on the window:**

```python
GtkLayerShell.init_for_window(window)
GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, False)
# No anchoring = compositor centers the surface, or we position manually
```

- **Layer: `OVERLAY`** — renders above everything, including fullscreen windows
- **KeyboardMode: `EXCLUSIVE`** — the popup exclusively owns keyboard input while visible; this is how focus-grabbing works correctly on Wayland without `xdg_activation`
- **No taskbar entry** — layer-shell surfaces are never managed windows; they don't appear in window lists by definition

**Compositor support for `zwlr_layer_shell_v1`:**

| Compositor | Support |
|---|---|
| Hyprland | ✅ Full |
| Sway | ✅ Full |
| river | ✅ Full |
| KDE Plasma (KWin) | ✅ (5.27+) |
| GNOME (Mutter) | ⚠️ Partial — requires `gnome-shell-extension-layer-shell` or GNOME-specific approach |

### 3.3 System Tray — StatusNotifierItem (SNI)

The StatusNotifierItem protocol is the standard D-Bus-based system tray mechanism on Wayland. It is compositor/panel-independent.

**Library:** `libayatana-appindicator3` via `gi.repository.AyatanaAppIndicator3`

SNI is already a D-Bus protocol and works identically under Wayland. No X11 dependency.

**Requirement:** A tray host must be running. On most Wayland desktops this is provided by the panel (Waybar, sfwbar, KDE Plasma panel, GNOME with the AppIndicator extension, etc.).

### 3.4 Clipboard — `wl-clipboard`

For the claude.ai fallback (copying the query to clipboard):

```python
import subprocess
subprocess.run(["wl-copy", query], check=True)
```

`wl-copy` from the `wl-clipboard` package is the standard tool. No `xclip` or `xdotool` dependency.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        loft daemon                          │
│                                                             │
│  ┌──────────────────┐     ┌──────────────────────────────┐  │
│  │   Tray Icon      │     │   Hotkey Listener            │  │
│  │  (SNI / D-Bus)   │     │  (GlobalShortcuts portal     │  │
│  │  ayatana-        │     │   via D-Bus)                 │  │
│  │  appindicator    │     │                              │  │
│  └────────┬─────────┘     └──────────────┬───────────────┘  │
│           │                              │                  │
│           └──────────────┬───────────────┘                  │
│                          ▼                                  │
│                ┌─────────────────────┐                      │
│                │   Window Controller │                      │
│                │   (show/hide popup, │                      │
│                │    state machine)   │                      │
│                └──────────┬──────────┘                      │
│                           │                                 │
│                ┌──────────▼──────────┐                      │
│                │   Popup Window      │                      │
│                │   GTK4 + layer-shell│                      │
│                │   OVERLAY layer     │                      │
│                │   EXCLUSIVE kbd     │                      │
│                └──────────┬──────────┘                      │
│                           │                                 │
│                ┌──────────▼──────────┐                      │
│                │   URL Builder &     │                      │
│                │   Browser Launch    │                      │
│                │   (xdg-open)        │                      │
│                └─────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘

External D-Bus interfaces:
  org.freedesktop.portal.GlobalShortcuts  ← hotkeys
  org.kde.StatusNotifierItem              ← tray
  org.freedesktop.portal.OpenURI          ← browser launch (optional alt to xdg-open)
```

---

## 5. Recommended Tech Stack

| Concern | Choice | Package (Arch) |
|---|---|---|
| Language | Python 3.12+ | `python` |
| GUI | GTK4 via PyGObject | `python-gobject`, `gtk4` |
| Layer shell | `gtk4-layer-shell` | `gtk4-layer-shell` |
| Global hotkeys | D-Bus → GlobalShortcuts portal | `python-dbus` or `python-dasbus` |
| System tray | `libayatana-appindicator3` | `libayatana-appindicator`, `python-ayatana-appindicator` (AUR) |
| Config | TOML (`tomllib`, stdlib 3.11+) | — |
| Clipboard fallback | `wl-clipboard` CLI | `wl-clipboard` |
| Portal backend | compositor-provided | `xdg-desktop-portal-hyprland` or equivalent |

---

## 6. Configuration

```toml
# ~/.config/loft/config.toml

[hotkey]
# XKB syntax; passed to the GlobalShortcuts portal
binding     = "Super+space"
description = "Open loft search popup"

[search]
google_url = "https://www.google.com/search?q={query}"
llm_url    = "https://claude.ai/new?q={query}"

# Set to true if ?q= pre-fill doesn't work on your LLM provider
llm_clipboard_fallback = false

[browser]
# Empty = use xdg-open (recommended)
command = ""

[window]
width   = 560
monitor = "active"   # "active" (cursor's monitor) | "primary" | index

[theme]
# Path to a GTK CSS file; empty = use built-in default
css = ""
```

---

## 7. UI / UX Specification

### Popup Layout

```
╭─────────────────────────────────────────────────╮
│  🔍  ▏search or ask anything...                 │
╰─────────────────────────────────────────────────╯
      small hint: Enter → Google  ·  ⇧Enter → Claude
```

- Undecorated, floating, centered on active monitor
- Drop shadow for visual depth
- Icon on the left shifts: 🔍 (default) → ✦ when `Shift` is held
- Hint text beneath the input fades in 200ms after open

### GTK CSS (default theme)

```css
window {
  background: transparent;
}

.popup-frame {
  background-color: #1e1e2e;
  border: 1px solid #45475a;
  border-radius: 10px;
  padding: 10px 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.65);
}

entry {
  background: transparent;
  border: none;
  color: #cdd6f4;
  font-family: "JetBrains Mono", monospace;
  font-size: 14pt;
  caret-color: #89b4fa;
}

.hint {
  color: #585b70;
  font-size: 9pt;
  margin-top: 4px;
}
```

Default palette: Catppuccin Mocha. Swappable via `config.toml → theme.css`.

---

## 8. Startup, Permissions & Autostart

### First-Run Hotkey Registration

On first launch, the GlobalShortcuts portal will present a compositor-native dialog asking the user to confirm the shortcut binding. This is a one-time step — the binding is persisted by the portal and restored on subsequent launches automatically.

`loft` should display a brief notification on first run explaining this dialog is expected.

### Autostart

Ship a `.desktop` file for `~/.config/autostart/`:

```ini
[Desktop Entry]
Type=Application
Name=loft
Exec=/usr/bin/loft
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Quick search tray utility
```

Also document manual autostart for compositors that don't honor XDG autostart (e.g., `exec-once = loft` in `hyprland.conf`, or `exec loft` in `sway/config`).

### Required System Packages

```
gtk4
gtk4-layer-shell
libayatana-appindicator
xdg-desktop-portal
xdg-desktop-portal-<compositor>   # e.g. xdg-desktop-portal-hyprland
wl-clipboard
```

---

## 9. Project Structure

```
loft/
├── loft/
│   ├── __init__.py
│   ├── main.py           # Entry point, GLib main loop, startup
│   ├── tray.py           # SNI tray icon & context menu
│   ├── hotkey.py         # GlobalShortcuts portal D-Bus client
│   ├── popup.py          # GTK4 + gtk4-layer-shell popup window
│   ├── url_builder.py    # Query encoding, URL construction
│   ├── browser.py        # xdg-open / portal OpenURI launch
│   ├── clipboard.py      # wl-copy fallback
│   ├── config.py         # TOML config loading & validation
│   └── assets/
│       ├── loft.svg      # Tray icon (symbolic, works on all themes)
│       └── style.css     # Default GTK stylesheet
├── tests/
├── pyproject.toml
├── README.md
└── loft.desktop
```

---

## 10. Implementation Phases

### Phase 1 — Wayland MVP

- [ ] GTK4 popup window via `gtk4-layer-shell` (`OVERLAY` layer, `EXCLUSIVE` keyboard)
- [ ] `Enter` → Google search via `xdg-open`
- [ ] `Shift+Enter` → claude.ai via `xdg-open`
- [ ] `Escape` / focus-out → dismiss
- [ ] Global hotkey via `xdg-desktop-portal` GlobalShortcuts (D-Bus)
- [ ] System tray icon with Quit option (SNI)
- [ ] Hardcoded config defaults; no config file yet

### Phase 2 — Config & Polish

- [ ] TOML config file (`~/.config/loft/config.toml`)
- [ ] Configurable hotkey, LLM URL, browser override
- [ ] Monitor-aware centering (cursor position → monitor geometry)
- [ ] CSS theming, hint text, mode indicator icon shift on Shift-hold
- [ ] `wl-copy` clipboard fallback for LLM dispatch
- [ ] First-run notification for portal shortcut dialog

### Phase 3 — Quality of Life

- [ ] Query history (navigable with `↑` / `↓`, stored in `~/.local/share/loft/history`)
- [ ] Additional configurable dispatch targets (cycle with `Tab`)
- [ ] AUR `PKGBUILD`
- [ ] GNOME compatibility investigation

---

## 11. Open Questions

1. **GlobalShortcuts portal availability:** Older `xdg-desktop-portal-wlr` (pre-0.7) did not implement GlobalShortcuts. Hyprland's portal implements it fully. Add a runtime check with a clear error or tray notification if the interface is unavailable.

2. **Monitor detection under Wayland:** GTK4's `Gdk.Display` can enumerate monitors. Cursor monitor can be inferred via `Gdk.Display.get_monitor_at_surface()` after mapping, or from `Gdk.Seat` pointer position. Needs testing — may need a two-step: map offscreen, detect monitor, reposition.

3. **`?q=` pre-fill on claude.ai:** Unverified. Test before Phase 1 ships. If it doesn't work, make `wl-copy` clipboard fallback the default rather than opt-in.

4. **Hotkey conflict UX:** If the portal rejects the requested binding (already claimed), `loft` must handle this gracefully — surface a tray notification or stderr warning rather than silently failing.

5. **GNOME compatibility:** `zwlr_layer_shell_v1` is not supported by stock Mutter. If GNOME support is desired later, options are: (a) require the Layer Shell GNOME extension, (b) ship a GNOME Shell extension as the popup backend, or (c) fall back to a regular `GtkWindow` with `set_keep_above(True)` and accept imperfect behavior. Out of scope for v1.
