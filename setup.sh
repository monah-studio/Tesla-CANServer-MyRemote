#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Tesla CAN Server — One-Click Setup
# ═══════════════════════════════════════════════════════════════════════
# Supports: Orange Pi 4 Pro, Raspberry Pi 3/4/5
# - Auto-detect CANable 2.0 / MCP2515
# - Auto-detect 4G modem
# - Choose: Tailscale P2P VPN  OR  Cloudflare Tunnel
# - Pulls latest server from GitHub
# ───────────────────────────────────────────────────────────────────────
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/monah-studio/\
# Tesla-ModelS-CAN-Server-Remote/main/setup.sh | bash
#
# Or after clone:
#   chmod +x setup.sh && sudo ./setup.sh
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
BOLD='\033[1m'; DIM='\033[2m'

log()  { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${BLUE}ℹ${NC} $1"; }
header() { echo -e "\n${CYAN}${BOLD}═══ $1 ═══${NC}\n"; }

# ── Config ──────────────────────────────────────────────────────────
REPO_URL="https://github.com/monah-studio/Tesla-CANServer-MyRemote.git"
INSTALL_DIR="/opt/tesla-control"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_USER="${SUDO_USER:-root}"
CURRENT_IP=""

# ── Root check ──────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "This script must be run as root (sudo)"
  exit 1
fi

# ═══════════════════════════════════════════════════════════════════
# 1. SYSTEM INFO
# ═══════════════════════════════════════════════════════════════════
header "1/8  System Detection"

ARCH=$(uname -m)
OS=$(grep -oP '^ID=\K.*' /etc/os-release 2>/dev/null || echo "unknown")
OS_VER=$(grep -oP '^VERSION_ID=\K.*' /etc/os-release 2>/dev/null || echo "unknown")
HOST=$(hostname)

info "Architecture : $ARCH"
info "OS          : $OS $OS_VER"
info "Hostname    : $HOST"
log "System compatible"

# Detect Orange Pi vs Raspberry Pi
if grep -qi "orange" /proc/device-tree/model 2>/dev/null || [[ "$HOST" == *"orangepi"* ]]; then
  BOARD="orangepi"
  log "Detected: Orange Pi"
elif grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
  BOARD="raspberrypi"
  log "Detected: Raspberry Pi"
else
  BOARD="generic"
  warn "Unknown SBC — continuing with generic setup"
fi

# ───────────────────────────────────────────────────────────────────
# 2. DEPENDENCIES
# ───────────────────────────────────────────────────────────────────
header "2/8  Installing System Dependencies"

apt-get update -qq

# Python + CAN tools + networking
DEPS=(
  python3 python3-pip python3-venv
  can-utils
  git
  curl wget
  usb-modeswitch usb-modeswitch-data
  network-manager modemmanager
  bluez bluez-tools
)

# Only install what's available (avoid errors on minimal images)
for pkg in "${DEPS[@]}"; do
  apt-get install -y -qq "$pkg" 2>/dev/null || warn "Package '$pkg' not available, skipping"
done

# Install Python packages
pip3 install --quiet --upgrade pip 2>/dev/null || true

log "System dependencies installed"

# ───────────────────────────────────────────────────────────────────
# 3. CANABLE / CAN HARDWARE DETECTION
# ───────────────────────────────────────────────────────────────────
header "3/8  CAN Hardware Detection"

CAN_INTERFACE=""
CAN_BITRATE=125000

# Check for CANable 2.0 (candleLight firmware → gs_usb kernel module)
if ls /dev/ttyACM* 2>/dev/null | grep -q .; then
  warn "CANable detected as serial (ttyACM) — needs candleLight firmware"
  warn "Flash firmware: https://canable.io/getting-started.html"
  CAN_INTERFACE="socketcan"
elif lsmod | grep -q "gs_usb"; then
  log "CANable detected via gs_usb (native socketcan)"
  CAN_INTERFACE="socketcan"
  modprobe gs_usb 2>/dev/null || true
# Check for MCP2515 on SPI
elif ls /dev/spidev* 2>/dev/null | grep -q .; then
  if dmesg 2>/dev/null | grep -qi "mcp2515\|mcp25xx"; then
    log "MCP2515 detected on SPI"
    CAN_INTERFACE="socketcan"
  else
    warn "SPI device found but no MCP2515 driver loaded"
    warn "Run: sudo dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25"
  fi
else
  warn "No CAN hardware auto-detected"
  warn "Plug in CANable 2.0 and try again"
  CAN_INTERFACE="socketcan"
fi

# Create CAN bringup service
cat > /etc/systemd/system/can0-bringup.service << 'EOSYSTEMD'
[Unit]
Description=Bring up CAN0 interface (Tesla Body CAN 125kbps)
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/ip link set can0 type can bitrate 125000
ExecStart=/sbin/ip link set can0 up
ExecStop=/sbin/ip link set can0 down

[Install]
WantedBy=multi-user.target
EOSYSTEMD

systemctl daemon-reload
systemctl enable can0-bringup 2>/dev/null || true

log "CAN bringup service created"

# ───────────────────────────────────────────────────────────────────
# 4. 4G MODEM DETECTION
# ───────────────────────────────────────────────────────────────────
header "4/8  4G Modem Detection"

if lsusb 2>/dev/null | grep -qi "modem\|huawei\|quectel\|simcom\|zte\|4g\|lte"; then
  log "4G modem hardware detected"
  systemctl enable ModemManager 2>/dev/null || true
  systemctl start ModemManager 2>/dev/null || true

  echo ""
  info "Available 4G modems:"
  mmcli -L 2>/dev/null || nmcli d 2>/dev/null | grep -i gsm || warn "No modem detected by ModemManager"

  echo ""
  info "───────────────────────────────────────────────"
  info "4G APN config (Hong Kong carriers):"
  info "  CMHK:     cmhk"
  info "  CSL:      mobile"
  info "  3HK:      mobile.three.com.hk"
  info "  SmarTone: smartone"
  info ""
  info "To configure later, run:"
  info "  sudo nmcli con add type gsm ifname \\"*\\""
  info "    con-name tesla-4g apn \\"<APN>\\""
  info "    connection.autoconnect yes"
  info "───────────────────────────────────────────────"
else
  warn "No 4G modem detected"
  warn "The server will use WiFi or Ethernet instead"
fi

# ───────────────────────────────────────────────────────────────────
# 5. SERVER CODE
# ───────────────────────────────────────────────────────────────────
header "5/8  Installing Server Code"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Updating existing installation at $INSTALL_DIR"
  cd "$INSTALL_DIR" && git pull --ff-only 2>/dev/null || warn "Git pull failed, using existing code"
else
  log "Cloning fresh from $REPO_URL"
  mkdir -p "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
    warn "Git clone failed — check network"
    warn "Install manually: git clone $REPO_URL $INSTALL_DIR"
  }
