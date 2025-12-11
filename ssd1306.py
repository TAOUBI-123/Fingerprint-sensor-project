# ssd1306.py - Minimal driver
from micropython import const
import framebuf

class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def init_display(self):
        for cmd in (0xAE, 0x20, 0x00, 0x40, 0xA1, 0xC8, 0x81, 0xFF, 0xA4, 0xA6, 0xD5, 0x80, 0x8D, 0x14, 0xAF):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self): self.write_cmd(0xAE)
    def poweron(self): self.write_cmd(0xAF)
    def contrast(self, contrast): self.write_cmd(0x81); self.write_cmd(contrast)
    def invert(self, invert): self.write_cmd(0xA6 | (invert & 1))
    def show(self):
        x0, x1 = 0, self.width - 1
        if self.width == 64: x0 += 32; x1 += 32
        self.write_cmd(0x21); self.write_cmd(x0); self.write_cmd(x1)
        self.write_cmd(0x22); self.write_cmd(0); self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)

class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b'\x40', None]
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80; self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        self.i2c.writevto(self.addr, self.write_list)