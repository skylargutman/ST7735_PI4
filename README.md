# ST7735R 1.8" LCD Display on Raspberry Pi 4B
### A complete setup guide including wiring, driver code, and hard-won lessons

**Platform:** Raspberry Pi 4B  
**Display:** ST7735R 1.8" 128×160 SPI LCD with onboard SD card reader  
**OS:** Raspberry Pi OS Bookworm 64-bit  
**Language:** Python 3.11  
**Refresh rate:** ~2 seconds full screen (Python bit-bang limitation)

---

## Table of Contents
1. [Why This Guide Exists](#why-this-guide-exists)
2. [Hardware](#hardware)
3. [OS Setup](#os-setup)
4. [Wiring](#wiring)
5. [Software Dependencies](#software-dependencies)
6. [The Driver](#the-driver)
7. [Using the Driver](#using-the-driver)
8. [How the Driver Works](#how-the-driver-works)
9. [Simulink Integration](#simulink-integration)
10. [Troubleshooting & Lessons Learned](#troubleshooting--lessons-learned)

---

## Why This Guide Exists

Getting the ST7735R working on a Raspberry Pi 4B is surprisingly difficult. The
display hardware is simple and well documented, but nearly every Python library
available has some combination of broken APIs, wrong init sequences, or
incompatibility with the Pi's hardware SPI driver. This guide documents what
actually works after extensive debugging, so you don't have to repeat the same
painful trial and error.

**The short version of what we discovered:**

The Pi's hardware SPI kernel driver toggles the CS (chip select) line between
every transfer, which resets the display controller's internal GRAM write
pointer. This makes it impossible to write a full frame of pixel data using the
standard `spidev` library or `lgpio.spi_write`. The solution is pure bit-bang
SPI for all communication, with CS controlled manually throughout.

---

## Hardware

- Raspberry Pi 4B (any RAM variant)
- ST7735R 1.8" 128×160 SPI LCD module (black PCB variant with onboard SD card reader)
- Female-to-female jumper wires
- 5V/3A USB-C power supply for the Pi

**Display module pins:**  
`VCC | GND | SCL | SDA | DC | RES | CS` plus SD card reader pins `MISO | SCLK | MOSI | CS`

---

## OS Setup

Use **Raspberry Pi OS Bookworm 64-bit (Desktop)** — this is the MathWorks-certified
version if you plan to use Simulink. Do not use Trixie (Debian 13) yet as
MathWorks support lags behind new OS releases.

Flash using Raspberry Pi Imager with these settings:

- Hostname: your choice (e.g. `PiControlTest`)
- Username + password: set and remember these
- WiFi SSID + password: fill in exactly
- SSH: enabled, password authentication

After first boot, SSH in and update fully:

```bash
sudo apt update && sudo apt full-upgrade -y
```

Enable SPI:

```bash
sudo raspi-config
# Interface Options → SPI → Yes → Finish
sudo reboot
```

Verify SPI is active after reboot:

```bash
ls /dev/spi*
# should show /dev/spidev0.0 and /dev/spidev0.1
```

---

## Wiring

> **Important:** The ST7735R runs on 3.3V logic. The Pi 4B GPIO is also 3.3V.
> Connect VCC to the Pi's 3.3V pin — NOT 5V. No level shifter is needed.

The display CS pin must be connected to a regular GPIO pin (not CE0/CE1) so we
can control it manually in software. We use GPIO 23 (physical pin 16).

| Display pin | Pi GPIO | Physical pin | Notes |
|---|---|---|---|
| VCC | 3.3V | Pin 1 | Power |
| GND | GND | Pin 6 | Ground |
| SCL | GPIO 11 | Pin 23 | SPI SCLK |
| SDA | GPIO 10 | Pin 19 | SPI MOSI |
| DC | GPIO 24 | Pin 18 | Data/Command select |
| RES | GPIO 25 | Pin 22 | Reset |
| CS (LCD) | GPIO 23 | Pin 16 | Chip select — software controlled |
| MISO (SD) | GPIO 9 | Pin 21 | SD card only |
| CS (SD) | GPIO 7 | Pin 26 | SD card chip select |

---

## Software Dependencies

```bash
sudo pip3 install lgpio numpy pillow --break-system-packages
```

- `lgpio` — GPIO control for bit-bang SPI
- `numpy` — fast pixel format conversion
- `pillow` — image and text rendering

> **Note:** Do NOT attempt to use `lgpio.spi_open` for pixel data while
> `dtparam=spi=on` is active. The kernel SPI driver claims GPIO 8, 10, and 11,
> conflicting with lgpio's attempts to claim those same pins as outputs.
> All communication in this driver is pure bit-bang through lgpio GPIO calls only.

---

## The Driver

```python
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
_spi_h       = None
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
    global _h, _spi_h, _initialized

    if _initialized and not force:
        return

    try:
        lgpio.spi_close(_spi_h)
    except Exception:
        pass
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

    arr = np.array(img.convert('RGB'), dtype=np.uint8)
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)

    # BGR565 — this display expects blue in the high bits
    color = ((b & 0xF8) << 8) | ((g & 0xFC) << 3) | (r >> 3)
    lo = (color & 0xFF).flatten().astype(np.uint8)
    hi = (color >> 8).flatten().astype(np.uint8)
    buf = np.empty(WIDTH * HEIGHT * 2, dtype=np.uint8)
    buf[0::2] = lo
    buf[1::2] = hi

    lgpio.gpio_write(_h, CS, 0)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2A)
    lgpio.gpio_write(_h, DC, 1)
    for byte in [0x00, 0x00, 0x00, 0x7F]: _write_byte(byte)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2B)
    lgpio.gpio_write(_h, DC, 1)
    for byte in [0x00, 0x00, 0x00, 0x9F]: _write_byte(byte)
    lgpio.gpio_write(_h, DC, 0); _write_byte(0x2C)
    lgpio.gpio_write(_h, DC, 1)
    _write_bytes(buf.tolist())
    lgpio.gpio_write(_h, CS, 1)


def cleanup():
    """Release all GPIO resources."""
    global _initialized
    if _h is not None:
        try:
            lgpio.gpiochip_close(_h)
        except Exception:
            pass
    _initialized = False
```

---

## Using the Driver

```python
import st7735_driver as lcd
from PIL import Image, ImageDraw, ImageFont

# show() calls init() automatically on first call
img = Image.new('RGB', (lcd.WIDTH, lcd.HEIGHT), (0, 0, 0))
draw = ImageDraw.Draw(img)
font = ImageFont.load_default()

draw.rectangle((0, 0, lcd.WIDTH, 20), fill=(200, 100, 0))
draw.text((4, 4), "HELLO WORLD", font=font, fill=(0, 0, 0))
draw.text((10, 60), "42.0", font=font, fill=(255, 255, 255))

lcd.show(img)      # first call initialises automatically
lcd.show(img)      # subsequent calls skip hardware reset

lcd.cleanup()      # release GPIO — always call when done
```

For a persistent display daemon, call `show()` in a loop. `init()` only runs
once — subsequent `show()` calls go straight to the pixel write.

To force a full hardware reset at any time:

```python
lcd.init(force=True)
```

---

## How the Driver Works

### SPI basics

SPI uses four signals: SCLK (clock), MOSI (data out), MISO (data in), and CS
(chip select). The master (Pi) drives the clock and holds CS low while talking
to a device. The ST7735R also has a DC (data/command) pin — when DC is low the
byte is interpreted as a command, when high it is pixel data.

### Why pure bit-bang

The Pi's hardware SPI kernel driver automatically toggles CS between every
transfer call. For this display this is fatal — each time CS goes high and low
between the window-set commands and the pixel write, the display controller
resets its GRAM pointer to zero. Only the first chunk of pixels lands in the
right place, producing stripes or snow.

Bit-banging gives complete manual control over CS, DC, SCLK, and MOSI. CS is
held low across the entire transaction from the window-set commands through the
last pixel byte. This matches what an Arduino does natively, which is why
Arduino implementations work immediately while Pi implementations struggle.

### Why not lgpio.spi_write for pixels

`lgpio.spi_open` opens `/dev/spidev0.0` — the kernel SPI device on GPIO 8/10/11.
Attempting to use this while lgpio also claims those pins as outputs causes a
GPIO busy conflict. All pixel data is therefore bit-banged through the same
`_write_byte` function used for commands.

### Performance

Pure Python bit-bang over 40,960 bytes (128×160×2) results in approximately 2
second full screen refresh. This is a known limitation of the Python interpreter
overhead per GPIO call. A C shared library using the same approach would reduce
this to under 100ms. For the current application (control system state display)
this is acceptable.

### Pixel format — BGR565

The ST7735R uses BGR565 — 16 bits per pixel. This display expects **blue in
the high bits**, not red. This was a hard-won discovery — using standard RGB565
ordering produces color-inverted images.

```python
# Correct for this display:
color = ((b & 0xF8) << 8) | ((g & 0xFC) << 3) | (r >> 3)
```

### Idempotent init

The `_initialized` flag means `init()` is safe to call multiple times without
reflashing the hardware. `show()` calls `init()` internally so callers never
need to call it explicitly. `cleanup()` resets the flag so the next `show()`
re-initialises cleanly.

---

## Simulink Integration

This driver is used as a Git submodule in the
[picontrol](https://github.com/skylargutman/picontrol) repository. The Simulink
model sends display data via UDP to a Python daemon (`update_display.py`) which
calls `show()` to render live system state.

The daemon pattern avoids calling `init()` repeatedly:

```python
# update_display.py pattern
import st7735_driver as lcd

while True:
    val = receive_udp()    # blocks until data arrives
    img = render(val)
    lcd.show(img)          # init() skipped after first call
```

### pigpiod conflict

If the Simulink Raspberry Pi support package is running, it requires `pigpiod`
which claims the GPIO chip. This conflicts with lgpio. The display daemon must
be started **before** pigpiod claims the pins, or pigpiod must be stopped before
running the display driver standalone.

In normal operation the start script handles ordering:

```bash
~/picontrol/scripts/start.sh
```

---

## Troubleshooting & Lessons Learned

### GPIO busy error

Another process is holding the GPIO chip open. Either a previous Python script
crashed without calling `cleanup()`, or `pigpiod` is running. Kill lingering
processes first:

```bash
pkill -f update_display.py
sudo systemctl stop pigpiod
```

If the error persists after killing processes, reboot — the OS holds GPIO claims
until the owning process exits cleanly.

### White screen after init

Pixel data is not reaching the display. Most likely cause: CS is toggling
mid-transfer. Ensure you are using pure bit-bang with CS held low across the
entire pixel write sequence.

### Snow (random colored pixels)

The pixel data is arriving but the color bytes are in the wrong order. Check
the BGR565 formula — this display expects blue in the high bits. Also verify
that `buf[0::2] = lo` and `buf[1::2] = hi` are assigned correctly.

### Blue flash then white screen

Hardware reset is working but pixel write is failing. See white screen above.

### Stripe of color instead of full screen

CS toggled between the window-set command and the pixel data. Keep CS low for
the entire sequence from the `0x2A` column command through the last pixel byte.

### Colors wrong (red looks blue)

BGR vs RGB byte order. Use:

```python
color = ((b & 0xF8) << 8) | ((g & 0xFC) << 3) | (r >> 3)
```

Not the RGB equivalent with `r` in the high bits.

### Libraries tried and abandoned

These were tested and did not work reliably for this specific display:

- `st7735` (pip) — broken API, missing gpiodevice dependency, wrong init for R variant
- `adafruit-circuitpython-st7735r` — BusDisplay API incompatibility, does not accept cs or dc kwargs
- `adafruit-circuitpython-rgb-display` — same BusDisplay issue
- `luma.lcd` — unsupported display mode for 128×160, reset timing insufficient
- Raw `spidev` alone — hardware CS toggling breaks GRAM writes
- `lgpio.spi_write` for pixel data — GPIO busy conflict with kernel SPI driver

### The Arduino sanity check

Wire the display to an Arduino Uno using the Adafruit ST7735 library with
`initR(INITR_BLACKTAB)`. If it works on the Arduino and not the Pi, the display
hardware is fine and the problem is in the Pi SPI driver interaction — which is
exactly the situation that led to this driver being written.

---

## Reference

- ST7735R datasheet — search "ST7735R datasheet Sitronix"
- Adafruit ST7735 Arduino library — the `_initR()` sequence is derived from the INITR_BLACKTAB path
- lgpio documentation — http://abyz.me.uk/lg/py_lgpio.html
- picontrol repository — https://github.com/skylargutman/picontrol

---

*Documented as part of FAU Senior Design Project: Parametric Retrofit of Lab Equipment for Remote Control*  
*Author: Skylar Gutman — March 2026*
