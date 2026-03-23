import time
import st7735_driver as lcd
from PIL import Image, ImageDraw, ImageFont

def make_screen(title, value, unit, color):
    img = Image.new('RGB', (lcd.WIDTH, lcd.HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.rectangle((0, 0, lcd.WIDTH, 20), fill=color)
    draw.text((4, 4), title, font=font, fill=(0, 0, 0))
    draw.text((10, 60), value, font=font, fill=(255, 255, 255))
    draw.text((10, 80), unit, font=font, fill=color)
    draw.rectangle((0, lcd.HEIGHT-20, lcd.WIDTH, lcd.HEIGHT), fill=(20, 20, 20))
    draw.text((4, lcd.HEIGHT-16), "PiControlTest", font=font, fill=(120, 120, 120))
    return img

lcd.init()

start = time.time()
img = make_screen("HELLO", "THERE", "PEOPLE", (200, 100, 0))
lcd.show(img)
print(f"Done in {time.time()-start:.3f}s")

time.sleep(10)
lcd.cleanup()

