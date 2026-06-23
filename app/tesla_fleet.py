"""
Tesla Fleet API — OAuth2 read-only client for Model X / other Teslas
=====================================================================
Uses Tesla's official Fleet API via OAuth2 device authorization flow.

Endpoints:
  GET  /api/tesla/auth          → Start OAuth flow, return URL + code
  POST /api/tesla/auth/poll     → Poll for token after user auth
  GET  /api/tesla/vehicles      → List all vehicles on account
  GET  /api/tesla/status        → Get status for configured Tesla-API vehicles
  POST /api/tesla/refresh       → Force refresh OAuth token
"""

import json
import logging
import os
import threading
import time
import urllib.request
import urllib.parse

log = logging.getLogger("tesla_fleet")

# ── Config ────────────────────────────────────────────────────────────
AUTH_BASE = "https://auth.tesla.com/oauth2/v3"
API_BASE  = "https://owner-api.teslamotors.com"

# Default public client ID (any registered app can use their own)
DEFAULT_CLIENT_ID = "ownerapi"

TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "tesla_tokens.json")


class TeslaFleetClient:
    """Tesla Fleet API OAuth2 client — read-only vehicle status."""

    def __init__(self, client_id=None):
        self.client_id = client_id or os.environ.get("TESLA_CLIENT_ID") or DEFAULT_CLIENT_ID
        self._token = None
        self._token_lock = threading.Lock()
        self._vehicles = []
        self._load_token()

    # ── Token Persistence ─────────────────────────────────────────

    def _token_path(self):
        return os.path.join(os.path.dirname(__file__), "..", "tesla_tokens.json")

    def _load_token(self):
        path = self._token_path()
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("access_token") and data.get("expires_at", 0) > time.time():
                    self._token = data
                    log.info("✅ Tesla token loaded (expires in %ds)", int(data["expires_at"] - time.time()))
                    return True
            except Exception as e:
                log.warning("Failed to load Tesla token: %s", e)
        return False

    def _save_token(self, data):
        path = self._token_path()
        with open(path, "w") as f:
            json.dump(data, f)
        self._token = data
        log.info("💾 Tesla token saved")

    # ── OAuth Device Flow ─────────────────────────────────────────

    def start_auth(self):
        """Start OAuth2 device authorization flow.
        Returns dict with verification_uri, user_code, device_code."""
        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "scope": "openid vehicle_device_data vehicle_charging:read",
        }).encode()

        req = urllib.request.Request(
            f"{AUTH_BASE}/device/authorize",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            log.info("🔐 Tesla auth started: %s", result.get("verification_uri_complete", ""))
            return {
                "device_code": result["device_code"],
                "user_code": result["user_code"],
                "verification_uri": result["verification_uri"],
                "verification_uri_complete": result.get("verification_uri_complete", ""),
                "interval": result.get("interval", 5),
            }
        except Exception as e:
            log.error("❌ Tesla auth start failed: %s", e)
            return {"error": str(e)}

    def poll_auth(self, device_code, interval=5, timeout=300):
        """Poll for token after user authorises in browser.
        Returns access_token dict on success, None if still waiting."""
        data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": self.client_id,
            "device_code": device_code,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{AUTH_BASE}/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            err_data = json.loads(body) if body else {}
            err = err_data.get("error", "unknown")
            if err == "authorization_pending":
                return None  # User hasn't authorised yet
            elif err == "slow_down":
                return {"wait": interval + 5}
            elif err == "expired_token":
                return {"error": "expired"}
            else:
                return {"error": err}
        except Exception as e:
            return {"error": str(e)}

        # Success — store tokens
        token_data = {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
            "expires_at": time.time() + result.get("expires_in", 28800),
            "created_at": time.time(),
        }
        self._save_token(token_data)

        # Fetch vehicles immediately
        self._fetch_vehicles()

        return {"success": True}

    def refresh_token(self):
        """Refresh the access token using refresh_token."""
        if not self._token or not self._token.get("refresh_token"):
            return False

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self._token["refresh_token"],
        }).encode()

        try:
            req = urllib.request.Request(
                f"{AUTH_BASE}/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            self._token["access_token"] = result["access_token"]
            if result.get("refresh_token"):
                self._token["refresh_token"] = result["refresh_token"]
            self._token["expires_at"] = time.time() + result.get("expires_in", 28800)
            self._save_token(self._token)
            log.info("🔄 Tesla token refreshed")
            return True
        except Exception as e:
            log.error("❌ Token refresh failed: %s", e)
            return False

    @property
    def is_authorized(self):
        return self._token is not None and self._token.get("expires_at", 0) > time.time()

    @property
    def auth_status(self):
        if self._token:
            exp = self._token.get("expires_at", 0)
            remaining = int(exp - time.time()) if exp > time.time() else 0
            return {"authorized": True, "expires_in": remaining}
        return {"authorized": False}

    # ── API Calls ─────────────────────────────────────────────────

    def _api_call(self, method, path, data=None):
        """Make an authenticated API call to Tesla."""
        if not self.is_authorized:
            return {"error": "Not authorized"}

        url = f"{API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self._token['access_token']}",
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url, headers=headers, method=method)
        if data is not None:
            req.data = json.dumps(data).encode()

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            return result.get("response", result)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.warning("Token expired, attempting refresh...")
                if self.refresh_token():
                    # Retry
                    headers["Authorization"] = f"Bearer {self._token['access_token']}"
                    req2 = urllib.request.Request(url, headers=headers, method=method)
                    if data is not None:
                        req2.data = json.dumps(data).encode()
                    try:
                        resp2 = urllib.request.urlopen(req2, timeout=15)
                        result2 = json.loads(resp2.read())
                        return result2.get("response", result2)
                    except Exception as e2:
                        return {"error": str(e2)}
                return {"error": "Auth failed even after refresh"}
            body = e.read().decode()
            return {"error": f"HTTP {e.code}: {body[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def _fetch_vehicles(self):
        """Fetch vehicle list from Tesla API."""
        result = self._api_call("GET", "/api/1/vehicles")
        if isinstance(result, list):
            self._vehicles = result
            log.info("🚗 Tesla vehicles: %d found", len(result))
        elif isinstance(result, dict) and "error" in result:
            log.error("Failed to fetch Tesla vehicles: %s", result["error"])
        return self._vehicles

    def get_vehicles(self):
        """Return list of vehicles."""
        if not self._vehicles:
            self._fetch_vehicles()
        return [
            {
                "id": v["id"],
                "vin": v.get("vin", ""),
                "display_name": v.get("display_name", ""),
                "state": v.get("state", ""),
                "model": v.get("vehicle_id", ""),
            }
            for v in self._vehicles
        ]

    def get_vehicle_status(self, vehicle_id):
        """Get full status for a specific vehicle."""
        result = self._api_call("GET", f"/api/1/vehicles/{vehicle_id}/vehicle_data")
        if isinstance(result, dict):
            return self._parse_status(result)
        return result

    @staticmethod
    def _parse_status(data):
        """Parse Tesla API response into our standard format."""
        charge = data.get("charge_state", {})
        drive = data.get("drive_state", {})
        climate = data.get("climate_state", {})
        vehicle = data.get("vehicle_state", {})

        soc = charge.get("battery_level")
        return {
            "connected": data.get("state") == "online",
            "source": "tesla_api",
            "battery_soc": soc,
            "range_km": round(charge.get("battery_range", 0) * 1.609, 1) if charge.get("battery_range") else None,
            "gear": drive.get("shift_state") or "P",
            "speed_kmh": drive.get("speed", None),
            "drive_mode": drive.get("previous_speed", None) if drive.get("shift_state") else "PARK",
            "charge_port": {
                "state": "OPEN" if charge.get("charge_port_door_open") else "CLOSED",
                "charging": charge.get("charging_state") == "Charging",
            },
            "doors": {
                "locked": vehicle.get("locked"),
                "driver": None,  # Tesla API doesn't expose per-door
                "passenger": None,
                "rear_left": None,
                "rear_right": None,
            },
            "windows": vehicle.get("fd_window", 0) > 0 and "VENTED" or "CLOSED",
            "ambient_temp_c": climate.get("outside_temp"),
            "inside_temp_c": climate.get("inside_temp"),
            "odometer_km": round(vehicle.get("odometer", 0) * 1.609, 1) if vehicle.get("odometer") else None,
            "software_version": vehicle.get("car_version", ""),
        }


# ── Singleton ────────────────────────────────────────────────────────
_client = None


def get_client():
    global _client
    if _client is None:
        _client = TeslaFleetClient()
    return _client
