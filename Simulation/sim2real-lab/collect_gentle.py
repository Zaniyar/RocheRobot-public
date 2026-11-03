"""Sammelt Demonstrationen des sanften Griffs nach einem Bewegungsprofil.

    python collect_gentle.py --profile right_arm --episodes 50 --out data/run01
    python collect_gentle.py --profile mein-profil.json --episodes 5 --out data/test --images
    python collect_gentle.py --profile right_arm --episodes 5 --out data/test --images --no-wrist-cameras

Das Profil legt fest, welche Gelenke zum Aktionsraum gehören. Gesperrte Gelenke bleiben auf der
Ausgangspose und erscheinen nicht in /action. Was die Szene nicht kann, wird abgelehnt, nicht simuliert.
Gespeichert wird nur, was aufrecht in der Box steht und unterwegs nicht durch den Körper fuhr.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import h5py
import measure as M
from roche_env import ACTION_NAMES, TABLE_TOP, KIT_HALF_Z
from gentle_expert import PlanFail
from waist_lab import WaistLab
from floating_lab import FloatingLab, STAND_X

HERE = Path(__file__).resolve().parent
GROUP_INDEX = {'left_arm': range(0, 7), 'left_gripper': [7], 'right_arm': range(8, 15), 'right_gripper': [15]}
UNSUPPORTED = {'base': 'Gehen und Greifen'}
WAIST_NAMES = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']

def without_wrist_cameras(env):
    """Roboter ohne Handkameras: Ihre Bilder fehlen im Datensatz, das Gehäuse fehlt auch im Bild der Kopfkamera."""
    env.cameras = [c for c in env.cameras if 'wrist' not in c]
    m = env.model
    for g in range(m.ngeom):
        if '_wrist_cam_' in m.geom(g).name:
            m.geom_rgba[g, 3] = 0

def load_profile(arg):
    path = Path(arg)
    if path.suffix == '.json' and path.exists():
        return json.load(open(path, encoding='utf8'))
    for p in json.load(open(HERE / 'dof_profiles.json', encoding='utf8')):
        if p['id'] == arg:
            return p
    sys.exit(f'Unbekanntes Profil: {arg}')

def check(profile):
    g = profile['groups']
    missing = [name for key, name in UNSUPPORTED.items() if g.get(key)]
    if missing:
        sys.exit(f"Profil nicht ausführbar, die MuJoCo-Szene kann das noch nicht: {', '.join(missing)}")
    if not (g.get('right_arm') and g.get('right_gripper')):
        sys.exit('Der Demonstrator greift mit der rechten Hand: rechter Arm und Greifer müssen frei sein.')
    return [i for key, idx in GROUP_INDEX.items() if g.get(key) for i in idx]

def run_balance(lab, seed, keep):
    """Freistehend: Die Laufpolicy regelt die Beine, /action enthält nur den rechten Arm und Greifer."""
    e, images = lab.world, {c: [] for c in lab.world.cameras} if lab.world.renderer else {}
    log = {k: [] for k in ('action', 'qpos', 'qvel', 'kit_pose', 'legs', 'base')}
    def record(t, target, g):
        obs = e.observation()
        a = np.r_[e.action[:8], target, g]
        log['action'].append(a[keep])
        log['qpos'].append(obs['qpos'][keep])
        log['qvel'].append(obs['qvel'][keep])
        log['kit_pose'].append(obs['kit_pose'])
        log['legs'].append(e.data.qpos[lab.b.q_obs[:12]].copy())
        log['base'].append(e.data.qpos[lab.b.free_q:lab.b.free_q + 7].copy())
        for c in images:
            images[c].append(obs['images'][c])
    r = lab.episode(seed, start=(STAND_X, 0.), correct=True, keep=record)
    if r['plan_fail']:
        raise PlanFail(r['plan_fail'])
    return r['gentle'], log, images, dict(kit_start=e.kit_start.copy(), tilt_max=r['tilt_max'], clearance_mm=r['clearance_mm'])

def run(lab, seed, profile, keep):
    e = lab.env
    p = dict(M.NOMINAL, sway=profile.get('sway_mm', 0) / 1000)
    rng = np.random.default_rng(seed + 10_000)
    lab.configure(p, rng)
    obs = e.reset(seed=seed)
    start = e.kit_start.copy()
    actions = lab.actions(p, rng)     # PlanFail: Griff wird verweigert
    log = {k: [] for k in ('action', 'qpos', 'qvel', 'kit_pose')}
    waist = hasattr(e, 'waist_target')
    if waist:
        log['waist'] = []
    images = {c: [] for c in e.cameras} if e.renderer else {}
    tilt_max, clearance = 0., 1.
    for t, a in enumerate(actions):
        log['action'].append(np.r_[a[keep], e.waist_target] if waist else a[keep])
        if waist:
            log['waist'].append(e.data.qpos[e.waist_q].copy())
        log['qpos'].append(obs['qpos'][keep])
        log['qvel'].append(obs['qvel'][keep])
        log['kit_pose'].append(obs['kit_pose'])
        for c in images:
            images[c].append(obs['images'][c])
        obs, _ = e.step(a)
        if e.data.xpos[e.kit][2] - TABLE_TOP - KIT_HALF_Z > .012:
            tilt_max = max(tilt_max, float(np.degrees(np.arccos(np.clip(e.data.xmat[e.kit][8], -1, 1)))))
        if t % 5 == 0:
            clearance = min(clearance, lab.check.worst(e.data.qpos)[0])
    for _ in range(40):
        obs, _ = e.step(e.action.copy())
    tilt_end = float(np.degrees(np.arccos(np.clip(e.data.xmat[e.kit][8], -1, 1))))
    ok = e.kit_in_box() and tilt_end < 10 and tilt_max < M.TILT_LIMIT and clearance >= -M.SELF_TOL
    e.model.body_pos[e.model.body('pelvis').id] = e.pelvis0
    if waist:
        e.waist_target = np.zeros(3)
    return ok, log, images, dict(kit_start=start, tilt_max=tilt_max, clearance_mm=clearance * 1000)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='right_arm')
    ap.add_argument('--episodes', type=int, default=10)
    ap.add_argument('--out', default='data/run')
    ap.add_argument('--seed0', type=int, default=20000)
    ap.add_argument('--images', action='store_true')
    ap.add_argument('--no-wrist-cameras', action='store_true', help='Roboter ohne Handkameras: nur die Kopfkamera speichern')
    a = ap.parse_args()
    profile = load_profile(a.profile)
    keep = check(profile)
    groups = profile['groups']
    if groups.get('legs'):
        lab = FloatingLab(render=a.images)
    elif groups.get('waist'):
        lab = WaistLab(render=a.images)
    else:
        lab = M.Lab(render=a.images)
    wrist = profile.get('wrist_cameras', True) and not a.no_wrist_cameras
    profile['wrist_cameras'] = wrist
    if not wrist:
        without_wrist_cameras(lab.world if groups.get('legs') else lab.env)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    saved = seed = refused = failed = 0
    while saved < a.episodes:
        s = a.seed0 + seed
        seed += 1
        try:
            ok, log, images, info = run_balance(lab, s, keep) if groups.get('legs') else run(lab, s, profile, keep)
        except PlanFail:
            refused += 1
            continue
        if not ok:
            failed += 1
            continue
        with h5py.File(out / f'episode_{saved:04d}.hdf5', 'w') as f:
            f['action'] = np.asarray(log['action'], np.float32)
            obs = f.create_group('observations')
            obs['qpos'], obs['qvel'] = np.asarray(log['qpos'], np.float32), np.asarray(log['qvel'], np.float32)
            obs['kit_pose'] = np.asarray(log['kit_pose'], np.float32)   # privilegiert: nur für Labels und Auswertung
            for k in ('waist', 'legs', 'base'):
                if k in log:
                    obs[k] = np.asarray(log[k], np.float32)
            for c, frames in images.items():
                obs.create_dataset(f'images/{c}', data=np.asarray(frames, np.uint8), compression='gzip', compression_opts=3)
            f.attrs.update(seed=s, fps=50, profile=json.dumps(profile), wrist_cameras=wrist, cameras=json.dumps(list(images)), action_names=json.dumps([ACTION_NAMES[i] for i in keep] + (WAIST_NAMES if groups.get('waist') else [])),
                           language_instruction='Stelle das Reagenzkit aufrecht in die blaue Box.',
                           tilt_max=info['tilt_max'], clearance_mm=info['clearance_mm'], kit_start=info['kit_start'])
        saved += 1
    print(json.dumps(dict(saved=saved, refused=refused, failed=failed, action_dim=len(keep) + (3 if groups.get('waist') else 0), profile=profile.get('id', a.profile))))
