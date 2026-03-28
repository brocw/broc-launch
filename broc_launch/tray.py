"""
StatusNotifierItem (SNI) tray icon implemented directly over D-Bus.
Avoids the GTK3/GTK4 version conflict that AyatanaAppIndicator3 would cause.
"""
import os
import dbus
import dbus.service
import dbus.mainloop.glib
from pathlib import Path

SNI_IFACE = "org.kde.StatusNotifierItem"
WATCHER_SERVICE = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_IFACE = "org.kde.StatusNotifierWatcher"

ICON_PATH = str(Path(__file__).parent / "assets" / "broc-launch.svg")


class StatusNotifierItem(dbus.service.Object):
    def __init__(self, bus, app, on_activate, on_quit):
        self._app = app
        self._on_activate = on_activate
        self._on_quit = on_quit

        service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        bus_name = dbus.service.BusName(service_name, bus)
        super().__init__(bus_name, "/StatusNotifierItem")

        self._register_with_watcher(bus, service_name)

    def _register_with_watcher(self, bus, service_name):
        try:
            watcher = bus.get_object(WATCHER_SERVICE, WATCHER_PATH)
            watcher.RegisterStatusNotifierItem(
                service_name,
                dbus_interface=WATCHER_IFACE,
            )
        except dbus.DBusException as e:
            print(f"[broc-launch] Could not register with StatusNotifierWatcher: {e}")

    # --- SNI properties (read via standard D-Bus Properties interface) ---

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self._props().get(prop, "")

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return self._props()

    def _props(self):
        return {
            "Category":     dbus.String("ApplicationStatus"),
            "Id":           dbus.String("broc-launch"),
            "Title":        dbus.String("broc-launch"),
            "Status":       dbus.String("Active"),
            "IconName":     dbus.String("search"),  # freedesktop icon name
            "IconThemePath":dbus.String(""),
            "Menu":         dbus.ObjectPath("/NO_DBUSMENU"),
            "ItemIsMenu":   dbus.Boolean(False),
            "ToolTip":      dbus.Struct(
                ("", dbus.Array([], signature="(iiay)"), "broc-launch", "Quick search popup"),
                signature=None,
            ),
        }

    # --- SNI methods ---

    @dbus.service.method(SNI_IFACE, in_signature="ii")
    def Activate(self, x, y):
        """Left-click: toggle popup."""
        self._on_activate()

    @dbus.service.method(SNI_IFACE, in_signature="ii")
    def SecondaryActivate(self, x, y):
        pass

    @dbus.service.method(SNI_IFACE, in_signature="i")
    def Scroll(self, delta):
        pass

    @dbus.service.method(SNI_IFACE, in_signature="ii")
    def ContextMenu(self, x, y):
        """Right-click: show a minimal native menu via GTK4."""
        self._show_context_menu()

    def _show_context_menu(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk

        win = Gtk.ApplicationWindow(application=self._app)
        win.set_decorated(False)
        win.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        # Disabled header label
        header = Gtk.Label(label="broc-launch")
        header.set_sensitive(False)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(4)
        header.set_margin_bottom(4)
        header.set_halign(Gtk.Align.START)
        box.append(header)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.append(sep)

        quit_btn = Gtk.Button(label="Quit")
        quit_btn.set_has_frame(False)
        quit_btn.set_margin_start(4)
        quit_btn.set_margin_end(4)
        quit_btn.set_margin_top(2)
        quit_btn.set_margin_bottom(2)
        quit_btn.connect("clicked", lambda _: (win.close(), self._on_quit()))
        box.append(quit_btn)

        win.set_child(box)

        # Close when focus is lost
        win.connect("notify::is-active", lambda w, _: w.close() if not w.props.is_active else None)

        win.present()

    # --- SNI signals ---

    @dbus.service.signal(SNI_IFACE)
    def NewTitle(self): pass

    @dbus.service.signal(SNI_IFACE)
    def NewIcon(self): pass

    @dbus.service.signal(SNI_IFACE)
    def NewStatus(self, status): pass


def setup_tray(app, on_activate, on_quit):
    """Initialise the D-Bus main loop integration and create the tray item."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    return StatusNotifierItem(bus, app, on_activate, on_quit)
