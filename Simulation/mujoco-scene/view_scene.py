"""Interaktiver MuJoCo-Viewer.

    python view_scene.py            # Szene ansehen; Leertaste = Pause, Doppelklick + Strg-Ziehen = Objekt schubsen
    python view_scene.py --demo     # Demonstrator greift das Kit immer wieder (neue Zufallspose je Durchlauf)
    python view_scene.py --replay data/run01/episode_0000.hdf5

Tasten im Fenster: R = neue zufällige Kitpose (Box bleibt fest).
Die Gelenk-Schieberegler im Control-Panel (rechts) steuern die Positionsregler direkt.
"""
import argparse, sys, time
import numpy as np
import mujoco.viewer
from roche_env import RocheKitBoxEnv
from scripted_expert import ScriptedExpert

def log(*a):
    print(*a, flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--demo', action='store_true')
    p.add_argument('--replay')
    p.add_argument('--seed', type=int, default=0)
    args = p.parse_args()
    env = RocheKitBoxEnv()
    state = {'seed': args.seed, 'reset': True}

    def key(code):
        if code in (ord('R'), ord('r')):
            state['seed'] += 1
            state['reset'] = True

    actions = None
    if args.replay:
        import h5py
        with h5py.File(args.replay) as f:
            actions = f['action'][:]
            state['seed'] = int(f.attrs['seed'])
    # Der Viewer rendert in einem eigenen Thread. Jede Änderung an env.data (Reset, Physikschritt)
    # muss deshalb unter v.lock() laufen, sonst kann der Prozess beim gleichzeitigen Lesen abstürzen.
    with mujoco.viewer.launch_passive(env.model, env.data, key_callback=key) as v:
        gen = None
        while v.is_running():
            t = time.time()
            if state['reset']:
                state['reset'] = False
                with v.lock():
                    env.reset(seed=state['seed'])
                gen = iter(actions) if actions is not None else (ScriptedExpert(env).actions() if args.demo else None)
                log('Seed', state['seed'], 'Kitstart x/y/yaw', np.round(env.kit_start, 3))
            if gen is not None:
                a = next(gen, None)  # IK-Berechnung ausserhalb des Locks; liest nur eine Kopie
                if a is None:
                    log('Erfolg:', env.kit_in_box())
                    for _ in range(50):
                        with v.lock():
                            env.step(env.action)
                        v.sync()
                        time.sleep(env.control_dt)
                    gen = None
                    if not args.replay:
                        state['seed'] += 1
                        state['reset'] = True
                else:
                    with v.lock():
                        env.step(a)
            else:
                # freie Interaktion: Sollwerte aus dem Viewer-Control-Panel übernehmen
                with v.lock():
                    env._physics(env.data.ctrl[env._ctrl_order()].copy())
            v.sync()
            time.sleep(max(0, env.control_dt - (time.time() - t)))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('FEHLER:', repr(exc))
        raise