fi

# Ensure app directory exists
APP_DIR="$INSTALL_DIR/app"
if [[ ! -d "$APP_DIR" ]]; then
  APP_DIR="$INSTALL_DIR"
fi

# Create Python virtualenv
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# Install Python deps
REQS="$APP_DIR/requirements.txt"
if [[ -f "$REQS" ]]; then
  "$VENV_DIR/bin/pip" install --quiet -r "$REQS"
else
  "$VENV_DIR/bin/pip" install --quiet flask flask-cors python-can
fi

log "Server code installed at $INSTALL_DIR"

# ───────────────────────────────────────────────────────────────────
# 6. NETWORK CHOICE: TAILSCALE vs CLOUDFLARE
# ───────────────────────────────────────────────────────────────────
header "6/8  Network Tunnel Setup"

PS3="Choose tunnel method (1 or 2): "
options=("🌐  Cloudflare Tunnel (recommended — no VPN needed for users)"
         "🔗  Tailscale P2P VPN"
         "❌  Skip — I'll configure manually")

echo ""
echo -e "${BOLD}How should users access the Tesla server?${NC}"
echo ""
echo -e "  ${CYAN}1) Cloudflare Tunnel${NC}  →  ${GREEN}No VPN needed${NC}"
echo -e "     Users access via domain: tesla-xxx.openfrunk.com"
echo -e "     Works with any 3rd party VPN simultaneously"
echo ""
echo -e "  ${CYAN}2) Tailscale${NC}  →  Users must install Tailscale app"
echo -e "     Simple if you just want P2P VPN"
echo ""
echo -e "  ${CYAN}3) Skip${NC}  →  Set up manually later"
echo ""

