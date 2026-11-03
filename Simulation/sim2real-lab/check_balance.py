"""Besteht die Laufpolicy in MuJoCo? Stehen, Gehen, Drehen, Armbewegung; Bericht als JSON."""
import json, sys, time
import numpy as np
import mujoco as mj
from balance_env import Balance

def scenario(name, seconds, command, base=(-2., 0.), arm=None):
    m = mj.MjModel.from_xml_path('scenes/floating.xml')
    d = mj.MjData(m)
    b = Balance(m, d, base=base)
    n = int(seconds / .02)
    trace = []
    fell = None
    for t in range(n):
        if arm: arm(b, t * .02)
        b.step(command(t * .02) if callable(command) else command)
        p, yaw, tilt = b.pose()
        trace.append([*p, yaw, tilt])
        if p[2] < .5 or tilt > 45:
            fell = t * .02
            break
    tr = np.array(trace)
    settle = tr[min(100, len(tr) - 1):]
    return dict(name=name, seconds=round(len(tr) * .02, 2), fell_at=fell, dx=round(float(tr[-1, 0] - base[0]), 3), dy=round(float(tr[-1, 1] - base[1]), 3),
                yaw_deg=round(float(np.degrees(tr[-1, 3])), 1), z_mean=round(float(settle[:, 2].mean()), 3),
                tilt_max=round(float(settle[:, 4].max()), 2), xy_sway_mm=round(float(np.ptp(settle[:, :2], axis=0).max() * 1000), 1))

t0 = time.time()
out = [
    scenario('stehen', 30, (0, 0, 0)),
    scenario('vorwaerts_.5', 10, (.5, 0, 0)),
    scenario('rueckwaerts_.3', 10, (-.3, 0, 0)),
    scenario('seitwaerts_.3', 10, (0, .3, 0)),
    scenario('drehen_.8', 10, (0, 0, .8)),
]
print(json.dumps(out, indent=1), f'{time.time() - t0:.0f}s')
