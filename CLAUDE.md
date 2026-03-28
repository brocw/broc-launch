# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`broc-launch` (internally "loft") is a Wayland-native Linux desktop utility — a system tray daemon that presents a keyboard-driven popup for quick Google searches and Claude.ai queries. It requires gtk4-layer-shell to float above all windows as an OVERLAY layer.

## Running

```bash
pip install -e --break-system-packages .       # install in editable mode
broc-launch            # launch (runs as background daemon)
python -m broc_launch.main  # alternative
```

No build step, no tests, no linter configured.

## Architecture

Three main components, all wired together in `LoftApp` (main.py):

| File | Role |
|------|------|
| `main.py` | `LoftApp(Gtk.Application)` — lifecycle, holds the event loop alive via `hold()` |
| `popup.py` | `PopupWindow` — GTK4 layer-shell overlay window with text entry and keyboard dispatch |
| `tray.py` | `StatusNotifierItem` — raw D-Bus implementation of the SNI tray protocol |

**Popup behavior:** The window sits on the OVERLAY layer with EXCLUSIVE keyboard mode (captures all input while visible). Enter opens Google, Shift+Enter opens Claude.ai. Escape or focus-loss hides it. The tray icon toggles it.

**Tray:** Implemented directly against `org.kde.StatusNotifierItem` D-Bus interface (no GTK StatusIcon, to avoid GTK3/4 version conflicts). Left-click toggles the popup; right-click shows a Quit menu.

**URL dispatch:** `_dispatch()` in popup.py uses `urllib.parse.quote_plus` then calls `xdg-open` via subprocess.

## Design Document

`DESIGN.md` is the authoritative spec — covers planned phases (global hotkey via xdg-desktop-portal, config file, query history) that are not yet implemented.

## Key Constraints

- **Wayland only** — gtk4-layer-shell has no X11 equivalent; don't add X11 fallbacks.
- **Python ≥ 3.12**, GTK4, `dbus-python`, `gtk4-layer-shell` must be installed system-wide (not pip-installable).
- The app uses `GLib.MainLoop` integration via `dbus.mainloop.glib.DBusGMainLoop` — keep D-Bus callbacks on the GLib main loop.
