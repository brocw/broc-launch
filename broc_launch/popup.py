import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell
import subprocess
import urllib.parse
from pathlib import Path

CSS_PATH = Path(__file__).parent / "assets" / "style.css"

ICON_SEARCH = "🌐"
ICON_LLM = "🧠"


class PopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app)

        self._search_url = config.search.search_url
        self._llm_url = config.search.llm_url
        self._search_name = config.search.search_name
        self._llm_name = config.search.llm_name
        self._width = config.window.width

        self._shift_held = False

        self._setup_layer_shell()
        self._build_ui()
        self._apply_css()
        self._connect_signals()

    def _setup_layer_shell(self):
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
        # No anchoring — compositor centers the surface
        Gtk4LayerShell.set_namespace(self, "broc-launch")

        self.set_decorated(False)
        self.set_size_request(self._width, -1)
        self.set_resizable(False)

    def _build_ui(self):
        # Outer box fills the window; transparent background lets layer-shell
        # compositing show through so the frame's drop shadow is visible.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(outer)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("popup-frame")
        frame.set_hexpand(True)
        outer.append(frame)

        # Input row: icon + text entry
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        input_row.set_valign(Gtk.Align.CENTER)
        frame.append(input_row)

        self._icon = Gtk.Label(label=ICON_SEARCH)
        self._icon.add_css_class("mode-icon")
        self._icon.set_valign(Gtk.Align.CENTER)
        input_row.append(self._icon)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("search or ask anything...")
        self._entry.set_hexpand(True)
        self._entry.set_valign(Gtk.Align.CENTER)
        input_row.append(self._entry)

        # Hint text
        self._hint = Gtk.Label(label=f"Enter → {self._search_name}  ·  ⇧Enter → {self._llm_name}")
        self._hint.add_css_class("hint")
        self._hint.set_halign(Gtk.Align.START)
        frame.append(self._hint)

    def _apply_css(self):
        provider = Gtk.CssProvider()
        if CSS_PATH.exists():
            provider.load_from_path(str(CSS_PATH))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _connect_signals(self):
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        key_ctrl.connect("key-released", self._on_key_released)
        self.add_controller(key_ctrl)

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", self._on_focus_leave)
        self.add_controller(focus_ctrl)

    # --- keyboard ---

    def _on_key_pressed(self, ctrl, keyval, keycode, state):
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self._shift_held = True
            self._icon.set_label(ICON_LLM)
            return False

        if keyval == Gdk.KEY_Escape:
            self._dismiss()
            return True

        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            query = self._entry.get_text().strip()
            if query:
                if state & Gdk.ModifierType.SHIFT_MASK:
                    self._dispatch(self._llm_url, query)
                else:
                    self._dispatch(self._search_url, query)
            self._dismiss()
            return True

        return False

    def _on_key_released(self, ctrl, keyval, keycode, state):
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self._shift_held = False
            self._icon.set_label(ICON_SEARCH)

    # --- focus ---

    def _on_focus_leave(self, ctrl):
        self._dismiss()

    # --- actions ---

    def _dispatch(self, url_template, query):
        encoded = urllib.parse.quote_plus(query)
        url = url_template.replace("{query}", encoded)
        subprocess.Popen(["xdg-open", url])

    def _dismiss(self):
        self._entry.set_text("")
        self._icon.set_label(ICON_SEARCH)
        self._shift_held = False
        self.hide()

    def apply_config(self, cfg):
        self._search_url = cfg.search.search_url
        self._llm_url = cfg.search.llm_url
        self._search_name = cfg.search.search_name
        self._llm_name = cfg.search.llm_name
        self._width = cfg.window.width
        self.set_size_request(self._width, -1)
        self.queue_resize()
        self._hint.set_label(f"Enter → {self._search_name}  ·  ⇧Enter → {self._llm_name}")

    def present_popup(self):
        self.present()
        self._entry.grab_focus()

    def toggle(self):
        if self.get_visible():
            self._dismiss()
        else:
            self.present_popup()
