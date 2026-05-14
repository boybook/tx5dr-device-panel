# TX-5DR Device Panel

Python MVP for a read-only TX-5DR `128x64` OLED status panel.

## Scope

- Talks to the TX-5DR server device API (`/api/device-ui/*`).
- Maintains a local state store from bootstrap snapshots and websocket events.
- Renders Access, FT8, and Voice status pages to a `128x64` frame.
- Uses `station.callsign` from the server device snapshot to highlight FT8 messages involving
  the local station; the panel does not accept a callsign override.
- Uses the server-provided FT8 frame location fields for country/region labels; Python does
  not calculate countries from callsigns.
- Has a global UI `language` setting (`zh`/`en`) that is shared by current and future labels.
- Supports deterministic PNG snapshots, pygame preview, and luma.oled hardware output.
- Supports SSD1306/SH1106 over I2C or SPI by configuration.
- Provides a Linux NetworkManager control interface for future user-initiated Wi-Fi/hotspot
  actions; current OLED UI remains display-only.

No pairing code, login flow, or panel-side control action exists in this MVP.

## Quick Start

```bash
uv venv
uv pip install -e ".[dev]"
tx5dr-device-panel snapshot --fixture fixtures/ft8.json --output out/ft8.png
tx5dr-device-panel --language zh preview --fixture fixtures/access.json
```

Linux images that enable future NetworkManager control should install:

```bash
uv pip install -e ".[network-control]"
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
language: "zh"
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

## OLED Hardware Setup

The OLED backend uses `luma.oled`. For a real I2C OLED panel, configure
`display.backend: "oled"` and set the `hardware` section to match the detected Linux I2C bus.

### 1. Check I2C Devices

Install I2C tools on the device:

```bash
sudo apt update
sudo apt install -y i2c-tools
```

List available I2C buses:

```bash
ls /dev/i2c-*
i2cdetect -l
```

Example output:

```text
/dev/i2c-3  /dev/i2c-5  /dev/i2c-6
i2c-3 i2c mv64xxx_i2c adapter I2C adapter
i2c-5 i2c DesignWare HDMI     I2C adapter
i2c-6 i2c mv64xxx_i2c adapter I2C adapter
```

Scan each candidate bus until the OLED address appears:

```bash
i2cdetect -y 3
i2cdetect -y 5
i2cdetect -y 6
```

Most SSD1306/SH1106 modules show up as `3c` or `3d`:

```text
30: -- -- -- -- -- -- -- -- -- -- -- -- 3c -- -- --
```

If the address appears on `/dev/i2c-3`, use `i2c_bus: 3`. If it appears as `3c`, use
`i2c_address: 0x3C`; if it appears as `3d`, use `i2c_address: 0x3D`.

### 2. Write Production Config

Create `/etc/tx5dr/device-panel.yaml`:

```bash
sudo mkdir -p /etc/tx5dr
sudo nano /etc/tx5dr/device-panel.yaml
```

Example for SH1106 over I2C on `/dev/i2c-3`:

```yaml
server:
  base_url: "http://192.168.31.101:8076"
  device_id: "tx5dr-oled-panel"
  token_file: "/home/kickpi/tx5dr-device-panel/.device-ui-token"
  reconnect_seconds: 2.0

language: "zh"

display:
  backend: "oled"
  width: 128
  height: 64
  scale: 4

hardware:
  controller: "sh1106"
  protocol: "i2c"
  i2c_bus: 3
  i2c_address: 0x3C
  sh1106_column_offset: 2
```

Use `controller: "ssd1306"` for SSD1306 panels. For SH1106 panels, keep
`sh1106_column_offset: 2` first; if the image is horizontally shifted, try `0` or another
small value.

### 3. Check Permissions

The runtime user must be able to open `/dev/i2c-*`. Prefer adding the user to the `i2c`
group:

```bash
sudo usermod -aG i2c "$USER"
```

Log out and back in after changing groups. For a quick permission check:

```bash
groups
test -r /dev/i2c-3 && test -w /dev/i2c-3 && echo "i2c ok"
```

### 4. Smoke Test the OLED

First render a fixture directly to the physical OLED without requiring a live server:

```bash
python - <<'PY'
import json
from pathlib import Path

from tx5dr_device_panel.config import HardwareConfig
from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.render.oled_luma import OledLumaBackend
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot

payload = json.loads(Path("fixtures/access.json").read_text())
snapshot = PanelStore().apply({"type": "snapshot", "payload": payload})
image = FramebufferRenderer().render(render_snapshot(snapshot, language="zh"))

backend = OledLumaBackend(
    HardwareConfig(
        controller="sh1106",
        protocol="i2c",
        i2c_bus=3,
        i2c_address=0x3C,
        sh1106_column_offset=2,
    )
)
backend.flush(image)
PY
```

Change `controller`, `i2c_bus`, and `i2c_address` to match the detected panel.

### 5. Run Live Mode

After the OLED smoke test passes and `.device-ui-token` exists:

```bash
tx5dr-device-panel --config /etc/tx5dr/device-panel.yaml live
```

The panel should show:

- Access page when the TX-5DR engine is stopped or the server cannot be reached.
- FT8 Monitor page when the engine is running in FT8/digital mode.
- Voice Monitor page when the engine is running in voice mode.

## Troubleshooting

- `FileNotFoundError: /dev/i2c-1`: the configured `i2c_bus` does not exist. Use a bus shown
  by `ls /dev/i2c-*`.
- `OSError: [Errno 121] Remote I/O error`: wrong bus/address, no power, or SDA/SCL wiring is
  wrong. Confirm with `i2cdetect -y <bus>`.
- OLED is blank but `i2cdetect` sees the address: verify `display.backend: "oled"` and the
  correct `controller`.
- Image is horizontally shifted on SH1106: adjust `sh1106_column_offset`.
- Access page stays on screen: verify `server.base_url`, `token_file`, and that the TX-5DR
  server device API is running.
