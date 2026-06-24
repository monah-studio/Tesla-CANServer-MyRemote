"""
Tesla Local Control — REST API (CAN version for 2015 Model S 85D)
==================================================================
Flask backend + Tesla model database + VIN decoder
"""

import subprocess
import logging
import os
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from app.tesla_can import TeslaCANDriver
from app.tesla_models import TESLA_MODELS, TESLA_COLORS, decode_vin
from app.tesla_models import WHEEL_SIZES, MCU_TYPES, INTERIOR_COLORS, BODY_STYLES

# ── Config from environment ──────────────────────────────────────────
HOST      = os.environ.get("TESLA_HOST", "0.0.0.0")
PORT      = int(os.environ.get("TESLA_PORT", "5000"))
DEBUG     = os.environ.get("TESLA_DEBUG", "").lower() in ("1", "true")
API_TOKEN = os.environ.get("TESLA_API_TOKEN", "")

# ── Init ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("tesla_api")

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

can = TeslaCANDriver()
_can_initialized = False

def ensure_can():
    global _can_initialized
    if not _can_initialized:
        if can.connect():
            _can_initialized = True

# ── Auth ─────────────────────────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_TOKEN:
            token = request.headers.get("X-Api-Token") or request.args.get("token")
            if token != API_TOKEN:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Pages ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

# ── CAN Control ──────────────────────────────────────────────────────
@app.route("/api/ping")
def ping():
    return jsonify({"ok": True, "mode": "CAN", "model": "Model S 85D (2015)"})

@app.route("/api/status")
@require_auth
def status():
    ensure_can()
    return jsonify(can.get_status())

# Convenience command handlers
_COMMANDS = [
    "lock", "unlock", "frunk", "trunk", "flash_lights",
    "honk", "windows_vent", "windows_close",
    "charge_port_open", "charge_port_close",
    "mirrors_fold", "mirrors_unfold",
    "interior_lights_on", "interior_lights_off",
    "hvac_on", "hvac_off",
]

for _cmd in _COMMANDS:
    def make_handler(name=_cmd):
        @require_auth
        def handler():
            ensure_can()
            fn = getattr(can, name, None)
            if not fn:
                return jsonify({"error": f"Unknown: {name}"}), 400
            return jsonify(fn())
        app.add_url_rule(f"/api/{name}", f"api_{name}", handler, methods=["POST"])

# ── Tesla Database ───────────────────────────────────────────────────
@app.route("/api/models")
def list_models():
    """Return all Tesla models in database."""
    return jsonify({"models": TESLA_MODELS})

@app.route("/api/models/<model_id>")
def get_model(model_id):
    """Get details for a specific model."""
    from tesla_models import get_model_by_id
    m = get_model_by_id(model_id)
    if m:
        return jsonify(m)
    return jsonify({"error": "Model not found"}), 404

# ── Vehicle Configuration ─────────────────────────────────────────────
@app.route("/api/config/colors")
def get_colors():
    """Return all Tesla paint colors + wrap options."""
    return jsonify(TESLA_COLORS)

@app.route("/api/config/wheels")
def get_wheels():
    """Return all wheel size options."""
    return jsonify(WHEEL_SIZES)

@app.route("/api/config/mcu")
def get_mcu_types():
    """Return MCU / FSD computer upgrade options."""
    return jsonify(MCU_TYPES)

@app.route("/api/config/interior")
def get_interior_colors():
    """Return interior leather color options with HEX codes."""
    return jsonify(INTERIOR_COLORS)

@app.route("/api/config/body")
def get_body_styles():
    """Return body style / facelift / kit options."""
    return jsonify(BODY_STYLES)

@app.route("/api/config/all")
def get_all_config():
    """Return all vehicle configuration options at once."""
    return jsonify({
        "colors": TESLA_COLORS,
        "wheels": WHEEL_SIZES,
        "mcu": MCU_TYPES,
        "interior": INTERIOR_COLORS,
        "body_styles": BODY_STYLES,
    })

@app.route("/api/colors")
def list_colors():
    """Return all Tesla paint colors."""
    return jsonify({"colors": TESLA_COLORS})

@app.route("/api/decode-vin", methods=["POST"])
def decode_vin_endpoint():
    """Decode a Tesla VIN and return vehicle info."""
    data = request.get_json() or {}
    vin = data.get("vin", "").strip()
    if not vin:
        return jsonify({"error": "VIN is required"}), 400
    result = decode_vin(vin)
    return jsonify(result)

@app.route("/api/vehicles")
def my_vehicles():
    """Return saved vehicles (stored in cookies/localStorage on frontend)."""
    # This is a stateless API — vehicles are stored in the frontend's localStorage
    # but we provide a default list
    return jsonify({
        "vehicles": [
            {"id": "default", "name": "My Tesla", "model_id": "ms_85d", "color_id": "midnight_silver", "vin": ""}
        ]
    })

# ── Tesla Fleet API ─────────────────────────────────────────────────

_fleet = None
def get_fleet():
    global _fleet
    if _fleet is None:
        _fleet = get_tesla_fleet()
    return _fleet

@app.route("/api/tesla/auth")
def tesla_auth_start():
    """Start OAuth2 device authorization flow."""
    result = get_fleet().start_auth()
    return jsonify(result)

