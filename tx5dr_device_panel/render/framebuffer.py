from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFont

from tx5dr_device_panel.models import DrawCommand, RenderFrame


class FramebufferRenderer:
    def __init__(self) -> None:
        self.font = ImageFont.load_default()

    def render(self, frame: RenderFrame) -> Image.Image:
        image = Image.new("1", (frame.width, frame.height), 0)
        draw = ImageDraw.Draw(image)
        for command in frame.commands:
            self._draw_command(image, draw, command)
        return image

    def _draw_command(self, image: Image.Image, draw: ImageDraw.ImageDraw, command: DrawCommand) -> None:
        if command.kind == "text" and command.text is not None:
            draw.text((command.x, command.y), command.text, font=self.font, fill=command.fill)
        elif command.kind == "line":
            draw.line((command.x, command.y, command.x2, command.y2), fill=command.fill)
        elif command.kind == "rect":
            draw.rectangle((command.x, command.y, command.x2, command.y2), outline=command.fill)
        elif command.kind == "filled_rect":
            draw.rectangle((command.x, command.y, command.x2, command.y2), fill=command.fill)
        elif command.kind == "bar_graph":
            self._bar_graph(draw, command)
        elif command.kind == "invert_region":
            self._invert_region(image, command)

    def _bar_graph(self, draw: ImageDraw.ImageDraw, command: DrawCommand) -> None:
        width = max(0, command.width or 0)
        height = max(0, command.height or 0)
        value = min(1.0, max(0.0, command.value or 0.0))
        draw.rectangle((command.x, command.y, command.x + width, command.y + height), outline=1)
        fill_width = int(width * value)
        if fill_width > 0:
            draw.rectangle((command.x, command.y, command.x + fill_width, command.y + height), fill=1)

    def _invert_region(self, image: Image.Image, command: DrawCommand) -> None:
        if command.x2 is None or command.y2 is None:
            return
        box = (command.x, command.y, command.x2 + 1, command.y2 + 1)
        region = image.crop(box)
        image.paste(ImageChops.invert(region), box)
