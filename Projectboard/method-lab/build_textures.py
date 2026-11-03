"""Macht aus den in ChatGPT generierten Bildern in assets-src/ die Texturen für public/textures.

Die Bilder kommen als „nahtlos“ an, sind es aber selten ganz. Deshalb wird jede Kante über einen Streifen
überblendet. Normal- und Rauheitskarte sind aus der Helligkeit abgeleitet, also plausibel, aber nicht gemessen.

    ..\\..\\Simulation\\mujoco-scene\\.venv\\Scripts\\python.exe build_textures.py
"""
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / 'assets-src', HERE / 'public/textures'
SIZE = 1024
# Name: (Tiefe der Normalkarte, Rauheit dunkel, Rauheit hell)
TEX = {'floor': (1.5, .22, .42), 'bench': (1.2, .5, .75), 'metal': (.8, .28, .42), 'plastic': (1.6, .42, .6)}

def seam_blend(a, width):
    """Macht das Bild periodisch: Mitte zeigt danach die alte Kante, sie wird überblendet."""
    h, w = a.shape[:2]
    out = a.copy()
    t = np.linspace(0, 1, width)
    for axis, n in ((1, w), (0, h)):
        roll = np.roll(out, n // 2, axis=axis)
        ramp = np.ones(n)
        ramp[n // 2 - width // 2:n // 2 + width // 2] = np.abs(2 * t - 1) ** 1.5
        ramp = ramp[None, :, None] if axis == 1 else ramp[:, None, None]
        out = roll * ramp + out * (1 - ramp)
    return out

def edge_error(a):
    return float(np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0] - a[-1]).mean()) / 2

def normal_map(height, strength):
    dx = np.roll(height, -1, 1) - np.roll(height, 1, 1)
    dy = np.roll(height, -1, 0) - np.roll(height, 1, 0)
    n = np.dstack([-dx * strength, dy * strength, np.ones_like(height)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return (n * .5 + .5) * 255

def save(a, name):
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(OUT / name, quality=90, optimize=True)

OUT.mkdir(parents=True, exist_ok=True)
for name, (depth, r0, r1) in TEX.items():
    path = SRC / f'tex_{name}.png'
    if not path.exists():
        print('fehlt', path.name)
        continue
    a = np.asarray(Image.open(path).convert('RGB').resize((SIZE, SIZE), Image.LANCZOS), float)
    before = edge_error(a)
    a = seam_blend(a, SIZE // 8)
    h = a.mean(2) / 255
    fine = h - np.asarray(Image.fromarray((h * 255).astype(np.uint8)).resize((64, 64)).resize((SIZE, SIZE), Image.BICUBIC), float) / 255
    save(a, f'{name}_albedo.jpg')
    save(normal_map(fine, depth * 4), f'{name}_normal.jpg')
    rough = r0 + (r1 - r0) * np.clip(.5 + fine * 6, 0, 1)
    save(np.dstack([rough * 255] * 3), f'{name}_rough.jpg')
    print(name, f'Kante vorher {before:.1f}, nachher {edge_error(a):.1f}')

env = np.asarray(Image.open(SRC / 'env_labor.png').convert('RGB'), float)
w = env.shape[1]
band = w // 40
t = np.linspace(1, 0, band)[None, :, None]
fixed = env.copy()
mean = (env[:, :1] + env[:, -1:]) / 2                # Naht links/rechts schliessen
fixed[:, :band] += (mean - env[:, :1]) * t
fixed[:, -band:] += (mean - env[:, -1:]) * t[:, ::-1]
save(fixed, 'env_labor.jpg')
print('Umgebung', env.shape[1], 'x', env.shape[0], 'Naht vorher', float(np.abs(env[:, 0] - env[:, -1]).mean()), 'nachher', float(np.abs(fixed[:, 0] - fixed[:, -1]).mean()))
