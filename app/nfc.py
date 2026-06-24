"""
Tesla NFC Card Reader — USB NFC reader for Orange Pi
=====================================================
Works with PN532 USB / ACR122U / RC522+USB adapters.
When a registered card is tapped → send CAN command.

Usage:
  python3 nfc.py                    # Foreground daemon
  python3 nfc.py --dump             # Read card UIDs only
  python3 nfc.py --register         # Register next scanned card
"""

import json, os, time, subprocess, sys, logging, requests
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [NFC] %(message)s")
log = logging.getLogger("nfc")

# Paths
CARDS_FILE = Path("/opt/tesla-control/data/nfc_cards.json")
API_URL = os.environ.get("TESLA_API", "http://localhost:5000/api")

# Ensure data dir
CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Card Database ──
def load_cards() -> list:
    try:
        return json.loads(CARDS_FILE.read_text()) if CARDS_FILE.exists() else []
    except:
        return []

def save_cards(cards: list):
    CARDS_FILE.write_text(json.dumps(cards, indent=2))

def add_card(uid: str, action: str = "unlock"):
    cards = load_cards()
    if any(c["uid"] == uid for c in cards):
        log.warning(f"Card {uid} already registered")
        return False
    cards.append({"uid": uid.upper(), "action": action, "name": f"Card {len(cards)+1}"})
    save_cards(cards)
    log.info(f"✅ Registered card {uid} → {action}")
    return True

# ── NFC Reader ──
class NFCReader:
    """Abstract NFC reader base class. Add reader-specific backends below."""

    def detect(self) -> bool:
        """Return True if reader hardware is present."""
        raise NotImplementedError

    def read_uid(self, timeout: float = 5.0) -> str | None:
        """Block until a card is detected, return UID string. None on timeout."""
        raise NotImplementedError

    def read_uid_loop(self, callback, poll_interval: float = 0.5):
        """Continuous read loop."""
        log.info("NFC reader started. Waiting for cards...")
        while True:
            uid = self.read_uid(timeout=1.0)
            if uid:
                callback(uid)
            time.sleep(poll_interval)


class PN532USB(NFCReader):
    """PN532 USB reader via libnfc / nfc-poll CLI."""

    def detect(self) -> bool:
        r = subprocess.run(["nfc-list"], capture_output=True, text=True, timeout=5)
        return "NFC device" in r.stdout or "PN532" in r.stdout

    def read_uid(self, timeout: float = 5.0) -> str | None:
        r = subprocess.run(
            ["nfc-poll"], capture_output=True, text=True, timeout=timeout + 1
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.split("\n"):
            if "UID" in line:
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    uid = parts[-1].strip().replace(" ", "").upper()
                    return uid
        return None


class ACR122U(NFCReader):
    """ACR122U via PCSC/pyscard. Requires 'pip install pyscard' + pcscd service."""

    def detect(self) -> bool:
        if os.system("which pcscd > /dev/null 2>&1") != 0:
            return False
        try:
            from smartcard.System import readers
            return len(readers()) > 0
        except:
            return False

    def read_uid(self, timeout: float = 5.0) -> str | None:
        try:
            from smartcard.System import readers
            from smartcard.CardConnectionObserver import CardConnectionObserver
            from smartcard.util import toHexString
            r = readers()
            if not r:
                return None
            conn = r[0].createConnection()
            conn.connect()
            data = conn.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])[0]
            if data and len(data) >= 2:
                uid_hex = "".join(f"{b:02X}" for b in data)
                return uid_hex
        except:
            pass
        return None


# ── Action Dispatch ──
def dispatch(uid: str, cards: list):
    """Find card and execute action."""
    card = next((c for c in cards if c["uid"] == uid.upper()), None)
    if not card:
        log.warning(f"Unknown card: {uid}")
        return False

    action = card["action"]
    log.info(f"💳 Card {uid} → {action}")

    try:
        r = requests.post(f"{API_URL}/{action}", timeout=5)
        if r.ok:
            log.info(f"✅ {action} success")
            return True
        else:
            log.warning(f"❌ {action} failed: {r.status_code}")
    except Exception as e:
        log.error(f"❌ {action} error: {e}")
    return False


# ── Main ──
def main():
    # Detect available reader
    readers_list = [PN532USB(), ACR122U()]
    reader = None
    for r in readers_list:
        if r.detect():
            reader = r
            log.info(f"🔍 Found reader: {type(r).__name__}")
            break

    if not reader:
        log.warning("No NFC reader detected. Available options:")
        log.warning("  USB PN532 — install libnfc-bin: sudo apt install libnfc-bin")
        log.warning("  ACR122U — install pcscd + pyscard: sudo apt install pcscd && pip install pyscard")
        log.warning("  RC522 SPI — not yet supported via this daemon")
        sys.exit(1)

    # Handle command-line flags
    if "--dump" in sys.argv:
        log.info("Dump mode: tap a card to read its UID")
        while True:
            uid = reader.read_uid(timeout=2.0)
            if uid:
                print(f"UID: {uid}")
    elif "--register" in sys.argv:
        log.info("Register mode: tap a card to add it")
        while True:
            uid = reader.read_uid(timeout=2.0)
            if uid:
                print(f"Scanned UID: {uid}")
                action = input("Action [unlock]: ").strip() or "unlock"
                add_card(uid, action)
    else:
        # Daemon mode
        cards = load_cards()
        log.info(f"Loaded {len(cards)} authorized card(s)")
        if not cards:
            log.warning("No cards registered. Use --register to add cards.")
        reader.read_uid_loop(lambda uid: dispatch(uid, load_cards()))


if __name__ == "__main__":
    main()
