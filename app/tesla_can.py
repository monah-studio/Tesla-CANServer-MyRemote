"""
Tesla Local Control — CAN Bus Driver for 2015 Model S 85D
==========================================================
Communicates with Body CAN (BCAN) at 125 kbps via OBD-II port.
Handles: door lock/unlock, frunk, trunk, windows, flash, honk.

CAN IDs for pre-2021 Model S (community-reversed):
  0x216  → Door lock
  0x217  → Frunk
  0x218  → Trunk
  0x215  → Windows
  0x244  → Lights
  0x245  → Horn
"""

import can
import logging
import time
import threading
from typing import Optional

log = logging.getLogger("tesla_can")

# ── CAN Configuration ────────────────────────────────────────────────
CAN_INTERFACE = "socketcan"
CAN_CHANNEL   = "can0"
CAN_BITRATE   = 125000  # Body CAN

# ── CAN IDs for Model S (pre-2021 Body CAN) ──────────────────────────
# ⚠️ These are community-documented. Your car may differ.
#    Use the CAN Sniffer tool to verify: python3 tools/can_sniffer.py
CAN_ID_DOOR_LOCK   = 0x216
CAN_ID_FRONT_TRUNK = 0x217
CAN_ID_REAR_TRUNK  = 0x218
CAN_ID_LIGHTS      = 0x244
CAN_ID_HORN        = 0x245
CAN_ID_WINDOWS     = 0x215

# ── Command Payloads ──────────────────────────────────────────────────
# These are the most common bytes for Model S Body CAN.
# Byte 0 usually controls the command type.
CMD_LOCK   = bytes([0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01])
CMD_UNLOCK = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_FRUNK  = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_TRUNK  = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_LIGHTS = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])  # flash
CMD_LIGHTS_OFF = bytes([0x00] * 8)
CMD_HORN   = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_WINDOW_CLOSE = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_WINDOW_VENT  = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])


class TeslaCANDriver:
    """CAN bus driver for 2015 Tesla Model S.""" 

    def __init__(self):
        self._bus: Optional[can.BusABC] = None
        self._lock = threading.Lock()
        self._status = {"connected": False}
        self._running = False
        self._listener: Optional[threading.Thread] = None

    # ── Bus Lifecycle ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Open CAN bus connection."""
        try:
            self._bus = can.interface.Bus(
                channel=CAN_CHANNEL,
                bustype=CAN_INTERFACE,
                bitrate=CAN_BITRATE,
            )
            self._running = True
            self._status["connected"] = True
            log.info(f"✅ CAN connected: {CAN_CHANNEL} @ {CAN_BITRATE}")
            # Start background listener
            self._listener = threading.Thread(target=self._listen, daemon=True)
            self._listener.start()
            return True
        except Exception as e:
            log.error(f"❌ CAN connect failed: {e}")
            log.error("   Check: sudo ip link set can0 up type can bitrate 125000")
            self._status["connected"] = False
            return False

    def disconnect(self):
        self._running = False
        if self._bus:
            self._bus.shutdown()
            self._bus = None
        self._status["connected"] = False

    @property
    def is_connected(self) -> bool:
        return self._bus is not None and self._status.get("connected", False)

    # ── Background Listener ──────────────────────────────────────────

    def _listen(self):
        """Listen for status messages from the car."""
        known_status_ids = {
            0x102: "drive_mode",
            0x202: "battery_soc",
            0x212: "speed",
            0x222: "gear",
        }
        while self._running and self._bus:
            try:
                msg = self._bus.recv(timeout=0.3)
                if msg and msg.arbitration_id in known_status_ids:
                    with self._lock:
                        self._status[known_status_ids[msg.arbitration_id]] = msg.data
            except Exception:
                if self._running:
                    time.sleep(0.5)

    def get_status(self) -> dict:
        """Return current known vehicle status."""
        with self._lock:
            soc = self._status.get("battery_soc", b'')
            return {
                "connected": self.is_connected,
                "battery_soc": soc[0] if len(soc) >= 1 else None,
            }

    # ── Send CAN Frame ───────────────────────────────────────────────

    def _send(self, can_id: int, data: bytes) -> bool:
        """Send a CAN frame. Returns True on success."""
        if not self._bus:
            log.warning("CAN bus not connected")
            return False
        msg = can.Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=False,
        )
        try:
            with self._lock:
                self._bus.send(msg)
            log.info(f"TX: {hex(can_id)} [{len(data)}] {data.hex()}")
            return True
        except Exception as e:
            log.error(f"CAN send error: {e}")
            return False

    # ── High-Level Commands ──────────────────────────────────────────

    def lock(self) -> dict:
        ok = self._send(CAN_ID_DOOR_LOCK, CMD_LOCK)
        return {"success": ok, "command": "lock"}

    def unlock(self) -> dict:
        ok = self._send(CAN_ID_DOOR_LOCK, CMD_UNLOCK)
        return {"success": ok, "command": "unlock"}

    def frunk(self) -> dict:
        ok = self._send(CAN_ID_FRONT_TRUNK, CMD_FRUNK)
        return {"success": ok, "command": "frunk"}

    def trunk(self) -> dict:
        ok = self._send(CAN_ID_REAR_TRUNK, CMD_TRUNK)
        return {"success": ok, "command": "trunk"}

    def flash_lights(self) -> dict:
        ok1 = self._send(CAN_ID_LIGHTS, CMD_LIGHTS)
        time.sleep(0.3)
        ok2 = self._send(CAN_ID_LIGHTS, CMD_LIGHTS_OFF)
        return {"success": ok1 and ok2, "command": "flash"}

    def honk(self) -> dict:
        ok = self._send(CAN_ID_HORN, CMD_HORN)
        return {"success": ok, "command": "honk"}

    def windows_vent(self) -> dict:
        ok = self._send(CAN_ID_WINDOWS, CMD_WINDOW_VENT)
        return {"success": ok, "command": "windows_vent"}

    def windows_close(self) -> dict:
        ok = self._send(CAN_ID_WINDOWS, CMD_WINDOW_CLOSE)
        return {"success": ok, "command": "windows_close"}
