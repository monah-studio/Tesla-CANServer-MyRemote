# 🚗 Tesla Model S CAN Server · Remote

<p align="center">
  <img src="https://img.shields.io/badge/status-unfinished-yellow" alt="unfinished">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS-blue" alt="platform">
  <img src="https://img.shields.io/badge/languages-4-orange" alt="lang-4">
</p>

> **[ English ]** · **[ 简体中文 ]** · **[ 日本語 ]** · **[ 한국어 ]**

---

**[English](#english) | [简体中文](#简体中文) | [日本語](#日本語) | [한국어](#한국어)**

---

<a name="english"></a>
## 🇺🇸 English

### Why This Exists — A Story About a Car

In 2015, I bought a Tesla Model S 85D. Midnight Silver Metallic. HK$900,000 before tax. It wasn't just a car — it was a statement, a companion, a piece of engineering history. We drove through monsoons, midnight expressways, and the quiet back roads of the New Territories. That car knew me before I knew myself.

Then one day, insurance declared it a "total loss."

Tesla's servers flipped a switch somewhere in Fremont. No more app. No more remote lock. No more climate control from my phone. The same vehicle I'd paid nearly a million Hong Kong dollars for was suddenly *dumber* than a 1998 Corolla — because a database entry said so.

I'm a lawyer by training, a mathematician by obsession, and a software engineer by love. GitHub is my second home. I invest in early-stage deep-tech startups. And I thought: *this is absurd*. I own the machine. The CAN bus is mine. Why should a server in California decide whether I can open my own frunk?

So I took a friend's spare Orange Pi 4 Pro — originally destined to become a dashcam NAS with 3 TOPS of edge AI compute — and repurposed it. This repository is the result.

### What This Is (and Isn't)

| ✅ This is | ❌ This is NOT |
|-----------|----------------|
| 🔧 A self-hosted CAN bus vehicle controller | 🚫 A finished product |
| 📡 Works offline, no Tesla servers needed | 🚫 A replacement for Tesla's app |
| 💻 Runs on Orange Pi / Raspberry Pi + USB CAN | 🚫 Production-ready |
| 🔗 Full PWA web app + REST API | 🚫 Plug-and-play — requires tinkering |
| 🇨🇳🇭🇰🇯🇵🇰🇷 Multi-language | 🚫 Warranty-friendly |

> **⚠️ WORK IN PROGRESS** — This is a weekend hacker's side project. It *mostly* works on my desk. It has NOT completed a full car integration yet. I'm sharing it because I believe in open-source, and if you have a similar situation (total-loss Tesla, blocked by OEM cloud), maybe we can figure it out together.

### The Stack

```
📱 Phone (PWA)
    ↓
🔗 Tailscale / WireGuard (encrypted P2P tunnel)
    ↓
🍊 Orange Pi 4 Pro (6GB RAM, ARM64 Linux)
    ├── Flask REST API (port 5000)
    ├── Python CAN driver (python-can + socketcan)
    ├── Tailscale client (always-on remote access)
    ├── DDNS updater (optional — remote.openfrunk.com)
    └── BLE beacon (local phone discovery)
    ↓
🔌 CANable 2.0 USB-CAN adapter
    └── OBD-II port → Vehicle Body CAN (125 kbps)
```

### Features

- 🔒 Lock / unlock doors via CAN bus
- 🟢 Open front trunk / 🟤 rear trunk
- 💡 Flash lights · 📯 Honk horn
- 🪟 Vent windows · ⚡ Charging control
- 📊 Real-time diagnostics (CAN / Bluetooth / 4G / Tailscale)
- 🚘 VIN decoder — 39 Tesla models database
- 🎨 Tesla + Material You style UI (dark theme)
- 🌐 Multi-language UI (ZH / EN / JA / KO)
- 📡 4 connection modes: Tailscale / DDNS / WiFi / BLE

### Hardware You'll Need

| Component | Est. Cost | Where |
|-----------|-----------|-------|
| Orange Pi 4 Pro / RPi 4 | ~¥300 | 淘宝 / Amazon |
| CANable 2.0 USB-CAN | ~¥45 | 淘宝 |
| OBD-II connector | ~¥20 | 淘宝 |
| 4G USB modem (opt.) | ~¥200 | Carrier |

### Quick Start

```bash
# 1. Flash Armbian or Ubuntu Server to Orange Pi
# 2. Clone this repo
git clone https://github.com/Monah-Limited/Tesla-ModelS-CAN-Server-Remote.git
cd Tesla-ModelS-CAN-Server-Remote

# 3. Run one-click setup
bash setup_orangepi.sh

# 4. Wire CANable to OBD-II port
#    CAN_H → pin 1   CAN_L → pin 9   GND → pin 4

# 5. Start CAN interface
sudo slcand -o -c -s8 /dev/ttyACM0 can0
sudo ip link set can0 up type can bitrate 125000

# 6. Configure network (optional)
bash network/setup_network.sh
```

### Similar Projects

- [Open Vehicles](https://docs.openvehicles.com) — OVMS hardware module
- [Tesla Vehicle Command SDK](https://github.com/teslamotors/vehicle-command) — For 2021+ models with BLE support
- [Comma.ai OpenPilot](https://github.com/commaai/openpilot) — ADAS system

## 🙏 Credits / 致谢

This project would not exist without these open-source projects and communities:

| Project | What it does |
|---------|-------------|
| [**Open Vehicles**](https://docs.openvehicles.com) | OVMS — the original open-source Tesla CAN bus project. Massive inspiration. |
| [**CANable**](https://canable.io) | USB-to-CAN adapter firmware & hardware — the physical bridge to the car |
| [**candleLight firmware**](https://github.com/candle-usb/candleLight_fw) | Open-source CAN firmware running on CANable |
| [**python-can**](https://github.com/hardbyte/python-can) | Python CAN library |
| [**Flask**](https://flask.palletsprojects.com) | Web framework for the REST API server |
| [**Tailscale**](https://tailscale.com) | Zero-config VPN — secure remote access to the car |
| [**Orange Pi 4 Pro**](http://www.orangepi.org) | The SBC running the server (Raspberry Pi alternative) |
| [**Tesla Vehicle Command SDK**](https://github.com/teslamotors/vehicle-command) | Tesla's official BLE/cloud API for 2021+ models |
| [**Comma.ai OpenPilot**](https://github.com/commaai/openpilot) | ADAS system — pushing the boundaries of what's possible with cars |
| [**OpenGarages**](https://opengarages.org) | Community of hackers reverse-engineering vehicle protocols |

**Special thanks** to the reverse-engineering community on [Tesla Motors Club](https://teslamotorsclub.com) and the CAN bus hacking forums — the collective knowledge that made this possible.

### License

MIT — do whatever you want. Just don't sue me if your car does something unexpected. This is a side project, not a product.

---

<a name="简体中文"></a>
## 🇨🇳 简体中文

### 为什么有这个项目 — 一辆车的故事

2015 年，我买了一台特斯拉 Model S 85D。午夜银，不含税 90 万港币。它不只是一辆车——它是一个宣言，一个伙伴，一段无法替代的旅程。我们一起穿过台风天、深夜高速公路、新界的乡间小路。那台车比任何机器都更懂我。

然后有一天，保险公司判定它「全损」。

特斯拉在弗里蒙特的某台服务器里打了一个开关。App 没了，远程锁门没了，手机预热空调没了。我花了近一百万港币买的车，因为数据库中某个标志位被翻转，突然变得比 1998 年的卡罗拉还要蠢。

我是法学出身，痴迷于数学，靠写代码获得快乐。GitHub 是我的第二个家。我投早期硬科技公司。我当时想：**这他妈太荒谬了**。我拥有这台机器。CAN 总线是我的。凭什么加州的一台服务器能决定我能不能打开自己的前备箱？

所以我拿朋友送的一块 Orange Pi 4 Pro——本来打算做成行车记录仪 NAS，用 3 TOPS 做边缘 AI 计算——改了用途。这个仓库就是结果。

### 这是什么（不是什么）

| ✅ 这是 | ❌ 不是 |
|---------|--------|
| 🔧 自建 CAN 总线车辆控制器 | 🚫 完成品 |
| 📡 离线可用，无需 Tesla 服务器 | 🚫 Tesla 官方 App 的替代品 |
| 💻 树莓派 / Orange Pi + USB CAN 模块 | 🚫 量产就绪 |
| 🔗 完整 PWA Web App + REST API | 🚫 开箱即用 |
| 🇨🇳🇭🇰🇯🇵🇰🇷 多语言 | 🚫 保修友好 |

> **⚠️ 开发中** — 周末黑客项目。在我的桌上大概是跑得通的。还没有完成完整车载集成。分享出来是因为我相信开源。

---

<a name="日本語"></a>
## 🇯🇵 日本語

### このプロジェクトが生まれた理由 — ある車の物語

2015年、税抜90万香港ドルで Tesla Model S 85D を購入しました。ミッドナイトシルバー。単なる移動手段ではなく、宣言であり、伴侶であり、エンジニアリングの申し子でした。台風の夜も、深夜の高速道路も、新界の静かな裏道も、その車はいつも私のそばにいました。

そしてある日、保険会社が「全損」と判断しました。

カリフォルニアのTeslaサーバーがフラグを一つ反転させただけで — アプリも、リモートロックも、スマホからのエアコン操作も、すべて消えました。100万香港ドル近く払った車が、データベースの一行のせいで突然1998年のカローラより「馬鹿」になったのです。

私は法学を学び、数学に魅せられ、コードを書くことで生きています。GitHubは第二の我が家。ディープテックのアーリー投資家でもあります。そして思いました：**これ、めっちゃおかしいやろ**。このマシンは俺のものだ。CANバスだって俺のものだ。カリフォルニアのサーバーが俺のフロントトランクを開けられるかどうか決めるって、どういうこと？

だから友達にもらった Orange Pi 4 Pro（3 TOPSのエッジAIでドラレコNASを作る予定だった）を転用しました。このリポジトリはその結果です。

> **⚠️ 開発中** — 週末のハッカープロジェクトです。机上では大体動いてます。実車での完全統合はまだです。

---

<a name="한국어"></a>
## 🇰🇷 한국어

### 이 프로젝트가 존재하는 이유 — 한 대의 차 이야기

2015년, 세금 제외 90만 홍콩달러를 주고 Tesla Model S 85D를 샀습니다. 미드나잇 실버. 그냥 차가 아니었어요. 선언이었고, 동반자였고, 엔지니어링 역사의 한 조각이었습니다. 태풍이 몰아치는 밤, 깊은 한밤의 고속도로, 신계의 조용한 뒷길 — 그 차는 나를 누구보다 잘 알았습니다.

그러던 어느 날, 보험사가 '전손' 판정을 내렸습니다.

프리몬트 어딘가의 Tesla 서버가 플래그 하나를 뒤집었을 뿐인데 — 앱도, 원격 잠금도, 폰으로 에어컨 켜는 것도, 전부 사라졌습니다. 거의 100만 홍콩달러를 낸 차가 데이터베이스 한 줄 때문에 갑자기 1998년식 코롤라보다 '멍청해진' 겁니다.

법학을 공부했고, 수학에 집착하며, 코드로 숨을 쉽니다. GitHub이 두 번째 집이에요. 딥테크 얼리 스테이지 투자자이기도 합니다. 저는 생각했습니다: **이건 말이 안 된다**. 이 기계는 내 소유다. CAN 버스도 내 거다. 캘리포니아 서버가 내 앞 트렁크를 열 수 있는지 결정한다는 게 말이 돼?

그래서 친구에게서 받은 Orange Pi 4 Pro(3 TOPS 에지 AI로 블랙박스 NAS를 만들 예정이었던)를 용도 변경했습니다. 이 저장소가 바로 그 결과입니다.

> **⚠️ 개발 중** — 주말 해커의 사이드 프로젝트입니다. 책상 위에선 대부분 돌아가요. 실차 완전 통합은 아직입니다.

---

## 📁 Project Structure

```
tesla-local-control/
├── app/
│   ├── tesla_can.py          # CAN bus driver (socketcan interface)
│   ├── tesla_models.py       # 39 Tesla models database + VIN decoder
│   ├── server.py             # Flask REST API server
│   └── static/index.html     # PWA mobile app (4-language UI)
├── network/
│   ├── setup_4g_modem.sh     # 4G/5G modem configuration
│   ├── setup_network.sh      # Tailscale + DDNS + BLE
│   └── ddns_update.sh        # DDNS periodic updater
├── setup_orangepi.sh         # One-click deployment
├── wiring.md                 # OBD-II wiring guide
├── ARCHITECTURE.md           # Architecture diagram
└── LICENSE                   # MIT
```

---

## 👤 About the Author

**Tim Wynter** — lawyer, mathematician, engineer. GitHub native. Deep-tech investor. Weekend hacker who refuses to let a cloud server dictate what his car can do.

This repo is a conversation starter, not a product pitch. PRs welcome. Issues welcome. Ideas welcome. Let's build together.

---

<p align="center">
  <sub>Built with ☕ and stubbornness in Hong Kong SAR</sub>
</p>
