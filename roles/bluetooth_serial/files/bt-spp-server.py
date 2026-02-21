#!/usr/bin/env python3
"""Bluetooth SPP (Serial Port Profile) server using BlueZ D-Bus API.

Registers an SPP profile and spawns getty for login terminal on connection.
"""

import os
import sys
import signal
import subprocess
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

BUS_NAME = "org.bluez"
AGENT_IFACE = "org.bluez.Agent1"
AGENT_MGR_IFACE = "org.bluez.AgentManager1"
PROFILE_IFACE = "org.bluez.Profile1"
PROFILE_MGR_IFACE = "org.bluez.ProfileManager1"
ADAPTER_IFACE = "org.bluez.Adapter1"

SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
AGENT_PATH = "/org/bluez/autologin_agent"
PROFILE_PATH = "/org/bluez/spp_profile"


class AutoAcceptAgent(dbus.service.Object):
    """Bluetooth agent that automatically accepts pairing requests."""

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        print(f"AuthorizeService: device={device} uuid={uuid}")

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print(f"RequestPinCode: device={device}")
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        print(f"RequestPasskey: device={device}")
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        print(f"DisplayPasskey: device={device} passkey={passkey:06d}")

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        print(f"DisplayPinCode: device={device} pincode={pincode}")

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print(f"RequestConfirmation: device={device} passkey={passkey:06d}")

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        print(f"RequestAuthorization: device={device}")

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        print("Agent cancelled")


class SppProfile(dbus.service.Object):
    """SPP profile that spawns getty on new connections."""

    fd = -1
    process = None

    @dbus.service.method(PROFILE_IFACE, in_signature="oha{sv}", out_signature="")
    def NewConnection(self, path, fd, properties):
        self.fd = fd.take()
        print(f"NewConnection: path={path} fd={self.fd}")
        self.process = subprocess.Popen(
            ["/sbin/agetty", "-L", "-a", "signage", "-", "115200", "vt100"],
            stdin=self.fd,
            stdout=self.fd,
            stderr=self.fd,
            preexec_fn=os.setsid,
        )
        print(f"Started agetty pid={self.process.pid}")

    @dbus.service.method(PROFILE_IFACE, in_signature="o", out_signature="")
    def RequestDisconnection(self, path):
        print(f"RequestDisconnection: path={path}")
        if self.process:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process = None
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    @dbus.service.method(PROFILE_IFACE, in_signature="", out_signature="")
    def Release(self):
        print("Profile released")


def find_adapter(bus):
    """Find the default Bluetooth adapter object path."""
    manager = dbus.Interface(
        bus.get_object(BUS_NAME, "/"), "org.freedesktop.DBus.ObjectManager"
    )
    for path, interfaces in manager.GetManagedObjects().items():
        if ADAPTER_IFACE in interfaces:
            return path
    return None


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter_path = find_adapter(bus)
    if not adapter_path:
        print("No Bluetooth adapter found", file=sys.stderr)
        sys.exit(1)

    adapter = dbus.Interface(
        bus.get_object(BUS_NAME, adapter_path),
        "org.freedesktop.DBus.Properties",
    )

    # Make adapter discoverable and pairable
    adapter.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
    adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
    adapter.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))

    # Register auto-accept agent
    agent = AutoAcceptAgent(bus, AGENT_PATH)
    agent_mgr = dbus.Interface(
        bus.get_object(BUS_NAME, "/org/bluez"), AGENT_MGR_IFACE
    )
    agent_mgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
    agent_mgr.RequestDefaultAgent(AGENT_PATH)
    print("Agent registered")

    # Register SPP profile
    profile = SppProfile(bus, PROFILE_PATH)
    profile_mgr = dbus.Interface(
        bus.get_object(BUS_NAME, "/org/bluez"), PROFILE_MGR_IFACE
    )
    opts = {
        "Name": "Serial Port",
        "Role": "server",
        "Channel": dbus.UInt16(1),
        "AutoConnect": dbus.Boolean(True),
    }
    profile_mgr.RegisterProfile(PROFILE_PATH, SPP_UUID, opts)
    print("SPP profile registered, waiting for connections...")

    loop = GLib.MainLoop()

    def sigterm_handler(signum, frame):
        loop.quit()

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    loop.run()


if __name__ == "__main__":
    main()
