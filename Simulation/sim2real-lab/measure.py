"""Misst Greifabläufe in der MuJoCo-Szene: Kippen, Schwappen, Robustheit gegen Sim-to-Real-Fehler.

Die Szene (Simulation/mujoco-scene) bleibt unverändert. LabEnv stört nur von aussen. Der Planer
arbeitet immer auf einem Nominalmodell und sieht die Störung nicht.

    python measure.py --quick
    python measure.py --episodes 40
"""
import argparse, json, multiprocessing as mp, sys, time
from pathlib import Path
import numpy as np

SCENE = Path(__file__).resolve().parents[1] / 'mujoco-scene'
sys.path.insert(0, str(SCENE))
import mujoco as mj
import scripted_expert as se
from roche_env import RocheKitBoxEnv, TABLE_TOP, KIT_HALF_Z, SIDES
from gentle_expert import GentlePlanner, PlanFail
from selfcheck import SelfCheck

# Schwappmodell: gedämpfter Schwinger, erste Mode eines Rechtecktanks. Geometrie ist eine ANNAHME.
SLOSH_L, SLOSH_H, SLOSH_ZETA, G = .06, .03, .03, 9.81
SLOSH_W = np.sqrt(G * np.pi / SLOSH_L * np.tanh(np.pi * SLOSH_H / SLOSH_L))
TILT_LIMIT = 5.   # Arbeitsannahme bis Roche einen Wert nennt
SELF_TOL = .002   # Regelabweichung um die geprüfte Sollbahn, darüber zählt es als Selbstkollision

NOMINAL = dict(expert='gentle', vmax=.08, friction=None, mass=None, com=0., latency=0, kp=1., gravcomp=1.,
               joint_offset=0., percept=0., yaw_err=0., base_xy=0., base_z=0., sway=0.)

class LabEnv(RocheKitBoxEnv):
    gravcomp, joint_offset, sway, base = 1., None, 0., np.zeros(3)

    def _physics(self, action):
        m, d = self.model, self.data
        a = np.asarray(action, float)
        if self.joint_offset is not None:
            a = a + self.joint_offset
        for i, s in enumerate(SIDES):
            d.ctrl[self.arm_a[s]] = a[8 * i:8 * i + 7]
            d.ctrl[self.grip_a[s]] = a[8 * i + 7]
        pelvis = m.body('pelvis').id
        for _ in range(self.substeps):
            m.body_pos[pelvis] = self.pelvis0 + self.base + \
                self.sway * np.array([np.sin(2 * np.pi * .9 * d.time), np.sin(2 * np.pi * 1.3 * d.time + 1), 0])
            d.qfrc_applied[:] = 0
            d.qfrc_applied[self.all_v] = self.gravcomp * d.qfrc_bias[self.all_v]
            mj.mj_step(m, d)

