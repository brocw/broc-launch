"""
StatusNotifierItem (SNI) tray icon implemented directly over D-Bus.
Avoids the GTK3/GTK4 version conflict that AyatanaAppIndicator3 would cause.

Right-click context menu uses com.canonical.dbusmenu so KDE Plasma renders
it natively instead of spawning a separate GTK/Wayland window.
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
DBUSMENU_IFACE = "com.canonical.dbusmenu"

ICON_PATH = str(Path(__file__).parent / "assets" / "broc-launch.svg")
MENU_PATH = "/StatusNotifierItem/Menu"

# Menu item IDs
_ID_HEADER = 1
_ID_SEP    = 2
_ID_QUIT   = 3


class DBusMenu(dbus.service.Object):
    """Minimal com.canonical.dbusmenu implementation for the tray context menu.

    Menu structure:
      broc-launch  (disabled label)
      ─────────────
      Quit
    """

    def __init__(self, bus_name, on_quit):
        super().__init__(bus_name, MENU_PATH)
        self._on_quit = on_quit
        self._revision = 1

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _item(id, props):
        """Return a menu item tuple (id, props_dict, children_array)."""
        return (
            dbus.Int32(id),
            dbus.Dictionary(props, signature="sv"),
            dbus.Array([], signature="v"),
        )

    def _layout(self):
        """Return the full menu tree as required by GetLayout."""
        children = dbus.Array([
            dbus.Struct(
                self._item(_ID_HEADER, {
                    "label":   dbus.String("broc-launch", variant_level=1),
                    "enabled": dbus.Boolean(False, variant_level=1),
                }),
                signature=None,
                variant_level=1,
            ),
            dbus.Struct(
                self._item(_ID_SEP, {
                    "type": dbus.String("separator", variant_level=1),
                }),
                signature=None,
                variant_level=1,
            ),
            dbus.Struct(
                self._item(_ID_QUIT, {
                    "label": dbus.String("Quit", variant_level=1),
                }),
                signature=None,
                variant_level=1,
            ),
        ], signature="v")

        root = (
            dbus.Int32(0),
            dbus.Dictionary({}, signature="sv"),
            children,
        )
        return root

    # ------------------------------------------------------------------ #
    # com.canonical.dbusmenu methods                                      #
    # ------------------------------------------------------------------ #

    @dbus.service.method(DBUSMENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)")
    def GetLayout(self, parent_id, recursion_depth, property_names):
        return (dbus.UInt32(self._revision), self._layout())

    @dbus.service.method(DBUSMENU_IFACE, in_signature="aias", out_signature="a(ia{sv})")
    def GetGroupProperties(self, ids, property_names):
        return dbus.Array([], signature="(ia{sv})")

    @dbus.service.method(DBUSMENU_IFACE, in_signature="isvu")
    def Event(self, id, event_id, data, timestamp):
        if event_id == "clicked" and int(id) == _ID_QUIT:
            self._on_quit()

    @dbus.service.method(DBUSMENU_IFACE, in_signature="a(isvu)", out_signature="ai")
    def EventGroup(self, events):
        for id, event_id, data, timestamp in events:
            self.Event(id, event_id, data, timestamp)
        return dbus.Array([], signature="i")

    @dbus.service.method(DBUSMENU_IFACE, in_signature="i", out_signature="b")
    def AboutToShow(self, id):
        return dbus.Boolean(False)

    @dbus.service.method(DBUSMENU_IFACE, in_signature="ai", out_signature="aiai")
    def AboutToShowGroup(self, ids):
        return (dbus.Array([], signature="i"), dbus.Array([], signature="i"))

    # ------------------------------------------------------------------ #
    # com.canonical.dbusmenu signals                                      #
    # ------------------------------------------------------------------ #

    @dbus.service.signal(DBUSMENU_IFACE, signature="ui")
    def LayoutUpdated(self, revision, parent): pass

    @dbus.service.signal(DBUSMENU_IFACE, signature="a(ia{sv})a(ias)")
    def ItemsPropertiesUpdated(self, updated_props, removed_props): pass


def _load_icon_pixmap(path, size=22):
    """Rasterise the SVG and return SNI IconPixmap data: [(width, height, ARGB32 bytes)]."""
    try:
        from gi.repository import GdkPixbuf
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
        pixels = bytearray(pixbuf.get_pixels())
        n = pixbuf.get_n_channels()
        w, h = pixbuf.get_width(), pixbuf.get_height()
        argb = bytearray(w * h * 4)
        for i in range(w * h):
            argb[i*4 + 0] = pixels[i*n + 3] if n == 4 else 255  # A
            argb[i*4 + 1] = pixels[i*n + 0]                      # R
            argb[i*4 + 2] = pixels[i*n + 1]                      # G
            argb[i*4 + 3] = pixels[i*n + 2]                      # B
        return [(dbus.Int32(w), dbus.Int32(h), dbus.Array(argb, signature="y"))]
    except Exception as e:
        print(f"[broc-launch] Could not load icon pixmap: {e}")
        return []


class StatusNotifierItem(dbus.service.Object):
    def __init__(self, bus, app, on_activate, on_quit):
        self._app = app
        self._on_activate = on_activate
        self._on_quit = on_quit
        self._icon_pixmap = _load_icon_pixmap(ICON_PATH)

        service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        bus_name = dbus.service.BusName(service_name, bus)
        super().__init__(bus_name, "/StatusNotifierItem")

        # Create the dbusmenu object on the same bus name so KDE can reach it.
        self._menu = DBusMenu(bus_name, on_quit)

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
            "IconName":     dbus.String("search"),  # freedesktop fallback
            "IconThemePath":dbus.String(""),
            "IconPixmap":   dbus.Array(self._icon_pixmap, signature="(iiay)"),
            "Menu":         dbus.ObjectPath(MENU_PATH),
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
        # KDE Plasma renders the menu natively via dbusmenu (Menu property).
        # This method is intentionally a no-op.
        pass

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
