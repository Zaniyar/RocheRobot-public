"""Profile "Stehend mit Balance" und "Gehen und Greifen": Becken frei, die Laufpolicy hält das Gleichgewicht.

Ablauf: einschwingen, gegebenenfalls zum Tisch gehen, Arme in Heimhaltung führen, gemessene Beckenpose
ins Planungsmodell übernehmen, sanften Griff planen und abspielen. Die Bahn läuft in Weltkoordinaten.
Mit correct=True gleicht eine Jacobi-Korrektur die Beckenbewegung gegenüber der Planungspose aus.
Die Kriterien entsprechen measure.py. Bestehen ist ein Sim-zu-Sim-Ergebnis, kein Nachweis am Roboter.
"""
import json, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import measure as M
import mujoco as mj
from balance_env import Balance
from gentle_expert import GentlePlanner, PlanFail
from roche_env import RocheKitBoxEnv, GRIP_OPEN, TABLE_TOP, KIT_HALF_Z, KIT_X_RANGE, KIT_Y_RANGE
from selfcheck import SelfCheck, world_contact

XML = Path(__file__).resolve().parent / 'scenes/floating.xml'
STAND_X = .05         # Standposition; schon 12 cm hinter null sind nur noch 3 von 28 Griffen planbar
COAST = float(__import__('os').environ.get('ROCHE_COAST', .35))           # m, so weit läuft der Roboter nach dem Stoppbefehl noch aus
CONTACT_LIMIT = 5.    # N; darüber stützt oder streift der Roboter am Tisch, das zählt als Fehlschlag

class FloatingLab:
    def __init__(self, render=False):
        self.world = RocheKitBoxEnv(render=render, xml=XML)
        self.plan = RocheKitBoxEnv()
        self.check = SelfCheck(self.world.model, side='right')
        self.pelvis_plan = self.plan.model.body('pelvis').id
        self.pelvis_pos0 = self.plan.model.body_pos[self.pelvis_plan].copy()
        self.pelvis_quat0 = self.plan.model.body_quat[self.pelvis_plan].copy()
        self.plan._home_pose()

    def reset(self, seed, start):
        e, m, d = self.world, self.world.model, self.world.data
        rng = np.random.default_rng(seed)
        mj.mj_resetData(m, d)
        pose = (rng.uniform(*KIT_X_RANGE), rng.uniform(*KIT_Y_RANGE), rng.uniform(-np.pi, np.pi))
        e.kit_start = np.array(pose)
        x, y, yaw = pose
        d.qpos[e.kit_q:e.kit_q + 3] = [x, y, TABLE_TOP + KIT_HALF_Z + .001]
        d.qpos[e.kit_q + 3:e.kit_q + 7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        self.b = Balance(m, d, base=start)
        # Rechter Arm startet in Heimhaltung über dem Tisch. Das Anheben nahe am Tisch streift die Platte
        # oder treibt den Roboter weg (geprüft, siehe README); am echten Roboter also vor dem Herantreten anheben.
        self.b.arm_targets[7:14] = self.plan.home['right']
        d.qpos[e.arm_q['right']] = self.plan.home['right']
        for s in ('left', 'right'):
            d.qpos[e.grip_q[s]] = GRIP_OPEN
            d.ctrl[e.grip_a[s]] = GRIP_OPEN
        d.qfrc_applied[:] = 0
        mj.mj_forward(m, d)
        self.track = dict(fell=False, base=[])
        self.contact = 0.

    def tick(self):
        d, e = self.world.data, self.world
        d.qfrc_applied[e.all_v] = d.qfrc_bias[e.all_v]

    def step(self, command=(0, 0, 0)):
        self.b.step(command, before_physics=self.tick)
        self.contact = max(self.contact, world_contact(self.world.model, self.world.data))
        p, yaw, tilt = self.b.pose()
        self.track['base'].append([*p, yaw, tilt])
        if p[2] < .55 or tilt > 40:
            self.track['fell'] = True
        return p, yaw, tilt

    def station(self, limit=25.):
        """Geht geradeaus auf die Standposition. Einmal stoppen statt regeln: Die Policy setzt erst ab
        etwa .3 m/s Schritte und läuft dann noch aus, eine Regelung würde nur pendeln."""
        for _ in range(int(limit / .02)):
            p, yaw, _ = self.step((.4, 0, 0))
            if self.track['fell']:
                return False
            if STAND_X - p[0] < COAST:
                break
        else:
            return False
        for _ in range(100):
            self.step()
        return not self.track['fell']

    def _tcp_plan(self, q):
        pe = self.plan
        pe.data.qpos[pe.arm_q['right']] = q
        mj.mj_kinematics(pe.model, pe.data)
        return pe.data.site_xpos[pe.tcp['right']].copy()

    def restore(self):
        self.plan.model.body_pos[self.pelvis_plan] = self.pelvis_pos0
        self.plan.model.body_quat[self.pelvis_plan] = self.pelvis_quat0

    def prepare(self):
        """Arme in Heimhaltung führen, gemessene Beckenpose ins Planungsmodell übernehmen."""
        e, d, pe = self.world, self.world.data, self.plan
        if self.walk and not self.station():
            raise PlanFail('Standposition nicht erreicht')
        for _ in range(100):
            self.step()
        pel = self.b.pelvis
        self.pos_plan, self.R_plan = d.xpos[pel].copy(), d.xmat[pel].reshape(3, 3).copy()
        pe.model.body_pos[self.pelvis_plan], pe.model.body_quat[self.pelvis_plan] = self.pos_plan, d.xquat[pel].copy()
        pe.reset(kit_pose=tuple(e.kit_start))
        qi = pe.arm_q['left']
        pe.data.qpos[qi] = self.b.arm_targets[:7]       # linker Arm steht wie in der Welt
        mj.mj_kinematics(pe.model, pe.data)
        return GentlePlanner(pe, vmax=M.NOMINAL['vmax']).plan(e.kit_pose(), pe.home['right'])

    def corrected(self, q):
        """Dieselbe Handlage trotz Beckenbewegung: Position und Neigung über die Armjacobi ausgleichen."""
        e, m, d, pe = self.world, self.world.model, self.world.data, self.plan
        pel = self.b.pelvis
        want = self._tcp_plan(q)
        Rw = pe.data.site_xmat[pe.tcp['right']].reshape(3, 3)
        R = d.xmat[pel].reshape(3, 3) @ self.R_plan.T
        now = d.xpos[pel] + R @ (want - self.pos_plan)
        jacp, jacr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        mj.mj_jacSite(m, d, jacp, jacr, e.tcp['right'])
        v = e.arm_v['right']
        J = np.vstack([jacp[:, v], .3 * jacr[:, v]])
        rot = Rotation.from_matrix(Rw @ (R @ Rw).T).as_rotvec()
        return q + J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), np.r_[want - now, .3 * rot])

    def episode(self, seed, start=(0., 0.), walk=False, correct=True, keep=None):
        e, m, d = self.world, self.world.model, self.world.data
        self.reset(seed, start)
        res = dict(seed=seed, start=list(start), plan_fail=None, fell=False, placed=False, gentle=False, self_hit=False, tilt_max=0.)
        self.walk = walk
        try:
            steps = self.prepare()
        except PlanFail as x:
            res.update(plan_fail=str(x), fell=self.track['fell'])
            self.restore()
            return res
        lo, hi = m.jnt_range[e.arm_j['right']].T
        tilt_max, clear = 0., 1.
        t0 = len(self.track['base'])
        for t, (q, g) in enumerate(steps):
            target = self.corrected(q) if correct else q
            self.b.arm_targets[7:14] = np.clip(target, lo, hi)
            d.ctrl[e.grip_a['right']] = g
            self.step()
            R = d.xmat[e.kit].reshape(3, 3)
            if d.xpos[e.kit][2] - (TABLE_TOP + KIT_HALF_Z) > .012:
                tilt_max = max(tilt_max, float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1)))))
            if t % 5 == 0:
                clear = min(clear, self.check.worst(d.qpos)[0])
            if keep is not None:
                keep(t, self.b.arm_targets[7:14].copy(), g)
            if self.track['fell']:
                break
        for _ in range(40):
            self.step()
        R = d.xmat[e.kit].reshape(3, 3)
        final = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
        hit = clear < -M.SELF_TOL
        touching = self.contact > CONTACT_LIMIT
        in_box = e.kit_in_box()
        fell = self.track['fell']
        base = np.array(self.track['base'][t0:])
        res.update(fell=fell, in_box=bool(in_box), final_tilt=final, self_hit=bool(hit), clearance_mm=float(clear * 1000),
                   placed=bool(in_box and final < 10 and not hit and not fell and not touching), tilt_max=tilt_max, table_force=float(self.contact),
                   gentle=bool(in_box and final < 10 and tilt_max < M.TILT_LIMIT and not hit and not fell and not touching),
                   sway_mm=float(np.ptp(base[:, :2], axis=0).max() * 1000), body_tilt_max=float(base[:, 4].max()),
                   base_final=[float(x) for x in base[-1, :2]], duration=len(steps) * .02)
        self.restore()
        return res