read -p "Choice [1/2/3]: " TUNNEL_CHOICE

case "$TUNNEL_CHOICE" in
  2|"")
    # ── TAILSCALE ────────────────────────────────────────────────
    header "  → Installing Tailscale"

    if ! command -v tailscale &>/dev/null; then
      curl -fsSL https://tailscale.com/install.sh | sh
    else
      log "Tailscale already installed"
    fi

    # Orange Pi OS fix: userspace networking
    if [[ "$BOARD" == "orangepi" ]]; then
      warn "Orange Pi detected — applying userspace-networking fix"
      sed -i 's|^ExecStart=.*|ExecStart=/usr/sbin/tailscaled --tun=userspace-networking --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=41641 $FLAGS|' /lib/systemd/system/tailscaled.service 2>/dev/null || true
      systemctl daemon-reload
    fi

    systemctl enable tailscaled
    systemctl restart tailscaled

    echo ""
    info "══════════════════════════════════════════════"
    info "  Authenticate Tailscale:"
    info ""
    info "  sudo tailscale up"
    info ""
    info "  Open the URL in your browser to connect"
    info "  this device to your Tailscale network."
    info "══════════════════════════════════════════════"
    echo ""

    NETWORK_TYPE="tailscale"
    ;;

  1)
    # ── CLOUDFLARE TUNNEL ─────────────────────────────────────────
    header "  → Installing Cloudflare Tunnel"

    # Install cloudflared
    if ! command -v cloudflared &>/dev/null; then
      case "$ARCH" in
        aarch64|arm64)
          wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O /usr/local/bin/cloudflared
          ;;
        armv7l|armhf)
          wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm -O /usr/local/bin/cloudflared
          ;;
        x86_64|amd64)
          wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared
          ;;
        *)
          err "Unsupported architecture: $ARCH"
          warn "Install cloudflared manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
          ;;
      esac
      chmod +x /usr/local/bin/cloudflared
      log "cloudflared installed"
    else
      log "cloudflared already installed"
    fi

    # Check if already logged in
    if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
      echo ""
      info "══════════════════════════════════════════════════════"
      info "  Step 1: Log in to Cloudflare"
      info ""
      info "  Run in another terminal (or continue here):"
      info ""
      info "    cloudflared tunnel login"
      info ""
      info "  This opens a URL — log in to your Cloudflare"
      info "  account and authorize this device."
      info ""
      info "  Press Enter after you've logged in."
      info "══════════════════════════════════════════════════════"
      read -p ""
      cloudflared tunnel login 2>&1 || warn "Login failed — you can run 'cloudflared tunnel login' later"
    fi

    # Create tunnel
    TUNNEL_NAME="tesla-can-$(hostname | tr -cd 'a-zA-Z0-9' | tr '[:upper:]' '[:lower:]' | cut -c1-10)"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}' || true)

    if [[ -z "$TUNNEL_ID" ]]; then
      cloudflared tunnel create "$TUNNEL_NAME" 2>&1 || warn "Tunnel creation failed"
      TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}' || echo "")
    fi

    log "Tunnel: $TUNNEL_NAME (ID: $TUNNEL_ID)"

    # Get credentials file path
    CRED_FILE=$(ls /root/.cloudflared/*.json 2>/dev/null | head -1 || echo "")

    # Create config
    mkdir -p /etc/cloudflared
    cat > /etc/cloudflared/config.yml << EOCF
tunnel: $TUNNEL_NAME
credentials-file: ${CRED_FILE:-/root/.cloudflared/$TUNNEL_ID.json}

ingress:
  - hostname: tesla-${TUNNEL_NAME}.openfrunk.com
    service: http://localhost:5000
  - service: http_status:404
EOCF

    # Create DNS route (optional)
    echo ""
    info "══════════════════════════════════════════════════════"
    info "  Step 2: Route DNS (optional)"
    info ""
    info "  To route a domain through the tunnel, run:"
    info ""
    info "    cloudflared tunnel route dns $TUNNEL_NAME \\"
    info "      tesla-${TUNNEL_NAME}.openfrunk.com"
    info ""
    info "  (Your domain must be on Cloudflare DNS)"
    info "══════════════════════════════════════════════════════"

    # Install as system service
    cloudflared --config /etc/cloudflared/config.yml install 2>/dev/null || {
      warn "Auto-install failed — creating service manually"
      cat > /etc/systemd/system/cloudflared-tunnel.service << 'EOCF'
[Unit]
Description=Cloudflare Tunnel for Tesla CAN
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel run
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOCF
    }

    systemctl daemon-reload
    systemctl enable cloudflared-tunnel 2>/dev/null || systemctl enable cloudflared 2>/dev/null || true

    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "  ╔════════════════════════════════════════════════╗"
    echo "  ║   ☁️  Cloudflare Tunnel Installed              ║"
    echo "  ║                                               ║"
    echo "  ║   Login:  cloudflared tunnel login            ║"
    echo "  ║   Start:  sudo systemctl start cloudflared    ║"
    echo "  ║   Status: sudo systemctl status cloudflared   ║"
    echo "  ╚════════════════════════════════════════════════╝"
    echo -e "${NC}"

    NETWORK_TYPE="cloudflare"
    ;;

  *)
    warn "Skipping network tunnel setup"
    NETWORK_TYPE="none"
    ;;
esac

# ───────────────────────────────────────────────────────────────────
# 7. TESLA CONTROL SERVICE
# ───────────────────────────────────────────────────────────────────
header "7/8  Creating Tesla Control Service"

SERVER_SCRIPT="$APP_DIR/server.py"
if [[ ! -f "$SERVER_SCRIPT" ]]; then
  # Try alternative paths
  for p in "$INSTALL_DIR/server.py" "$INSTALL_DIR/app/server.py" "$INSTALL_DIR/tesla_api.py"; do
    if [[ -f "$p" ]]; then
      SERVER_SCRIPT="$p"
      break
    fi
  done
fi

PYTHON_BIN="$VENV_DIR/bin/python"

cat > /etc/systemd/system/tesla-control.service << EOSVC
[Unit]
Description=Tesla CAN Control Server — 2015 Model S 85D
After=network.target can0.target
Wants=can0-bringup.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_BIN $SERVER_SCRIPT
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOSVC

systemctl daemon-reload
systemctl enable tesla-control

log "Tesla control service created"

# ───────────────────────────────────────────────────────────────────
# 8. VERIFICATION
# ───────────────────────────────────────────────────────────────────
header "8/8  Starting Services"

# Bring up CAN
systemctl start can0-bringup 2>/dev/null || warn "CAN bringup failed — check hardware"

# Start server
systemctl start tesla-control 2>/dev/null || warn "tesla-control start failed"

# Wait a moment
sleep 2

# Check status
echo ""
SVC_STATUS=$(systemctl is-active tesla-control 2>/dev/null || echo "inactive")

if [[ "$SVC_STATUS" == "active" ]]; then
  echo -e "${GREEN}${BOLD}  ✅ Tesla CAN Server is RUNNING${NC}"
else
  echo -e "${RED}${BOLD}  ❌ Tesla CAN Server is NOT running${NC}"
  echo ""
  warn "Check logs: sudo journalctl -u tesla-control -n 30 --no-pager"
fi

# Test locally
if curl -sf http://localhost:5000/api/ping >/dev/null 2>&1; then
  log "Local API: http://localhost:5000/api/ping → OK"
else
  warn "Local API not responding yet (service may still be starting...)"
fi

# Get public IP
CURRENT_IP=$(curl -sf ifconfig.me 2>/dev/null || curl -sf api.ipify.org 2>/dev/null || echo "unknown")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
header "✅ Setup Complete"

echo ""
echo -e "${BOLD}${CYAN}  ╔════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}  ║         🚗 Tesla CAN Server Ready             ║${NC}"
echo -e "${BOLD}${CYAN}  ╚════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "  ${DIM}Hardware:${NC}"
echo -e "    Board   : ${BOLD}$BOARD${NC}"
echo -e "    CAN     : ${BOLD}$CAN_INTERFACE${NC} @ ${BOLD}125 kbps${NC}"
echo -e "    Install : ${DIM}$INSTALL_DIR${NC}"
echo ""

echo -e "  ${DIM}Network:${NC}"
echo -e "    Method  : ${BOLD}$NETWORK_TYPE${NC}"
echo ""

case "$NETWORK_TYPE" in
  tailscale)
    echo -e "  ${DIM}Access:${NC}"
    echo -e "    1. On your phone: ${BOLD}Install Tailscale${NC}"
    echo -e "    2. Run on Orange Pi: ${BOLD}sudo tailscale up${NC}"
    echo -e "    3. Open browser: ${BOLD}http://100.x.x.x:5000${NC}"
    echo ""
    echo -e "    ${YELLOW}⚠ Users must have Tailscale installed on their device${NC}"
    ;;
  cloudflare)
    echo -e "  ${DIM}Access:${NC}"
    echo -e "    1. ${BOLD}cloudflared tunnel login${NC} (if not done)"
    echo -e "    2. ${BOLD}sudo systemctl start cloudflared${NC}"
    echo -e "    3. Route a domain:"
    echo -e "       ${DIM}cloudflared tunnel route dns $TUNNEL_NAME tesla-xxx.yourdomain.com${NC}"
    echo ""
    echo -e "    ${GREEN}✓ No VPN needed — works with any 3rd party VPN${NC}"
    ;;
  *)
    echo -e "  No tunnel configured — configure manually later"
    ;;
esac

echo ""
echo -e "  ${DIM}API Endpoints:${NC}"
echo -e "    ${CYAN}GET  /api/ping${NC}         → Health check"
echo -e "    ${CYAN}GET  /api/status${NC}       → Vehicle status"
echo -e "    ${CYAN}GET  /api/diagnostics${NC}  → System diagnostics"
echo -e "    ${CYAN}POST /api/lock${NC}         → Lock doors"
echo -e "    ${CYAN}POST /api/unlock${NC}       → Unlock doors"
echo -e "    ${CYAN}POST /api/frunk${NC}        → Front trunk"
echo -e "    ${CYAN}POST /api/trunk${NC}        → Rear trunk"
echo -e "    ${CYAN}POST /api/flash_lights${NC} → Flash lights"
echo -e "    ${CYAN}POST /api/honk${NC}         → Honk horn"
echo -e "    ${CYAN}POST /api/windows_vent${NC} → Vent windows"
echo -e "    ${CYAN}POST /api/windows_close${NC}→ Close windows"
echo -e "    ${CYAN}POST /api/charge_port_open${NC}  → Open charge port"
echo -e "    ${CYAN}POST /api/charge_port_close${NC} → Close charge port"
echo -e "    ${CYAN}POST /api/mirrors_fold${NC} → Fold mirrors"
echo -e "    ${CYAN}POST /api/mirrors_unfold${NC}→ Unfold mirrors"
echo -e "    ${CYAN}POST /api/hvac_on${NC}      → HVAC on"
echo -e "    ${CYAN}POST /api/hvac_off${NC}     → HVAC off"
echo -e "    ${CYAN}POST /api/decode-vin${NC}   → Decode VIN"
echo ""

echo -e "  ${DIM}Useful commands:${NC}"
echo -e "    ${DIM}sudo journalctl -u tesla-control -f${NC}  # Live logs"
echo -e "    ${DIM}sudo systemctl restart tesla-control${NC}  # Restart"
echo -e "    ${DIM}ip link show can0${NC}                     # Check CAN"
echo -e "    ${DIM}candump can0${NC}                          # Sniff CAN"
echo ""

# Check if we should reboot
if [[ "$SVC_STATUS" != "active" ]]; then
  warn "Server not running. Reboot suggested: sudo reboot"
elif [[ -z "$CURRENT_IP" || "$CURRENT_IP" == "unknown" ]]; then
  warn "No internet detected. Check 4G/WiFi and reboot if needed."
fi

echo -e "${GREEN}${BOLD}  Happy hacking! 🚗⚡${NC}"
echo ""