class Lab:
    """Pro Prozess einmal: Welt-Umgebung plus unverändertes Planungsmodell."""
    def __init__(self, render=False):
        self.env, self.plan_env = LabEnv(render=render), RocheKitBoxEnv()
        m, e = self.env.model, self.env
        e.pelvis0 = m.body_pos[m.body('pelvis').id].copy()
        self.base = dict(friction=m.geom_friction.copy(), mass=float(m.body_mass[e.kit]),
                         inertia=m.body_inertia[e.kit].copy(), ipos=m.body_ipos[e.kit].copy(),
                         gain=m.actuator_gainprm[:, 0].copy(), bias=m.actuator_biasprm[:, 1].copy(),
                         kv=m.actuator_biasprm[:, 2].copy())
        self.check = SelfCheck(self.plan_env.model, side='right')
        self.fingers = [i for i in range(m.ngeom) if 'dex1' in (m.body(m.geom_bodyid[i]).name or '')]
        self.kit_geoms = np.where(m.geom_bodyid == e.kit)[0]

    def configure(self, p, rng):
        e, m, b = self.env, self.env.model, self.base
        m.geom_friction[:] = b['friction']
        m.body_mass[e.kit], m.body_inertia[e.kit], m.body_ipos[e.kit] = b['mass'], b['inertia'], b['ipos']
        m.actuator_gainprm[:, 0], m.actuator_biasprm[:, 1], m.actuator_biasprm[:, 2] = b['gain'], b['bias'], b['kv']
        if p['friction'] is not None:
            m.geom_friction[self.kit_geoms, 0] = p['friction']
            m.geom_friction[self.fingers, 0] = p['friction']
        if p['mass'] is not None:
            m.body_mass[e.kit] = p['mass']
            m.body_inertia[e.kit] = b['inertia'] * p['mass'] / b['mass']
        m.body_ipos[e.kit] = b['ipos'] + [0, 0, p['com']]
        m.actuator_gainprm[:, 0] = b['gain'] * p['kp']
        m.actuator_biasprm[:, 1] = b['bias'] * p['kp']
        m.actuator_biasprm[:, 2] = b['kv'] * np.sqrt(p['kp'])
        e.gravcomp = p['gravcomp']
        e.sway = p['sway']
        e.joint_offset = None
        if p['joint_offset']:
            off = rng.choice([-1, 1], 16) * p['joint_offset']
            off[[7, 15]] = 0
            e.joint_offset = off
        a = rng.uniform(0, 2 * np.pi)
        e.base = np.array([p['base_xy'] * np.cos(a), p['base_xy'] * np.sin(a), p['base_z']])

    def perceived(self, p, rng):
        k = self.env.kit_pose()
        a = rng.uniform(0, 2 * np.pi)
        k[:2] += p['percept'] * np.array([np.cos(a), np.sin(a)])
        if p['yaw_err']:
            w, z = np.cos(p['yaw_err'] / 2), rng.choice([-1, 1]) * np.sin(p['yaw_err'] / 2)
            q = k[3:].copy()
            k[3:] = [w * q[0] - z * q[3], w * q[1] - z * q[2], w * q[2] + z * q[1], w * q[3] + z * q[0]]
        return k

    def actions(self, p, rng):
        e = self.env
        if p['expert'] == 'scripted':
            return se.ScriptedExpert(e, rng).actions()
        pe = self.plan_env
        pe.reset(kit_pose=tuple(e.kit_start))
        planner = GentlePlanner(pe, vmax=p['vmax'])
        steps = planner.plan(self.perceived(p, rng), pe.home['right'])
        base = e.action.copy()
        def gen():
            a = base.copy()
            for q, g in steps:
                a[8:15], a[15] = q, g
                yield a.copy()
        return gen()

    def episode(self, seed, p, keep_trace=False):
        e = self.env
        rng = np.random.default_rng(seed + 10_000)
        self.configure(p, rng)
        e.reset(seed=seed)
        dt = e.control_dt
        queue, vel_f, vel_prev = [], None, None
        s_ang, s_vel = np.zeros(2), np.zeros(2)
        tilt_max = acc_max = slosh_max = carry_time = t = 0.
        lifted = False
        trace, bodies = [], list(range(1, e.model.nbody))
        clearance, count = 1., 0

        def tick(action):
            nonlocal clearance, count, vel_f, vel_prev, s_ang, s_vel, tilt_max, acc_max, slosh_max, lifted, carry_time, t
            queue.append(action)
            applied = queue.pop(0) if len(queue) > p['latency'] else queue[0]
            e.step(applied)
            t += dt
            count += 1
            if count % 5 == 0:   # tatsächliche Gelenkwinkel, nicht die Sollwerte
                clearance = min(clearance, self.check.worst(e.data.qpos)[0])
            d, k = e.data, e.kit
            R = d.xmat[k].reshape(3, 3)
            tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
            vel = d.cvel[k][3:].copy()
            vel_f = vel if vel_f is None else vel_f + (dt / .06) * (vel - vel_f)     # Kontaktrauschen filtern
            acc = np.zeros(3) if vel_prev is None else (vel_f - vel_prev) / dt
            vel_prev = vel_f.copy()
            height = d.xpos[k][2] - (TABLE_TOP + KIT_HALF_Z)
            lifted = lifted or height > .015
            air = height > .012
            g_app = R.T @ (acc + np.array([0, 0, G]))
            eq = np.arctan2(g_app[:2], max(g_app[2], 1.)) if air else np.zeros(2)
            s_vel = s_vel + (-2 * SLOSH_ZETA * SLOSH_W * s_vel - SLOSH_W ** 2 * (s_ang - eq)) * dt
            s_ang = s_ang + s_vel * dt
            slosh = float(np.degrees(np.linalg.norm(s_ang)))
            if air:
                carry_time += dt
                tilt_max, acc_max = max(tilt_max, tilt), max(acc_max, float(np.linalg.norm(acc)))
                slosh_max = max(slosh_max, slosh)
            if keep_trace:
                q = e.qpos16()
                trace.append(dict(t=t, tilt=tilt, slosh=slosh, acc=float(np.linalg.norm(acc)), height=float(height),
                                  speed=float(np.linalg.norm(vel_f)), grip=float(q[15]),
                                  track=float(np.degrees(np.abs(e.action[8:15] - q[8:15]).max())),
                                  xpos=d.xpos[bodies].astype(np.float32).copy(), xquat=d.xquat[bodies].astype(np.float32).copy()))

        fail = None
        try:
            actions = self.actions(p, rng)
        except PlanFail as x:
            fail, actions = str(x), []
        for a in actions:
            tick(a)
        for _ in range(int(.8 / dt)):
            tick(e.action.copy())
        R = e.data.xmat[e.kit].reshape(3, 3)
        final_tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
        in_box = e.kit_in_box()
        hit = bool(clearance < -SELF_TOL)
        res = dict(seed=seed, plan_fail=fail, in_box=bool(in_box), lifted=bool(lifted), final_tilt=final_tilt,
                   clearance_mm=float(clearance * 1000), self_hit=hit,
                   placed=bool(in_box and final_tilt < 10 and not hit), tilt_max=tilt_max, acc_max=acc_max, slosh_max=slosh_max,
                   duration=t, carry_time=carry_time, kit_start=[float(x) for x in e.kit_start],
                   gentle=bool(in_box and final_tilt < 10 and tilt_max < TILT_LIMIT and not hit),
                   kit_z=float(e.data.xpos[e.kit][2]))
        e.model.body_pos[e.model.body('pelvis').id] = e.pelvis0
        return (res, trace) if keep_trace else res