@app.route("/api/tesla/auth/poll", methods=["POST"])
def tesla_auth_poll():
    """Poll for completed authorization."""
    data = request.get_json() or {}
    device_code = data.get("device_code", "")
    interval = data.get("interval", 5)
    result = get_fleet().poll_auth(device_code, interval)
    return jsonify(result)

@app.route("/api/tesla/status")
def tesla_status():
    """Return status of all Tesla API vehicles."""
    fleet = get_fleet()
    if not fleet.is_authorized:
        return jsonify({"error": "Not authorized", "auth_status": fleet.auth_status})
    vehicles = fleet.get_vehicles()
    results = []
    for v in vehicles:
        status = fleet.get_vehicle_status(v["id"])
        results.append({
            "vin": v["vin"],
            "display_name": v["display_name"],
            "state": v["state"],
            "status": status,
        })
    return jsonify({"vehicles": results, "auth_status": fleet.auth_status})

@app.route("/api/tesla/vehicles")
def tesla_vehicles():
    """List vehicles on Tesla account."""
    fleet = get_fleet()
    if not fleet.is_authorized:
        return jsonify({"error": "Not authorized"})
    return jsonify({"vehicles": fleet.get_vehicles()})

@app.route("/api/tesla/auth/status")
def tesla_auth_status():
    """Check Tesla API auth status."""
    return jsonify(get_fleet().auth_status)

# ── Diagnostics ──────────────────────────────────────────────────────
@app.route("/api/diagnostics")
def diagnostics():
    """Return system diagnostic status: CAN, network, Bluetooth."""
    import subprocess, socket

    result = {
        "can": {"status": "unknown", "detail": ""},
        "cellular": {"status": "unknown", "detail": ""},
        "bluetooth": {"status": "unknown", "detail": ""},
        "wifi": {"status": "unknown", "detail": ""},
    }

    # ── CAN ──
    try:
        # Check if can0 interface exists and is up
        r = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            if "UP" in r.stdout:
                result["can"]["status"] = "ok"
                result["can"]["detail"] = "can0 UP"
            elif "DOWN" in r.stdout:
                result["can"]["status"] = "error"
                result["can"]["detail"] = "can0 exists but DOWN"
            else:
                result["can"]["status"] = "warn"
                result["can"]["detail"] = "can0 exists, state unknown"
        else:
            result["can"]["status"] = "error"
            result["can"]["detail"] = "can0 interface not found"

        # Check if Python CAN driver is connected
        result["can"]["driver"] = can.is_connected
    except Exception as e:
        result["can"]["status"] = "error"
        result["can"]["detail"] = str(e)

    # ── Cellular (4G/5G) ──
    try:
        # Check for cellular network interfaces
        r = subprocess.run(["ip", "link"], capture_output=True, text=True, timeout=5)
        interfaces = r.stdout
        cell_ifaces = ["wwan0", "usb0", "eth1"]
        found_cell = [i for i in cell_ifaces if i in interfaces]
        if found_cell:
            result["cellular"]["status"] = "ok"
            result["cellular"]["detail"] = f"Found: {', '.join(found_cell)}"
        else:
            # Check via NM or ModemManager
            r2 = subprocess.run(["nmcli", "-t", "-f", "TYPE,DEVICE", "device"], capture_output=True, text=True, timeout=5)
            if "gsm" in r2.stdout.lower():
                result["cellular"]["status"] = "ok"
                result["cellular"]["detail"] = "GSM modem detected"
            else:
                result["cellular"]["status"] = "warn"
                result["cellular"]["detail"] = "No cellular interface detected"
    except Exception as e:
        result["cellular"]["status"] = "warn"
        result["cellular"]["detail"] = f"Check failed: {e}"

    # ── Bluetooth ──
    try:
        r = subprocess.run(["hciconfig", "hci0"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            if "UP" in r.stdout:
                result["bluetooth"]["status"] = "ok"
                # Extract BD address
                import re
                m = re.search(r'BD Address: ([0-9A-F:]+)', r.stdout)
                addr = m.group(1) if m else "unknown"
                result["bluetooth"]["detail"] = f"hci0 UP · {addr}"
            else:
                result["bluetooth"]["status"] = "error"
                result["bluetooth"]["detail"] = "hci0 exists but DOWN"
        else:
            result["bluetooth"]["status"] = "error"
            result["bluetooth"]["detail"] = "hci0 not found"
    except Exception as e:
        result["bluetooth"]["status"] = "error"
        result["bluetooth"]["detail"] = str(e)

    # ── Internet ──
    try:
        # Ping test (Google DNS)
        r = subprocess.run(["ping", "-c", "1", "-W", "3", "8.8.8.8"],
                          capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            result["cellular"]["internet"] = True
            result["cellular"]["detail"] += " · Internet OK"
        else:
            result["cellular"]["internet"] = False
    except:
        result["cellular"]["internet"] = False

    # ── Tailscale ──
    try:
        r = subprocess.run(["tailscale", "status"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if "100." in line:
                    result["cellular"]["tailscale"] = line.split()[0] if line.split() else "connected"
                    break
            else:
                result["cellular"]["tailscale"] = "connected"
        else:
            result["cellular"]["tailscale"] = False
    except:
        result["cellular"]["tailscale"] = False

    return jsonify(result)


# ── Error ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("🚗 Tesla Local Control (CAN) — Model S 85D (2015)")
    log.info(f"   Listening: {HOST}:{PORT}")
    log.info(f"   Auth: {'ON' if API_TOKEN else 'OFF'}")
    log.info(f"   Open: http://localhost:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)
