"""Rechnet eine im Dashboard eingestellte Szene wirklich in MuJoCo nach.

    python simulate_config.py --config szene.json --out ../../Projectboard/method-lab/dist/data --episodes 40

Tisch, Box und Zusatzobjekte werden in eine eigene scene.xml geschrieben; mujoco-scene bleibt unverändert.
Zusatzobjekte sind statische Hindernisse mit vereinfachter Kollisionsform. Ergebnis: custom.json und
run_custom.bin mit einem aufgezeichneten Lauf für die Wiedergabe.
"""
import argparse, json, os, sys, time
import xml.etree.ElementTree as E
from multiprocessing import Pool
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE = HERE.parent / 'mujoco-scene'
sys.path.insert(0, str(SCENE))
WAIST = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']
TABLE_NEAR_X = .2     # Tischvorderkante bleibt fest: So steht der Roboter weiter gleich weit davor.
WALL = .008
KIT_HALF_Z = .0407

def fmt(v):
    return ' '.join(f'{float(x):.6g}' for x in v)

def write_scene(cfg, path):
    from build_variants import build
    t, b = cfg['table'], cfg['box']
    build(path.name, WAIST, False)     # Taille frei, Becken fest
    tree = E.parse(path)
    root = tree.getroot()
    world = root.find('worldbody')
    geoms = {g.get('name'): g for g in world.iter('geom')}
    cx = TABLE_NEAR_X + t['depth'] / 2
    top = geoms['table_top']
    top.set('pos', fmt([cx, 0, t['height'] - .025]))
    top.set('size', fmt([t['depth'] / 2, t['width'] / 2, .025]))
    for sx in (-1, 1):
        for sy in (-1, 1):
            leg = geoms[f'table_leg_{sx}_{sy}']
            leg.set('pos', fmt([cx + sx * (t['depth'] / 2 - .05), sy * (t['width'] / 2 - .05), (t['height'] - .05) / 2]))
            leg.set('size', fmt([.025, .025, (t['height'] - .05) / 2]))
    box = next(x for x in world.iter('body') if x.get('name') == 'box')
    box.set('pos', fmt([b['x'], b['y'], t['height']]))
    bx, by, h = b['inner_x'], b['inner_y'], b['height']
    geoms['box_floor'].set('size', fmt([bx / 2 + WALL, by / 2 + WALL, WALL / 4]))
    inner = (bx, by)
    for axis in range(2):
        for sign, s in ((1, 'p'), (-1, 'n')):
            p = [0., 0., h / 2]
            p[axis] = sign * ((inner[axis] + WALL) / 2)
            half = [bx / 2 + WALL, by / 2 + WALL, h / 2]
            half[axis] = WALL / 2
            g = geoms[f'box_wall_{axis}_{s}']
            g.set('pos', fmt(p))
            g.set('size', fmt(half))
    for site in box.findall('site'):
        site.set('size', fmt([bx / 2, by / 2, .001]))
    for i, a in enumerate(cfg.get('assets', [])):
        c = a['collision']
        z = (0 if a.get('floor') else t['height']) + c['height'] / 2
        E.SubElement(world, 'geom', name=f"asset_{i}_{a['id']}", type='cylinder', pos=fmt([a['x'], a['y'], z]),
                     size=fmt([c['radius'], c['height'] / 2]), rgba='.6 .6 .6 1', contype='2', conaffinity='5')
    tree.write(path, encoding='utf8')

def setup(cfg, path):
    """Muss vor dem Import von measure und gentle_expert laufen: Sie übernehmen die Konstanten beim Import."""
    import roche_env as R
    t, b = cfg['table'], cfg['box']
    R.TABLE_TOP = t['height']
    R.BOX_CENTER = np.array([b['x'], b['y']])
    R.BOX_INNER = np.array([b['inner_x'], b['inner_y']])
    R.BOX_HEIGHT = b['height']
    lift = t['height'] + .22
    R.HOME_TCP = {'left': (.30, .26, lift), 'right': (.30, -.26, lift)}
    # Kit liegt nur dort, wo es nicht in Box oder Tischkante fällt.
    y0 = max(R.KIT_Y_RANGE[0], b['y'] + b['inner_y'] / 2 + WALL + .07) if b['y'] < 0 else R.KIT_Y_RANGE[0]
    y1 = min(R.KIT_Y_RANGE[1], t['width'] / 2 - .06)
    x1 = min(R.KIT_X_RANGE[1], TABLE_NEAR_X + t['depth'] - .06)
    R.KIT_Y_RANGE = (y0, max(y0 + .001, y1))
    R.KIT_X_RANGE = (R.KIT_X_RANGE[0], max(R.KIT_X_RANGE[0] + .001, x1))
    import waist_lab as W
    W.XML = path
    return W

