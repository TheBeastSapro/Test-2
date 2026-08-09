"""Export procedural placeholder art for the Remotion engine.

Two families:
  plates/slotNN.png   background plates, one per UNIQUE location (shots reuse them)
  cutouts/cutNN_*.png alpha cutouts for the layered-cutout scene language
  tex/grain.png       tiling grain used by the atmosphere pass

Plates are rendered at 2600x1600 (was 1700x1050): the rebuild hard-cuts to
'close' and 'insert' crops of the SAME plate, which magnifies the source ~2-3x.
At the old size those crops went visibly soft.
"""
import os, sys
sys.path.insert(0, "/home/claude/hp/engine")
import numpy as np
from PIL import Image
import plates as P
import cutouts as C
import sheets.sewer_spider as M

ROOT = "/home/claude/hp/remotion/public"
P.PW, P.PH = 2600, 1600          # module-level, read by make_plate()

os.makedirs(f"{ROOT}/plates", exist_ok=True)
for slot, desc, kl in M.PLATES:
    im = P.make_plate(slot, desc, slot * 977 + 13, key_light=kl)
    im.save(f"{ROOT}/plates/slot{slot:02d}.png", "PNG")
    print(f"plate slot{slot:02d} {im.size} {desc}")

card = P.make_plate(99, M.CARDS[0]["desc"], 4242, key_light=0.62)
card.save(f"{ROOT}/plates/card.png", "PNG")
print("plate card", card.size)

for slot, name, path, size in C.export_all(f"{ROOT}/cutouts"):
    print(f"cut{slot:02d} {name} {size}")

# --- tiling grain --------------------------------------------------------
os.makedirs(f"{ROOT}/tex", exist_ok=True)
rng = np.random.default_rng(7)
g = rng.normal(0.5, 0.16, (512, 512)).clip(0, 1)
a = (np.abs(g - 0.5) * 2 * 255).astype(np.uint8)
v = np.where(g > 0.5, 255, 0).astype(np.uint8)
Image.fromarray(np.stack([v, v, v, (a * 0.55).astype(np.uint8)], -1), "RGBA").save(f"{ROOT}/tex/grain.png")
print("tex/grain.png (512x512)")
