"""Sammelt Trainingsepisoden (HDF5, ALOHA/ACT-ähnliches Layout; mit LeRobot-Konvertern kompatibel aufgebaut).

    python collect_data.py --episodes 50 --out data/run01
    python collect_data.py --episodes 5 --no-images        # schnell, nur Zustände

Pro Episode eine Datei episode_XXXX.hdf5:
    /action                        (T, 16)  Gelenk-Sollwerte [L-Arm 7, L-Greifer, R-Arm 7, R-Greifer]
    /observations/qpos             (T, 16)  gemessene Gelenkwinkel, gleiche Reihenfolge
    /observations/qvel             (T, 16)
    /observations/kit_pose         (T, 7)   xyz + Quaternion wxyz (privilegiert, nur für Auswertung/Labels)
    /observations/images/<kamera>  (T, H, W, 3) uint8
    attrs: seed, success, kit_start (x, y, yaw), language_instruction, fps
"""
import argparse, json, time
from pathlib import Path
import numpy as np
import h5py
from roche_env import RocheKitBoxEnv, ACTION_NAMES, CAMERAS
from scripted_expert import ScriptedExpert

INSTRUCTION = 'Pick up the reagent kit and place it into the box.'

def record_episode(env, seed, settle_steps=25):
    obs = env.reset(seed=seed)
    expert = ScriptedExpert(env, rng=np.random.default_rng(seed + 10_000))
    frames = []
    def keep(o, a):
        frames.append((o, a.copy()))
    for a in expert.actions():
        keep(obs, a)              # Beobachtung VOR der Aktion (Policy-Konvention)
        obs, info = env.step(a)
    for _ in range(settle_steps):
        a = env.action.copy()
        keep(obs, a)
        obs, info = env.step(a)
    return frames, info

def save(path, frames, info, seed, env):
    with h5py.File(path, 'w') as f:
        f.attrs.update(seed=seed, success=info['success'], kit_start=env.kit_start, fps=round(1 / env.control_dt),
                       language_instruction=INSTRUCTION, action_names=json.dumps(ACTION_NAMES))
        f['action'] = np.array([a for _, a in frames], np.float32)
        o = f.create_group('observations')
        for key in ('qpos', 'qvel', 'kit_pose'):
            o[key] = np.array([ob[key] for ob, _ in frames], np.float32)
        if 'images' in frames[0][0]:
            g = o.create_group('images')
            for cam in frames[0][0]['images']:
                g.create_dataset(cam, data=np.stack([ob['images'][cam] for ob, _ in frames]),
                                 compression='gzip', compression_opts=4, chunks=(1, *frames[0][0]['images'][cam].shape))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--episodes', type=int, default=10)
    p.add_argument('--seed', type=int, default=0, help='erster Seed; Episode i nutzt seed+i')
    p.add_argument('--out', default='data/run01')
    p.add_argument('--width', type=int, default=320)
    p.add_argument('--height', type=int, default=240)
    p.add_argument('--cameras', default=','.join(CAMERAS[:3]))
    p.add_argument('--no-images', action='store_true')
    p.add_argument('--keep-failures', action='store_true', help='auch fehlgeschlagene Episoden speichern')
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = RocheKitBoxEnv(render=not args.no_images, width=args.width, height=args.height,
                         cameras=args.cameras.split(','))
    summary = []
    t0 = time.time()
    for i in range(args.episodes):
        seed = args.seed + i
        frames, info = record_episode(env, seed)
        saved = info['success'] or args.keep_failures
        if saved:
            save(out / f'episode_{seed:04d}.hdf5', frames, info, seed, env)
        summary.append({'seed': seed, 'success': info['success'], 'steps': len(frames), 'saved': saved,
                        'kit_start_x_y_yaw': [round(float(v), 4) for v in env.kit_start]})
        print(f'Episode {seed}: Erfolg={info["success"]} Schritte={len(frames)} gespeichert={saved}', flush=True)
    ok = sum(s['success'] for s in summary)
    (out / 'summary.json').write_text(json.dumps({'episodes': summary, 'success': ok, 'total': len(summary),
                                                  'seconds': round(time.time() - t0, 1),
                                                  'instruction': INSTRUCTION}, indent=2))
    print(f'{ok}/{len(summary)} erfolgreich, Daten in {out.resolve()}')

if __name__ == '__main__':
    main()
