# Contributing to Tesla Local Control

This is a community project — all contributions welcome.

## 🐛 Reporting Bugs

1. Search [existing issues](https://github.com/Monah-Limited/tesla-local-control/issues)
2. Describe: hardware setup (Orange Pi / CANable), Tesla model/year, error message
3. Attach logs (redact any personal IPs or tokens)

## 💡 Feature Ideas

- New CAN commands? Share the CAN ID and data format
- New hardware support? Tell us what SBC or CAN adapter you're using
- Documentation improvements? Always welcome

## 🔧 Pull Requests

### Hardware notes

- Primary target: **Orange Pi 4 Pro** (RK3399) + **CANable** (candleLight firmware)
- Secondary target: Raspberry Pi 4/5 + MCP2515 CAN hat
- VPN layer: **Tailscale** (preferred) or WireGuard
- Web framework: **Flask**

### Code style

- Python 3.9+
- CAN bus safety comes first — comment any command that can affect vehicle control
- Mark DANGER: lines that control HV contactors, steering, or braking with `# ⚠️ DANGER`

### PR checklist

- [ ] Tested on actual hardware (or indicate which hardware)
- [ ] CAN commands verified against vehicle
- [ ] Dangerous operations clearly marked in comments
- [ ] README updated if adding new features

## ⚠️ Safety

This project interacts with a vehicle's CAN bus. Incorrect commands can cause unexpected vehicle behavior. All contributors and users assume full responsibility for their actions. When in doubt, ask in the issue tracker.

## 📜 License

MIT — contributions are licensed under the same terms.
