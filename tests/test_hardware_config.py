from tx5dr_device_panel.config import HardwareConfig
from tx5dr_device_panel.render.oled_luma import OledLumaBackend
from PIL import Image


def test_hardware_config_defaults_cover_i2c_ssd1306():
    config = HardwareConfig()

    assert config.controller == "ssd1306"
    assert config.protocol == "i2c"
    assert config.i2c_bus == 1
    assert config.i2c_address == 0x3C


def test_sh1106_spi_config_keeps_column_offset_and_throttle_defaults():
    config = HardwareConfig(controller="sh1106", protocol="spi", sh1106_column_offset=2)

    assert config.sh1106_column_offset == 2
    assert OledLumaBackend.max_normal_fps == 1.0
    assert OledLumaBackend.max_tx_fps == 2.0


def test_oled_throttle_keeps_pending_last_frame():
    backend = object.__new__(OledLumaBackend)
    backend.config = HardwareConfig()
    backend.max_normal_fps = 1.0
    backend.max_tx_fps = 2.0
    backend.device = FakeDevice()
    backend._last_image = None
    backend._pending_image = None
    backend._pending_tx_active = False
    backend._last_flush = 0.0

    first = Image.new("1", (128, 64), 0)
    second = Image.new("1", (128, 64), 1)

    assert backend.display(first) is True
    assert backend.display(second) is False
    assert backend._pending_image is not None
    assert backend.flush_pending() is True
    assert backend.device.count == 2


class FakeDevice:
    def __init__(self):
        self.count = 0

    def display(self, image):
        self.count += 1
