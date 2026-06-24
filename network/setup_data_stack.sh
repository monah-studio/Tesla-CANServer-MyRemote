#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Tesla Data Stack — Grafana + InfluxDB + Telegraf + Cloudflare Tunnel
# 跑在 Orange Pi 4 Pro 上，收 CAN 总线数据 → 可视化仪表盘
# ──────────────────────────────────────────────────────────────────────
# 用法:
#   bash setup_data_stack.sh
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

echo -e "${CYAN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Tesla Data Stack Installer              ║${NC}"
echo -e "${CYAN}║  Grafana + InfluxDB + Telegraf + Tunnel  ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════╝${NC}"

# ── 1. Kill any stuck apt processes ──
echo ""
echo "[1/6] 清理 apt 锁"
sudo killall apt-get apt 2>/dev/null || true
sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock /var/cache/apt/archives/lock /var/lib/dpkg/lock
sudo dpkg --configure -a 2>/dev/null || true
log "apt 就绪"

# ── 2. Install Grafana from APT repo ──
echo ""
echo "[2/6] 安装 Grafana"
if ! dpkg -l grafana 2>/dev/null | grep -q '^ii'; then
  sudo apt-get install -y -qq software-properties-common wget gnupg2 2>/dev/null
  wget -q -O - https://apt.grafana.com/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/grafana.gpg 2>/dev/null
  echo 'deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main' | sudo tee /etc/apt/sources.list.d/grafana.list > /dev/null
  sudo apt-get update -qq 2>/dev/null
  sudo apt-get install -y -qq grafana 2>&1 | tail -2
  log "Grafana installed"
else
  log "Grafana 已安装"
fi

# Create grafana user if missing
id -u grafana &>/dev/null || sudo useradd --system -r grafana

# Config files
sudo cp /usr/share/grafana/conf/defaults.ini /etc/grafana/grafana.ini 2>/dev/null || true
sudo mkdir -p /var/lib/grafana/data /var/lib/grafana/log /var/lib/grafana/plugins /var/run/grafana /etc/grafana/provisioning
sudo chown -R grafana:grafana /var/lib/grafana /var/run/grafana /etc/grafana

# Environment file
sudo tee /etc/default/grafana-server > /dev/null << 'ENVEOF'
CONF_FILE=/etc/grafana/grafana.ini
PID_FILE_DIR=/var/run/grafana
LOG_DIR=/var/lib/grafana/log
DATA_DIR=/var/lib/grafana/data
PLUGINS_DIR=/var/lib/grafana/plugins
PROVISIONING_CFG_DIR=/etc/grafana/provisioning
ENVEOF

# Fix service unit WorkingDirectory
sudo sed -i 's|WorkingDirectory=/usr/share/grafana|WorkingDirectory=/usr/share/grafana/bin|' /lib/systemd/system/grafana-server.service 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable grafana-server
sudo systemctl restart grafana-server
sleep 3
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q 200; then
  log "Grafana 运行中 → http://localhost:3000"
else
  warn "Grafana 启动较慢，稍后检查: sudo journalctl -u grafana-server -n 20"
fi

# ── 3. Install InfluxDB ──
echo ""
echo "[3/6] 安装 InfluxDB"
if ! which influxd &>/dev/null; then
  cd /tmp
  wget -q --show-progress https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.11-linux-arm64.tar.gz -O influxdb.tar.gz
  tar xzf influxdb.tar.gz 2>/dev/null
  sudo cp influxdb2-*/usr/bin/influxd /usr/local/bin/
  sudo cp influxdb2-*/usr/bin/influx /usr/local/bin/
  rm -rf influxdb2-* influxdb.tar.gz
  log "InfluxDB installed"
else
  log "InfluxDB 已安装"
fi

# Create user + systemd service
id -u influxdb &>/dev/null || sudo useradd --system -r influxdb
sudo mkdir -p /var/lib/influxdb2 /var/log/influxdb2
sudo chown -R influxdb:influxdb /var/lib/influxdb2 /var/log/influxdb2

sudo tee /etc/systemd/system/influxdb2.service > /dev/null << 'SVC'
[Unit]
Description=InfluxDB 2.x
After=network.target

[Service]
Type=simple
User=influxdb
Group=influxdb
ExecStart=/usr/local/bin/influxd --bolt-path=/var/lib/influxdb2/influxd.bolt --engine-path=/var/lib/influxdb2/engine
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SVC

sudo systemctl daemon-reload
sudo systemctl enable influxdb2
sudo systemctl restart influxdb2
sleep 3
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8086/ping | grep -q 204; then
  log "InfluxDB 运行中 → http://localhost:8086"
else
  warn "InfluxDB 启动中，稍后: sudo journalctl -u influxdb2 -n 20"
fi

# ── 4. Configure Telegraf ──
echo ""
echo "[4/6] 配置 Telegraf (CAN 数据采集)"
sudo tee /etc/telegraf/telegraf.conf > /dev/null << 'TELGRAF'
[agent]
  interval = "10s"
  flush_interval = "10s"
  omit_hostname = false

[[inputs.exec]]
  commands = ["/opt/tesla-control/app/tools/can_sniffer.py --telegraf"]
  interval = "10s"
  timeout = "8s"
  data_format = "influx"
  name_override = "tesla_can"

[[outputs.influxdb_v2]]
  urls = ["http://localhost:8086"]
  token = ""
  organization = "tesla"
  bucket = "tesla_data"
TELGRAF

sudo systemctl restart telegraf
log "Telegraf 已配置"

# ── 5. Cloudflare Tunnel ──
echo ""
echo "[5/6] 配置 Cloudflare Tunnel"
if ! which cloudflared &>/dev/null; then
  cd /tmp
  wget -q --show-progress https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -O cloudflared.deb
  sudo dpkg -i cloudflared.deb 2>&1 | tail -2
  rm cloudflared.deb
  log "cloudflared installed"
else
  log "cloudflared 已安装"
fi

echo ""
warn "═══════════════════════════════════════════════════════"
warn "  下一步: Cloudflare Tunnel 认证"
warn "  → 先确认 openfrunk.com 的 NS 已改到 Cloudflare"
warn "  → 在 Orange Pi 上运行:"
warn "     cloudflared tunnel login"
warn "  → 浏览器打开显示的 URL → 授权"
warn "  → 然后运行:"
warn "     cloudflared tunnel create tesla-can"
warn "     cloudflared tunnel route dns tesla-can can.openfrunk.com"
warn "     sudo tee /etc/systemd/system/cfd-tunnel.service..."
warn "═══════════════════════════════════════════════════════"

# ── 6. Summary ──
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Tesla Data Stack 安装完成${NC}"
echo ""
echo "  Grafana  : http://localhost:3000"
echo "  InfluxDB : http://localhost:8086"
echo "  Telegraf : $(systemctl is-active telegraf)"
echo ""
echo "  📡 一键启动所有服务:"
echo "    sudo systemctl start grafana-server influxdb2 telegraf"
echo ""
echo "  📋 查看日志:"
echo "    sudo journalctl -u grafana-server -n 30"
echo "    sudo journalctl -u influxdb2 -n 30"
echo ""
warn "  Cloudflare Tunnel 需要手动认证后才完整"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
