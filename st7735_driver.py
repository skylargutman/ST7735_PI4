import time
import lgpio
import numpy as np
from PIL import Image

DC   = 24
RST  = 25
CS   = 23
MOSI = 10
SCLK = 11

WIDTH  = 128
HEIGHT = 160

_h           = None
_initialized = False


def _write_byte(b):
    for i in range(7, -1, -1):
        lgpio.gpio_write(_h, MOSI, (b >> i) & 1)
        lgpio.gpio_write(_h, SCLK, 1)
        lgpio.gpio_write(_h, SCLK, 0)


def _write_bytes(data):
    for b in data:
        _write_byte(b)


def _cmd(c):
    lgpio.gpio_write(_h, DC, 0)
    lgpio.gpio_write(_h, CS, 0)
    _write_byte(c)
    lgpio.gpio_write(_h, CS, 1)


def _data(d):
    lgpio.gpio_write(_h, DC, 1)
    lgpio.gpio_write(_h, CS, 0)
    _write_bytes(d if isinstance(d, list) else [d])
    lgpio.gpio_write(_h, CS, 1)


def _reset():
    lgpio.gpio_write(_h, CS, 1)
    lgpio.gpio_write(_h, RST, 1); time.sleep(0.5)
    lgpio.gpio_write(_h, RST, 0); time.sleep(0.5)
    lgpio.gpio_write(_h, RST, 1); time.sleep(0.5)


def _initR():
    _reset()
    _cmd(0x01); time.sleep(0.15)
    _cmd(0x11); time.sleep(0.5)
    _cmd(0xB1); _data([0x01, 0x2C, 0x2D])
    _cmd(0xB2); _data([0x01, 0x2C, 0x2D])
    _cmd(0xB3); _data([0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D])
    _cmd(0xB4); _data([0x07])
    _cmd(0xC0); _data([0xA2, 0x02, 0x84])
    _cmd(0xC1); _data([0xC5])
    _cmd(0xC2); _data([0x0A, 0x00])
    _cmd(0xC3); _data([0x8A, 0x2A])
    _cmd(0xC4); _data([0x8A, 0xEE])
    _cmd(0xC5); _data([0x0E])
    _cmd(0x20)
    _cmd(0x36); _data([0xC8])
    _cmd(0x3A); _data([0x05])
    _cmd(0x2A); _data([0x00, 0x00, 0x00, 0x7F])
    _cmd(0x2B); _data([0x00, 0x00, 0x00, 0x9F])
    _cmd(0xE0); _data([0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22,
                       0x1f, 0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
    _cmd(0xE1); _data([0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e,
                       0x30, 0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10])
    _cmd(0x29); time.sleep(0.1)
    _cmd(0x13); time.sleep(0.1)


def init(force=False):
    """Open GPIO and send init sequence. Safe to call multiple times —
    skips hardware reset if already initialised unless force=True."""
    global _h, _initialized

    if _initialized and not force:
        return

    try:
        lgpio.gpiochip_close(_h)
    except Exception:
        pass

    _h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(_h, DC)
    lgpio.gpio_claim_output(_h, RST)
    lgpio.gpio_claim_output(_h, CS)
    lgpio.gpio_claim_output(_h, MOSI)
    lgpio.gpio_claim_output(_h, SCLK)
    lgpio.gpio_write(_h, CS, 1)

    _initR()
    _initialized = True


def show(img: Image.Image):
    """Push a PIL Image (128x160 RGB) to the display.
    Calls init() automatically if not yet initialised."""
    init()

    arr = img.convert('RGB').__array_interface__
    img = img.convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)

    # BGR565 — this display expects blue in high bits
    color = ((b & 0xF8) << 8) | ((g & 0xFC) << 3) | (r >> 3)
    lo = (color & 0xFF).flatten().astype(np.uint8)
    hi = (color >> 8).flatten().astype(np.uint8)
    buf = np.empty(WIDTH * HEIGHT * 2, dtype=np.uint8)
    buf[0::2] = lo
    buf[1::2] = hi
    buf_list = buf.tolist()

    lgpio.gpio_write(_h, CS, 0)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2A)
    lgpio.gpio_write(_h, DC, 1)
    for byte in [0x00, 0x00, 0x00, 0x7F]: _write_byte(byte)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2B)
    lgpio.gpio_write(_h, DC, 1)
    for byte in [0x00, 0x00, 0x00, 0x9F]: _write_byte(byte)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2C)
    lgpio.gpio_write(_h, DC, 1)
    _write_bytes(buf_list)
    lgpio.gpio_write(_h, CS, 1)


def cleanup():
    global _initialized
    if _h is not None:
        try:
            lgpio.gpiochip_close(_h)
        except Exception:
            pass
    _initialized = False
