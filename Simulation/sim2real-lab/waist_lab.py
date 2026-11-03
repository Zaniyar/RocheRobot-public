"""Profil "Taille frei": Die Taille stellt sich vor dem Griff ein und hält diese Haltung bis zum Ablegen.

Der Arm plant auf derselben Haltung, geprüft mit denselben Kriterien wie measure.py. Es wird zuerst ohne
Taillenbewegung geplant, die Taille kommt also nur dort zum Einsatz, wo der Griff sonst verweigert würde.
"""
import json, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import mujoco as mj
import measure as M
from gentle_expert import GentlePlanner, PlanFail, min_jerk
from roche_env import RocheKitBoxEnv, SIDES
from selfcheck import SelfCheck, world_contact

XML = Path(__file__).resolve().parent / 'scenes/waist.xml'
WAIST = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']
# (Gieren, Nicken) in rad. Erst nur Drehen; Vorneigen ist erlaubt, solange der Tisch nicht berührt wird (world_contact).
POSTURES = [(y, 0) for y in (0, .25, -.25, .5, -.5, .75, -.75)] + [(y, p) for p in (.15, .3) for y in (0, .25, -.25, .5, -.5)]
WAIST_RATE = .35   # rad/s, Spitze der Min-Jerk-Bewegung

class WaistEnv(M.LabEnv):
    def __init__(self, **kw):
        super().__init__(xml=XML, **kw)
        self.pelvis0 = self.model.body_pos[self.model.body('pelvis').id].copy()
        m = self.model
        self.waist_a = np.array([m.actuator(n).id for n in WAIST])
        self.waist_q = m.jnt_qposadr[[m.joint(n).id for n in WAIST]]
        self.all_v = np.r_[self.all_v, m.jnt_dofadr[[m.joint(n).id for n in WAIST]]]
        self.waist_target = np.zeros(3)

    def _physics(self, action):
        self.data.ctrl[self.waist_a] = self.waist_target
        super()._physics(action)
        self.contact = max(getattr(self, 'contact', 0.), world_contact(self.model, self.data))

class WaistLab(M.Lab):
    def __init__(self, render=False):
        self.env, self.plan_env = WaistEnv(render=render), WaistEnv()
        m, e = self.env.model, self.env
        e.pelvis0 = m.body_pos[m.body('pelvis').id].copy()
        self.base = dict(friction=m.geom_friction.copy(), mass=float(m.body_mass[e.kit]),
                         inertia=m.body_inertia[e.kit].copy(), ipos=m.body_ipos[e.kit].copy(),
                         gain=m.actuator_gainprm[:, 0].copy(), bias=m.actuator_biasprm[:, 1].copy(),
                         kv=m.actuator_biasprm[:, 2].copy())
        self.check = SelfCheck(self.plan_env.model, side='right')
        self.fingers = [i for i in range(m.ngeom) if 'dex1' in (m.body(m.geom_bodyid[i]).name or '')]
        self.kit_geoms = np.where(m.geom_bodyid == e.kit)[0]

    def plan_posture(self, p, rng):
        e, pe = self.env, self.plan_env
        seen = self.perceived(p, rng)
        last = None
        for y, pitch in POSTURES:
            pe.reset(kit_pose=tuple(e.kit_start))
            w = np.array([y, 0, pitch])
            pe.data.qpos[pe.waist_q] = w
            mj.mj_kinematics(pe.model, pe.data)
            planner = GentlePlanner(pe, vmax=p['vmax'])
            try:
                # Hinbewegung der Taille mit Arm in Heimhaltung muss ebenfalls frei sein.
                q = pe.data.qpos.copy()
                if planner.check.worst(q)[0] < 0:
                    continue
                return w, planner.plan(seen, pe.home['right'])
            except PlanFail as x:
                last = x
        raise last or PlanFail('keine Taillenhaltung')

    def actions(self, p, rng):
        e = self.env
        w, steps = self.plan_posture(p, rng)
        self.posture = w
        base = e.action.copy()
        n = max(1, int(1.875 * np.abs(w).max() / WAIST_RATE / e.control_dt)) if np.any(w) else 0
        def gen():
            a = base.copy()
            for i in range(n):
                e.waist_target = w * min_jerk((i + 1) / n)
                yield a.copy()
            for q, g in steps:
                e.waist_target = w
                a[8:15], a[15] = q, g
                yield a.copy()
            for i in range(n):
                e.waist_target = w * (1 - min_jerk((i + 1) / n))
                yield a.copy()
        return gen()

_lab = None
def work(seed):
    global _lab
    if _lab is None:
        _lab = WaistLab()
    _lab.env.waist_target = np.zeros(3)
    _lab.env.contact = 0.
    r = _lab.episode(seed, M.NOMINAL)
    r['table_force'] = float(_lab.env.contact)
    r['posture'] = [float(x) for x in getattr(_lab, 'posture', (0, 0, 0))] if not r['plan_fail'] else None
    return r

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    t0 = time.time()
    with Pool(int(sys.argv[3]) if len(sys.argv) > 3 else 14) as pool:
        res = pool.map(work, range(a, b), chunksize=1)
    n = len(res)
    used = [r for r in res if r['posture'] and any(r['posture'])]
    summary = dict(date='2026-11-02', seeds=[a, b - 1], n=n, seconds=round(time.time() - t0),
                   placed=sum(r['placed'] for r in res), gentle=sum(r['gentle'] for r in res),
                   refused=sum(bool(r['plan_fail']) for r in res), self_hit=sum(r['self_hit'] for r in res),
                   lying_or_failed=sum(not r['placed'] and not r['plan_fail'] for r in res),
                   table_contact=sum(r['table_force'] > 5 for r in res), table_force_max=max(r['table_force'] for r in res), waist_used=len(used), waist_used_gentle=sum(r['gentle'] for r in used),
                   tilt_median=float(np.median([r['tilt_max'] for r in res if r['placed']])))
    print(json.dumps(summary, indent=1))
    json.dump(dict(summary=summary, episodes=res), open('results_waist.json', 'w'), indent=0)