_lab = None
def _feasible(seed):
    global _lab
    if _lab is None:
        _lab = Lab()
    e = _lab.plan_env
    e.reset(seed=seed)
    try:
        GentlePlanner(e, vmax=NOMINAL['vmax']).plan(e.kit_pose(), e.home['right'])
        return seed
    except PlanFail:
        return None

def _worker(job):
    global _lab
    if _lab is None:
        _lab = Lab()
    name, shown, seed, p = job
    r = _lab.episode(seed, p)
    r.update(sweep=name, value=shown)
    return r

# Name: (Schlüssel, angezeigte Werte, Umrechnung in Modellwert)
SWEEPS = {
    'vmax_mm_s': ('vmax', [30, 50, 80, 120, 200, 300], lambda v: v / 1000),
    'percept_mm': ('percept', [0, 3, 6, 10, 15, 20], lambda v: v / 1000),
    'yaw_deg': ('yaw_err', [0, 3, 6, 10, 15, 25], np.radians),
    'base_xy_mm': ('base_xy', [0, 3, 6, 10, 15, 25], lambda v: v / 1000),
    'base_z_mm': ('base_z', [-15, -8, -4, 0, 4, 8, 15], lambda v: v / 1000),
    'sway_mm': ('sway', [0, 2, 4, 8, 12], lambda v: v / 1000),
    'friction': ('friction', [.3, .45, .6, .8, 1.1], lambda v: v),
    'mass_g': ('mass', [70, 100, 180, 300, 500], lambda v: v / 1000),
    'com_mm': ('com', [0, 10, 20, 30], lambda v: v / 1000),
    'latency_ms': ('latency', [0, 20, 40, 80, 160], lambda v: int(v / 20)),
    'kp_scale': ('kp', [.4, .6, .8, 1., 1.3], lambda v: v),
    'gravcomp': ('gravcomp', [1., .9, .7, .4, 0.], lambda v: v),
    'joint_offset_deg': ('joint_offset', [0, .25, .5, 1, 2], np.radians),
}

