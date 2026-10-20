"""Small contact sheet of app screenshots with a 10% grid, for choosing demo tap points cheaply.

usage: python3 screens_sheet.py <design repo>/screens/13-student-home.png [...more] -o /home/claude/out/sheet.png
Read the printed sheet once: grid lines every 0.1 of width/height; tap = [x, y] in those fractions.
"""
import argparse
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument('screens', nargs='+')
ap.add_argument('-o', '--out', default='/home/claude/out/screens-sheet.png')
a = ap.parse_args()
W, H = 216, 467                     # 1170x2532 scaled down; up to 5 screens per sheet stay cheap to look at
shots = a.screens[:5]
sheet = Image.new('RGB', (len(shots) * (W + 28), H + 22), 'white')
d = ImageDraw.Draw(sheet)
for i, path in enumerate(shots):
    x0 = i * (W + 28) + 20
    im = Image.open(path).convert('RGB').resize((W, H))
    sheet.paste(im, (x0, 18))
    d.text((x0, 2), path.rsplit('/', 1)[-1][:28], fill='black')
    for k in range(1, 10):
        gx, gy = x0 + W * k / 10, 18 + H * k / 10
        d.line([(gx, 18), (gx, 18 + H)], fill=(255, 0, 0) if k == 5 else (255, 150, 150), width=1)
        d.line([(x0, gy), (x0 + W, gy)], fill=(255, 0, 0) if k == 5 else (255, 150, 150), width=1)
        d.text((x0 - 18, gy - 6), f'.{k}', fill='red')
import pathlib
pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
sheet.save(a.out)
print(a.out)
