"""
Global hotkey via xdg-desktop-portal GlobalShortcuts.

Flow:
  1. CreateSession  → wait for Response → get session_handle
  2. BindShortcuts  → wait for Response → confirm registration
  3. Listen for Activated signals → call on_activate()

If the portal interface is unavailable (older portal, unsupported compositor)
a warning is printed and the app continues without a global hotkey.
"""
import uuid
import dbus

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH    = "/org/freedesktop/portal/desktop"
SHORTCUTS_IFACE = "org.freedesktop.portal.GlobalShortcuts"

SHORTCUT_ID      = "toggle-popup"
DEFAULT_TRIGGER  = "Super+Shift+Return"


def _token():
    return "broc_launch_" + uuid.uuid4().hex[:8]


class HotkeyManager:
    def __init__(self, bus, on_activate, trigger=DEFAULT_TRIGGER):
        self._bus         = bus
        self._on_activate = on_activate
        self._trigger     = trigger
        self._session_handle = None

        try:
            self._portal = bus.get_object(PORTAL_SERVICE, PORTAL_PATH)
            self._create_session()
        except dbus.DBusException as e:
            print(f"[broc-launch] GlobalShortcuts portal unavailable: {e}")

    # ------------------------------------------------------------------ #
    # Session creation                                                     #
    # ------------------------------------------------------------------ #

    def _create_session(self):
        handle_token  = _token()
        session_token = _token()

        options = dbus.Dictionary({
            "handle_token":         dbus.String(handle_token,  variant_level=1),
            "session_handle_token": dbus.String(session_token, variant_level=1),
        }, signature="sv")

        try:
            request_path = self._portal.CreateSession(
                options,
                dbus_interface=SHORTCUTS_IFACE,
            )
        except dbus.DBusException as e:
            print(f"[broc-launch] GlobalShortcuts not supported by this desktop, global hotkey unavailable: {e}")
            return

        req = self._bus.get_object(PORTAL_SERVICE, request_path)
        req.connect_to_signal("Response", self._on_create_session_response)

    def _on_create_session_response(self, response, results):
        if response != 0:
            print(f"[broc-launch] GlobalShortcuts CreateSession denied (response={response})")
            return

        self._session_handle = str(results["session_handle"])
        self._bind_shortcuts()

    # ------------------------------------------------------------------ #
    # Bind shortcuts                                                       #
    # ------------------------------------------------------------------ #

    def _bind_shortcuts(self):
        shortcuts = dbus.Array([
            dbus.Struct([
                dbus.String(SHORTCUT_ID),
                dbus.Dictionary({
                    "description":      dbus.String("Toggle broc-launch popup", variant_level=1),
                    "preferred-trigger": dbus.String(self._trigger,              variant_level=1),
                }, signature="sv"),
            ], signature=None),
        ], signature="(sa{sv})")

        handle_token = _token()
        options = dbus.Dictionary({
            "handle_token": dbus.String(handle_token, variant_level=1),
        }, signature="sv")

        try:
            request_path = self._portal.BindShortcuts(
                dbus.ObjectPath(self._session_handle),
                shortcuts,
                dbus.String(""),   # parent window handle (none)
                options,
                dbus_interface=SHORTCUTS_IFACE,
            )
        except dbus.DBusException as e:
            print(f"[broc-launch] GlobalShortcuts.BindShortcuts failed: {e}")
            return

        req = self._bus.get_object(PORTAL_SERVICE, request_path)
        req.connect_to_signal("Response", self._on_bind_response)

        # Start listening for Activated signals now (before bind completes).
        self._bus.add_signal_receiver(
            self._on_activated,
            signal_name="Activated",
            dbus_interface=SHORTCUTS_IFACE,
            bus_name=PORTAL_SERVICE,
            path=PORTAL_PATH,
        )

    def _on_bind_response(self, response, results):
        if response != 0:
            print(f"[broc-launch] GlobalShortcuts BindShortcuts denied (response={response})")
        else:
            print(f"[broc-launch] Global hotkey registered: {self._trigger}")

    # ------------------------------------------------------------------ #
    # Hotkey fired                                                         #
    # ------------------------------------------------------------------ #

    def rebind(self, trigger):
        """Update the preferred trigger and re-register with the portal."""
        if trigger == self._trigger or self._session_handle is None:
            return
        self._trigger = trigger
        self._bind_shortcuts()

    def _on_activated(self, session_handle, shortcut_id, timestamp, options):
        if (str(session_handle) == self._session_handle
                and str(shortcut_id) == SHORTCUT_ID):
            self._on_activate()


def setup_hotkey(on_activate, trigger=DEFAULT_TRIGGER):
    """Create a SessionBus connection and set up the HotkeyManager.

    Must be called after dbus.mainloop.glib.DBusGMainLoop has been set as
    the default (setup_tray does this).
    """
    try:
        bus = dbus.SessionBus()
    except dbus.DBusException as e:
        print(f"[broc-launch] Could not connect to session bus for hotkey: {e}")
        return None
    return HotkeyManager(bus, on_activate, trigger)
