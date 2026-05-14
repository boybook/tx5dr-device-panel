# TX-5DR Device Panel

Python MVP for a read-only TX-5DR `128x64` OLED status panel.

## Scope

- Talks to the TX-5DR server device API (`/api/device-ui/*`).
- Maintains a local state store from bootstrap snapshots and websocket events.
- Renders Access, FT8, and Voice status pages to a `128x64` frame.
- Uses `station.callsign` from the server device snapshot to highlight FT8 messages involving
  the local station; the panel does not accept a callsign override.
- Supports deterministic PNG snapshots, pygame preview, and luma.oled hardware output.
- Supports SSD1306/SH1106 over I2C or SPI by configuration.

No pairing code, login flow, network mutation, or panel-side control action exists in this MVP.

## Quick Start

```bash
uv venv
uv pip install -e ".[dev]"
tx5dr-device-panel snapshot --fixture fixtures/ft8.json --output out/ft8.png
tx5dr-device-panel preview --fixture fixtures/access.json
```

## Configuration

Precedence is CLI > environment > YAML > defaults.

- Production YAML: `/etc/tx5dr/device-panel.yaml`
- Development YAML: `./device-panel.dev.yaml`
- Environment prefix: `TX5DR_PANEL_`
- Font: Fusion Pixel Font 8px monospaced `zh_hans` TTF is bundled under SIL OFL 1.1 for
  English and Chinese text. Font license files are in
  `tx5dr_device_panel/assets/fonts/fusion-pixel-font/`.

Example:

```yaml
server:
  base_url: "http://127.0.0.1:8076"
  device_id: "panel-1"
  token_file: "/var/lib/tx5dr/.device-ui-token"
display:
  width: 128
  height: 64
  backend: "preview"
  font_path: "./tx5dr_device_panel/assets/fonts/fusion-pixel-font/fusion-pixel-8px-monospaced-zh_hans.ttf"
  font_size: 8
hardware:
  controller: "sh1106"
  protocol: "i2c"
  i2c_bus: 1
  i2c_address: 0x3C
  sh1106_column_offset: 2
```
