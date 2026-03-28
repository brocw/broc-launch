import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio

from .popup import PopupWindow
from .tray import setup_tray


class LoftApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.broc_launch")
        self._popup = None
        self._tray = None

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)

    def do_activate(self):
        if self._popup is None:
            self._popup = PopupWindow(self)
            self._tray = setup_tray(
                app=self,
                on_activate=self._popup.toggle,
                on_quit=self.quit,
            )
        self._popup.present_popup()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # Keep the app alive even when the popup is hidden.
        self.hold()


def main():
    app = LoftApp()
    app.run()


if __name__ == "__main__":
    main()