def wilson(k, n, z=1.96):
    p, d = k / n, 1 + z * z / n
    c, h = p + z * z / (2 * n), z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [float((c - h) / d), float((c + h) / d)]

def stats(g):
    lifted = [r for r in g if r['lifted']]
    med = lambda key: float(np.median([r[key] for r in lifted])) if lifted else None
    return dict(n=len(g), placed=sum(r['placed'] for r in g), gentle=sum(r['gentle'] for r in g),
                placed_ci95=wilson(sum(r['placed'] for r in g), len(g)), gentle_ci95=wilson(sum(r['gentle'] for r in g), len(g)),
                plan_fail=sum(bool(r['plan_fail']) for r in g), lifted=len(lifted), lying_in_box=sum(r['in_box'] and r['final_tilt'] >= 10 for r in g), self_hit=sum(r['self_hit'] for r in g), clearance_min=float(min(r['clearance_mm'] for r in g)),
                tilt_median=med('tilt_max'), tilt_p95=float(np.percentile([r['tilt_max'] for r in lifted], 95)) if lifted else None,
                slosh_median=med('slosh_max'), acc_median=med('acc_max'), duration_median=float(np.median([r['duration'] for r in g])))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episodes', type=int, default=40)
    ap.add_argument('--compare', type=int, default=200)
    ap.add_argument('--seed0', type=int, default=2000)
    ap.add_argument('--workers', type=int, default=14)
    ap.add_argument('--out', default=str(Path(__file__).with_name('results.json')))
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    t0 = time.time()
    with mp.Pool(a.workers) as pool:
        if a.quick:
            jobs = [('q', 0, a.seed0 + s, dict(NOMINAL)) for s in range(a.workers * 2)]
            for r in pool.map(_worker, jobs):
                print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k not in ('kit_start', 'sweep', 'value', 'in_box', 'lifted')})
            print('s', round(time.time() - t0, 1))
            sys.exit()
        jobs = []
        # Vorher/Nachher auf denselben Seeds; danach Empfindlichkeit, immer nur eine Grösse verändert.
        for s in range(a.compare):
            jobs.append(('compare', 'scripted', a.seed0 + s, dict(NOMINAL, expert='scripted')))
            jobs.append(('compare', 'gentle', a.seed0 + s, dict(NOMINAL)))
        # Empfindlichkeit nur auf nominal planbaren Startlagen, sonst überdeckt die Arbeitsraumgrenze den Effekt.
        seeds = [s for s in pool.map(_feasible, range(a.seed0 + 5000, a.seed0 + 5000 + a.episodes * 2)) if s is not None][:a.episodes]
        for name, (key, values, conv) in SWEEPS.items():
            for v in values:
                p = dict(NOMINAL, **{key: conv(v)})
                jobs += [(name, v, s, p) for s in seeds]
        print(len(jobs), 'Episoden', flush=True)
        rows = []
        for i, r in enumerate(pool.imap_unordered(_worker, jobs, chunksize=2)):
            rows.append(r)
            if i % 200 == 0:
                print(i, round(time.time() - t0), flush=True)
    out = {}
    for name in ['compare', *SWEEPS]:
        vals = dict.fromkeys(r['value'] for r in sorted((r for r in rows if r['sweep'] == name), key=lambda r: str(r['value']) if name == 'compare' else r['value']))
        out[name] = [dict(value=v, **stats([r for r in rows if r['sweep'] == name and r['value'] == v])) for v in vals]
    json.dump(dict(date='2026-11-02', engine='MuJoCo ' + mj.__version__, seeds=[a.seed0, a.seed0 + max(a.compare, a.episodes) - 1],
                   tilt_limit_deg=TILT_LIMIT, slosh_model=dict(L=SLOSH_L, h=SLOSH_H, zeta=SLOSH_ZETA, f_hz=float(SLOSH_W / 2 / np.pi), note='Annahme, nicht gemessen'),
                   seconds=round(time.time() - t0), sweeps=out, episodes=rows), open(a.out, 'w'), indent=0)
    print('fertig', round(time.time() - t0))
