# ST7735R 1.8" LCD Display on Raspberry Pi 4B
### A complete setup guide including wiring, driver code, and hard-won lessons

**Platform:** Raspberry Pi 4B  
**Display:** ST7735R 1.8" 128×160 SPI LCD with onboard SD card reader  
**OS:** Raspberry Pi OS Bookworm 64-bit  
**Language:** Python 3.11  
**Refresh rate achieved:** ~74ms full screen (≈13 fps)

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
9. [Troubleshooting & Lessons Learned](#troubleshooting--lessons-learned)

---

## Why This Guide Exists

Getting the ST7735R working on a Raspberry Pi 4B is surprisingly difficult. The display hardware is simple and well documented, but nearly every Python library available has some combination of broken APIs, wrong init sequences, or incompatibility with the Pi's hardware SPI driver. This guide documents what actually works after extensive debugging, so you don't have to repeat the same painful trial and error.

**The short version of what we discovered:**

The Pi's hardware SPI kernel driver toggles the CS (chip select) line between every transfer, which resets the display controller's internal GRAM write pointer. This makes it impossible to write a full frame of pixel data using the standard `spidev` library. The solution is to use bit-banged SPI for commands and `lgpio`'s SPI for bulk pixel data, with CS controlled manually throughout.

---

## Hardware

- Raspberry Pi 4B (any RAM variant)
- ST7735R 1.8" 128×160 SPI LCD module (black PCB variant with onboard SD card reader)
- Female-to-female jumper wires
- 5V/3A USB-C power supply for the Pi (do NOT power from a computer USB port — the Pi 4B draws up to 1.5A under load, exceeding what USB 3.0 can provide)

**Display module pins:**
`VCC | GND | SCL | SDA | DC | RES | CS` plus SD card reader pins `MISO | SCLK | MOSI | CS`

---

## OS Setup

Use **Raspberry Pi OS Bookworm 64-bit (Desktop)** — this is the MathWorks-certified version if you plan to use Simulink later. Do not use Trixie (Debian 13) yet as MathWorks support lags behind new OS releases.

Flash using Raspberry Pi Imager with these settings:

- Hostname: your choice (e.g. `PiControlTest`)
- Username + password: set and remember these
- WiFi SSID + password: fill in exactly
- SSH: enabled, password authentication

After first boot, SSH in from your PC:

```bash
ssh yourusername@yourhostname.local
```

Then update fully before doing anything else:

```bash
sudo apt update
sudo apt full-upgrade -y
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

> **Important:** The ST7735R runs on 3.3V logic. The Pi 4B GPIO is also 3.3V. Connect VCC to the Pi's 3.3V pin — NOT 5V. No level shifter is needed.

The display CS pin must be connected to a regular GPIO pin (not CE0/CE1) so we can control it manually in software. We use GPIO23 (physical pin 16).

| Display pin | Pi GPIO | Physical pin | Notes |
|---|---|---|---|
| VCC | 3.3V | Pin 1 | Power |
| GND | GND | Pin 6 | Ground |
| SCL | GPIO11 | Pin 23 | SPI SCLK |
| SDA | GPIO10 | Pin 19 | SPI MOSI |
| DC | GPIO24 | Pin 18 | Data/Command select |
| RES | GPIO25 | Pin 22 | Reset |
| CS (LCD) | GPIO23 | Pin 16 | Chip select — software controlled |
| MISO (SD) | GPIO9 | Pin 21 | SD card only |
| CS (SD) | GPIO7 | Pin 26 | SD card chip select |

---

## Software Dependencies

```bash
sudo pip3 install lgpio numpy pillow --break-system-packages
```

- `lgpio` — GPIO and SPI control, bypasses the kernel SPI driver
- `numpy` — fast pixel format conversion
- `pillow` — image and text rendering

---

## The Driver

Save this as `st7735_driver.py` in your project directory:

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

h = None
spi_h = None

def init():
    global h, spi_h
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, DC)
    lgpio.gpio_claim_output(h, RST)
    lgpio.gpio_claim_output(h, CS)
    lgpio.gpio_claim_output(h, MOSI)
    lgpio.gpio_claim_output(h, SCLK)
    lgpio.gpio_write(h, CS, 1)
    spi_h = lgpio.spi_open(0, 0, 8000000, 0)
    _initR()

def cleanup():
    lgpio.spi_close(spi_h)
    lgpio.gpiochip_close(h)

def _write_byte(b):
    for i in range(7, -1, -1):
        lgpio.gpio_write(h, MOSI, (b >> i) & 1)
        lgpio.gpio_write(h, SCLK, 1)
        lgpio.gpio_write(h, SCLK, 0)

def _cmd(c):
    lgpio.gpio_write(h, DC, 0)
    lgpio.gpio_write(h, CS, 0)
    _write_byte(c)
    lgpio.gpio_write(h, CS, 1)

def _data(d):
    lgpio.gpio_write(h, DC, 1)
    lgpio.gpio_write(h, CS, 0)
    for b in (d if isinstance(d, list) else [d]):
        _write_byte(b)
    lgpio.gpio_write(h, CS, 1)

def _reset():
    lgpio.gpio_write(h, CS, 1)
    lgpio.gpio_write(h, RST, 1); time.sleep(0.5)
    lgpio.gpio_write(h, RST, 0); time.sleep(0.5)
    lgpio.gpio_write(h, RST, 1); time.sleep(0.5)

def _initR():
    _reset()
    _cmd(0x01); time.sleep(0.15)   # software reset
    _cmd(0x11); time.sleep(0.5)    # sleep out

    _cmd(0xB1); _data([0x01, 0x2C, 0x2D])              # frame rate normal
    _cmd(0xB2); _data([0x01, 0x2C, 0x2D])              # frame rate idle
    _cmd(0xB3); _data([0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D])  # frame rate partial
    _cmd(0xB4); _data([0x07])                           # display inversion off

    _cmd(0xC0); _data([0xA2, 0x02, 0x84])              # power control 1
    _cmd(0xC1); _data([0xC5])                           # power control 2
    _cmd(0xC2); _data([0x0A, 0x00])                    # power control 3
    _cmd(0xC3); _data([0x8A, 0x2A])                    # power control 4
    _cmd(0xC4); _data([0x8A, 0xEE])                    # power control 5
    _cmd(0xC5); _data([0x0E])                           # VCOM

    _cmd(0x20)                                          # display inversion off
    _cmd(0x36); _data([0xC8])                           # MADCTL
    _cmd(0x3A); _data([0x05])                           # 16-bit color

    _cmd(0x2A); _data([0x00, 0x00, 0x00, 0x7F])        # column 0-127
    _cmd(0x2B); _data([0x00, 0x00, 0x00, 0x9F])        # row 0-159

    _cmd(0xE0); _data([0x0f,0x1a,0x0f,0x18,0x2f,0x28,0x20,0x22,
                       0x1f,0x1b,0x23,0x37,0x00,0x07,0x02,0x10])  # gamma +
    _cmd(0xE1); _data([0x0f,0x1b,0x0f,0x17,0x33,0x2c,0x29,0x2e,
                       0x30,0x30,0x39,0x3f,0x00,0x07,0x03,0x10])  # gamma -

    _cmd(0x29); time.sleep(0.1)    # display on
    _cmd(0x13); time.sleep(0.1)    # normal display on

def show(img):
    """Send a PIL Image to the display. Image must be 128x160 RGB."""
    img = img.convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    r = arr[:,:,0].astype(np.uint16)
    g = arr[:,:,1].astype(np.uint16)
    b = arr[:,:,2].astype(np.uint16)
    color = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    hi = (color >> 8).flatten().astype(np.uint8)
    lo = (color & 0xFF).flatten().astype(np.uint8)
    buf = np.empty(WIDTH * HEIGHT * 2, dtype=np.uint8)
    buf[0::2] = lo
    buf[1::2] = hi
    buf_list = buf.tolist()

    # bit-bang window setup commands — hardware SPI cannot be used here
    lgpio.gpio_write(h, CS, 0)
    lgpio.gpio_write(h, DC, 0); _write_byte(0x2A)
    lgpio.gpio_write(h, DC, 1)
    for b in [0x00, 0x00, 0x00, 0x7F]: _write_byte(b)
    lgpio.gpio_write(h, DC, 0); _write_byte(0x2B)
    lgpio.gpio_write(h, DC, 1)
    for b in [0x00, 0x00, 0x00, 0x9F]: _write_byte(b)
    lgpio.gpio_write(h, DC, 0); _write_byte(0x2C)
    lgpio.gpio_write(h, DC, 1)
    lgpio.gpio_write(h, CS, 1)

    # lgpio SPI for fast bulk pixel transfer
    lgpio.gpio_write(h, CS, 0)
    lgpio.gpio_write(h, DC, 1)
    for i in range(0, len(buf_list), 4096):
        lgpio.spi_write(spi_h, buf_list[i:i+4096])
    lgpio.gpio_write(h, CS, 1)
```

---

## Using the Driver

```python
import st7735_driver as lcd
from PIL import Image, ImageDraw, ImageFont
import time

lcd.init()

# create a 128x160 image with Pillow
img = Image.new('RGB', (lcd.WIDTH, lcd.HEIGHT), (0, 0, 0))
draw = ImageDraw.Draw(img)
font = ImageFont.load_default()

# draw whatever you want
draw.rectangle((0, 0, lcd.WIDTH, 20), fill=(200, 100, 0))
draw.text((4, 4), "HELLO WORLD", font=font, fill=(0, 0, 0))
draw.text((10, 60), "42.0", font=font, fill=(255, 255, 255))
draw.text((10, 80), "deg C", font=font, fill=(200, 100, 0))

# send to display (~74ms)
lcd.show(img)

time.sleep(10)
lcd.cleanup()
```

For live updating displays, call `lcd.show(img)` in a loop with a freshly drawn image each iteration.

---

## How the Driver Works

### SPI basics

SPI uses four signals: SCLK (clock), MOSI (data out), MISO (data in), and CS (chip select). The master (Pi) drives the clock and holds CS low while talking to a device. The ST7735R also has a DC (data/command) pin — when DC is low the byte is interpreted as a command, when high it is pixel data.

### Why bit-bang for commands

The Pi's hardware SPI kernel driver automatically toggles CS between every `xfer2()` call. For pixel data this doesn't matter much, but for commands it is fatal — each time CS goes high and low again between a window-set command and the pixel write, the display controller resets its internal GRAM pointer back to zero. This means only the first chunk of pixels lands in the right place, producing the characteristic "stripe" symptom.

Bit-banging gives complete manual control over CS, DC, SCLK, and MOSI, exactly replicating what a microcontroller like an Arduino does natively. The Arduino test worked first time because it uses bit-bang by default.

### Why lgpio SPI for pixels

Once the window is set and the RAMWR (0x2C) command has been sent, the controller simply accepts a raw stream of bytes — no CS toggling or DC changes needed mid-transfer. At this point `lgpio.spi_write()` can push data at 8MHz hardware speed, which is orders of magnitude faster than bit-banging every pixel individually. The combination gives us the best of both worlds.

### Pixel format

The ST7735R uses RGB565 — 16 bits per pixel, 5 bits red, 6 bits green, 5 bits blue. The numpy conversion packs a 128×160 RGB888 PIL image into RGB565 in one vectorized operation, which is much faster than a Python loop over individual pixels.

---

## Troubleshooting & Lessons Learned

### White screen after init

The display initialised but pixel data is not landing. Most likely cause: hardware SPI CS toggling is resetting the GRAM pointer. Make sure you are using the bit-bang approach for all window setup commands and RAMWR.

### Blue flash then white screen

The hardware reset is working (the blue flash is the display clearing during reset). The init sequence is reaching the display. The problem is the pixel write, not the init — see white screen above.

### Stripe of color instead of full screen

The window addressing commands are being accepted but CS is toggling mid-transfer. Each new CS-low cycle restarts the GRAM pointer at the top of the window, so only the first chunk of pixels fills a strip. Solution: keep CS low for the entire pixel write sequence.

### Colors appear wrong (red looks blue, etc.)

The ST7735R supports both RGB and BGR byte order controlled by the MADCTL register (0x36). The INITR_BLACKTAB variant used here (MADCTL = 0xC8) expects RGB order in the pixel data. If colors are swapped, check the RGB565 packing formula in `show()`.

### Colors appear washed out or wrong after boot

The display may have leftover data in GRAM from a previous run. Always call `lcd.init()` which performs a hardware reset before sending the init sequence.

### spidev xfer2 OverflowError: Argument list size exceeds 4096 bytes

The Linux SPI driver limits single transfers to 4096 bytes. Split large buffers into 4096-byte chunks. The driver handles this automatically.

### lgpio spi xfer/read/write failed

Same 4096-byte limit applies to `lgpio.spi_write()`. Split into chunks as shown in the driver.

### ModuleNotFoundError for various libraries

The Adafruit and luma.lcd libraries have frequent breaking API changes and incomplete ST7735R support. Avoid them entirely for this display. Use the raw lgpio + spidev approach documented here.

### Libraries tried and abandoned

These were tested and did not work reliably for this specific display:

- `st7735` (pip) — broken API, missing gpiodevice dependency, wrong init for R variant
- `adafruit-circuitpython-st7735r` — BusDisplay API incompatibility, does not accept cs or dc kwargs
- `adafruit-circuitpython-rgb-display` — same BusDisplay issue
- `luma.lcd` — unsupported display mode for 128×160, reset timing insufficient
- Raw `spidev` alone — hardware CS toggling breaks GRAM writes

### The Arduino sanity check

If you are completely stuck, wire the display to an Arduino Uno using the Adafruit ST7735 library with `initR(INITR_BLACKTAB)`. If it works on the Arduino and not the Pi, the display hardware is fine and the problem is in the Pi SPI driver interaction — which is exactly the situation documented here.

---

## Reference

- ST7735R datasheet — search "ST7735R datasheet Sitronix"
- Adafruit ST7735 Arduino library source — the `initR()` sequence in this driver is derived from the INITR_BLACKTAB path in that library
- lgpio documentation — http://abyz.me.uk/lg/py_lgpio.html

---

*Documented as part of FAU Senior Design Project: Parametric Retrofit of Lab Equipment for Remote Control*  
*Author: Skylar — March 2026*