RUNS = [('balance_open_loop', (STAND_X, 0.), False, False), ('balance_corrected', (STAND_X, 0.), False, True),
        ('walk_1.5m', (-1.5, 0.), True, True)]

_lab = None
def work(job):
    global _lab
    if _lab is None:
        _lab = FloatingLab()
    seed, start, walk, correct = job
    return _lab.episode(seed, start=start, walk=walk, correct=correct)

def summary(name, res):
    ok = [r for r in res if r['placed']]
    return dict(name=name, n=len(res), placed=len(ok), gentle=sum(r['gentle'] for r in res), fell=sum(r['fell'] for r in res),
                refused=sum(bool(r['plan_fail']) and not r['fell'] for r in res), self_hit=sum(r['self_hit'] for r in res), table_contact=sum(r.get('table_force', 0) > CONTACT_LIMIT for r in res),
                tilt_median=float(np.median([r['tilt_max'] for r in ok])) if ok else None,
                sway_median_mm=float(np.median([r['sway_mm'] for r in ok])) if ok else None,
                body_tilt_max=float(max(r['body_tilt_max'] for r in ok)) if ok else None)

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    t0 = time.time()
    out = {}
    with Pool(14) as pool:
        for name, start, walk, correct in (RUNS if len(sys.argv) < 4 else [r for r in RUNS if r[0] in sys.argv[3]]):
            res = pool.map(work, [(s, start, walk, correct) for s in range(a, b)], chunksize=1)
            out[name] = dict(summary=summary(name, res), episodes=res)
            print(json.dumps(out[name]['summary']), flush=True)
    json.dump(dict(date='2026-11-02', seeds=[a, b - 1], seconds=round(time.time() - t0), **out), open('results_floating.json', 'w'), indent=0)
    print(round(time.time() - t0), 's')
