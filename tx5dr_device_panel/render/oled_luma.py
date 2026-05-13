from __future__ import annotations

import time
from dataclasses import dataclass

from PIL import Image
from luma.oled.device import sh1106 as _LumaSH1106

from tx5dr_device_panel.config import HardwareConfig


@dataclass
class OledLumaBackend:
    config: HardwareConfig
    max_normal_fps: float = 1.0
    max_tx_fps: float = 2.0

    def __post_init__(self) -> None:
        self.device = self._create_device()
        self._last_image: Image.Image | None = None
        self._pending_image: Image.Image | None = None
        self._pending_tx_active = False
        self._last_flush = 0.0

    def display(self, image: Image.Image, tx_active: bool = False) -> bool:
        now = time.monotonic()
        fps = self.max_tx_fps if tx_active else self.max_normal_fps
        if now - self._last_flush < 1.0 / fps:
            self._pending_image = image.copy()
            self._pending_tx_active = tx_active
            return False
        return self.flush(image, tx_active)

    def flush_pending(self) -> bool:
        if self._pending_image is None:
            return False
        image = self._pending_image
        tx_active = self._pending_tx_active
        self._pending_image = None
        self._pending_tx_active = False
        return self.flush(image, tx_active)

    def flush(self, image: Image.Image, tx_active: bool = False) -> bool:
        if self._last_image is not None and image.tobytes() == self._last_image.tobytes():
            return False
        self.device.display(image)
        self._last_image = image.copy()
        self._last_flush = time.monotonic()
        return True

    def _create_device(self):
        from luma.core.interface.serial import i2c, spi
        from luma.oled.device import ssd1306

        protocol = self.config.protocol.lower()
        if protocol == "i2c":
            serial = i2c(port=self.config.i2c_bus, address=self.config.i2c_address)
        elif protocol == "spi":
            kwargs = {
                "port": self.config.spi_port,
                "device": self.config.spi_device,
                "gpio_DC": self.config.spi_dc,
            }
            if self.config.spi_rst is not None:
                kwargs["gpio_RST"] = self.config.spi_rst
            if self.config.spi_cs is not None:
                kwargs["gpio_CS"] = self.config.spi_cs
            serial = spi(**kwargs)
        else:
            raise ValueError(f"Unsupported OLED protocol: {self.config.protocol}")

        controller = self.config.controller.lower()
        if controller == "ssd1306":
            return ssd1306(serial, width=128, height=64)
        if controller == "sh1106":
            return _configurable_sh1106(
                serial,
                width=128,
                height=64,
                column_offset=self.config.sh1106_column_offset,
            )
        raise ValueError(f"Unsupported OLED controller: {self.config.controller}")


class _configurable_sh1106(_LumaSH1106):
    def __init__(self, *args, column_offset: int = 2, **kwargs) -> None:
        self._column_offset = max(0, min(15, column_offset))
        super().__init__(*args, **kwargs)

    def display(self, image: Image.Image) -> None:
        assert image.mode == self.mode
        assert image.size == self.size

        image = self.preprocess(image)
        set_page_address = 0xB0
        image_data = image.getdata()
        pixels_per_page = self._w * 8
        buf = bytearray(self._w)
        low_column = self._column_offset & 0x0F
        high_column = 0x10 | (self._column_offset >> 4)

        for y in range(0, int(self._pages * pixels_per_page), pixels_per_page):
            self.command(set_page_address, low_column, high_column)
            set_page_address += 1
            offsets = [y + self._w * i for i in range(8)]

            for x in range(self._w):
                buf[x] = (
                    (image_data[x + offsets[0]] and 0x01)
                    | (image_data[x + offsets[1]] and 0x02)
                    | (image_data[x + offsets[2]] and 0x04)
                    | (image_data[x + offsets[3]] and 0x08)
                    | (image_data[x + offsets[4]] and 0x10)
                    | (image_data[x + offsets[5]] and 0x20)
                    | (image_data[x + offsets[6]] and 0x40)
                    | (image_data[x + offsets[7]] and 0x80)
                )

            self.data(list(buf))