CONFIG = os.environ.get('ROCHE_SCENE_CONFIG')
W = None
if CONFIG:   # auch in den Arbeitsprozessen, die dieses Modul neu importieren
    CFG = json.load(open(CONFIG, encoding='utf8'))
    PATH = HERE / 'scenes' / 'custom.xml'
    if __name__ == '__main__':
        write_scene(CFG, PATH)
    W = setup(CFG, PATH)

def run_episode(seed):
    return W.work(seed)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--episodes', type=int, default=40)
    ap.add_argument('--seed0', type=int, default=7000)
    a = ap.parse_args()
    t0 = time.time()
    seeds = range(a.seed0, a.seed0 + a.episodes)
    with Pool(min(14, os.cpu_count() or 4)) as pool:
        res = pool.map(run_episode, seeds, chunksize=1)
    # in_box allein prüft nur die Mitte des Kits. Es muss wirklich auf dem Boxboden stehen, nicht auf den Wänden.
    rest = CFG['table']['height'] + WALL / 2 + KIT_HALF_Z + .012
    for r in res:
        r['seated'] = bool(not r['plan_fail'] and r['kit_z'] < rest)
        r['touching'] = r['table_force'] > 5
        r['placed'] = bool(r['placed'] and r['seated'] and not r['touching'])
        r['gentle'] = bool(r['gentle'] and r['seated'] and not r['touching'])
    placed = [r for r in res if r['placed']]
    touching = sum(r['touching'] for r in res)
    summary = dict(n=len(res), placed=len(placed), gentle=sum(r['gentle'] for r in res), not_seated=sum(not r['plan_fail'] and not r['seated'] for r in res),
                   refused=sum(bool(r['plan_fail']) for r in res), self_hit=sum(r['self_hit'] for r in res), table_contact=touching,
                   waist_used=sum(bool(r['posture'] and any(r['posture'])) for r in res),
                   tilt_median=float(np.median([r['tilt_max'] for r in placed])) if placed else None,
                   seconds=round(time.time() - t0))
    out = Path(a.out)
    best = next((r for r in res if r['gentle']), None) or next((r for r in res if not r['plan_fail']), None)
    run = None
    if best:
        import measure as M
        lab = W.WaistLab()
        lab.env.waist_target = np.zeros(3)
        r, trace = lab.episode(best['seed'], M.NOMINAL, keep_trace=True)
        step = max(1, round(1 / 25 / lab.env.control_dt))
        tr = trace[::step]
        arr = np.stack([np.hstack([f['xpos'], f['xquat']]) for f in tr]).astype(np.float32)
        (out / 'run_custom.bin').write_bytes(arr.tobytes())
        keys = ('tilt', 'slosh', 'acc', 'height', 'speed', 'track', 'grip')
        run = dict(id='custom', title='Eigene Szene, in MuJoCo berechnet', group='Eigene Szene', seed=best['seed'], params={},
                   note=f"Eigene Szene: {summary['gentle']} von {summary['n']} sanft abgelegt.", frames=len(tr), bodies=arr.shape[1],
                   dt=step * lab.env.control_dt, series={k: [round(float(f[k]), 4) for f in tr] for k in keys},
                   result={k: v for k, v in r.items() if k != 'kit_start'}, kit_start=r['kit_start'], sceneConfig=CFG)
    json.dump(dict(summary=summary, run=run, config=CFG, stamp=time.time()), open(out / 'custom.json', 'w', encoding='utf8'))
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
