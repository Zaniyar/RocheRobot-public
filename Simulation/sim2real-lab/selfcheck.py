"""Prüft Selbstkollisionen des G1: Arme gegen Körper und gegen den anderen Arm.

Die Szene schaltet Selbstkollision ab. Hier werden deshalb die Abstände direkt berechnet,
auf Basis der sichtbaren Meshes (konvexe Hüllen je Mesh, also eher konservativ).
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mujoco-scene'))
import mujoco as mj

ARM = ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist_roll', 'wrist_pitch', 'wrist_yaw', 'dex1')
BODY = ('torso', 'pelvis', 'head', 'waist', 'logo', 'hip', 'knee')

def link_side(name):
    return 'left' if name.startswith('left_') else 'right' if name.startswith('right_') else None

def is_arm(name):
    return any(k in name for k in ARM)

class SelfCheck:
    def __init__(self, model, margin=.02, side=None):
        self.m, self.d, self.margin = model, mj.MjData(model), margin
        m = model
        vis = [i for i in range(m.ngeom) if m.geom_type[i] == mj.mjtGeom.mjGEOM_MESH and m.geom_group[i] == 1 and m.geom_bodyid[i] > 0]
        name = lambda g: m.body(m.geom_bodyid[g]).name
        arms = [g for g in vis if is_arm(name(g))]
        torso = [g for g in vis if not is_arm(name(g)) and any(k in name(g) for k in BODY)]
        self.pairs = []
        for a in arms:
            na = name(a)
            for b in torso:
                # Schulter und Oberkörper sind durch das Gelenk verbunden und überlappen konstruktiv.
                if 'shoulder_pitch' in na and any(k in name(b) for k in ('torso', 'waist', 'logo', 'head')):
                    continue
                self.pairs.append((a, b))
        for a in arms:
            for b in arms:
                if a < b and link_side(name(a)) != link_side(name(b)):
                    self.pairs.append((a, b))
        if side:   # nur Paare mit dem bewegten Arm, der Rest ändert sich nicht
            self.pairs = [p for p in self.pairs if link_side(name(p[0])) == side or link_side(name(p[1])) == side]
        self.name = name
        self.fromto = np.zeros(6)

    def worst(self, qpos):
        """Kleinster Abstand aller Paare in Metern; negativ = Durchdringung."""
        m, d = self.m, self.d
        d.qpos[:] = qpos
        mj.mj_kinematics(m, d)
        best, pair = 1., None
        for a, b in self.pairs:
            dist = mj.mj_geomDistance(m, d, a, b, self.margin + .05, self.fromto)
            if dist < best:
                best, pair = dist, (self.name(a), self.name(b))
        return best, pair

    def report(self, qpos, below=.0):
        m, d = self.m, self.d
        d.qpos[:] = qpos
        mj.mj_kinematics(m, d)
        out = []
        for a, b in self.pairs:
            dist = mj.mj_geomDistance(m, d, a, b, .1, self.fromto)
            if dist < below:
                out.append((round(float(dist) * 1000, 1), self.name(a), self.name(b)))
        return sorted(out)

if __name__ == '__main__':
    from roche_env import RocheKitBoxEnv, HOME_TCP
    from gentle_expert import GentlePlanner, PlanFail
    e = RocheKitBoxEnv()
    e.reset(seed=2002)
    c = SelfCheck(e.model)
    print('Paare', len(c.pairs), 'HOME_TCP', HOME_TCP)
    print('Home, Abstand unter 20 mm (mm, Körper A, Körper B):')
    for row in c.report(e.data.qpos, .02):
        print(' ', row)
    planner = GentlePlanner(e)
    steps = planner.plan(e.kit_pose(), e.home['right'])
    worst, hits = 1., {}
    q = e.data.qpos.copy()
    for s, (arm, _) in enumerate(steps[::5]):
        q[e.arm_q['right']] = arm
        for row in c.report(q, 0.):
            hits[row[1:]] = min(hits.get(row[1:], 0), row[0])
    print('Bahn, Durchdringungen (mm):', hits or 'keine')

_force = np.zeros(6)
def world_contact(m, d):
    """Grösste Normalkraft (N) zwischen Roboter und Tisch oder Box. Boden und Kit zählen nicht."""
    worst = 0.
    for i in range(d.ncon):
        c = d.contact[i]
        b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
        if (b1 == 0) == (b2 == 0):                    # genau eine Seite muss statisch sein
            continue
        static, other = (c.geom1, b2) if b1 == 0 else (c.geom2, b1)
        if m.geom(static).name == 'floor' or m.body(other).name == 'kit':
            continue
        mj.mj_contactForce(m, d, i, _force)
        worst = max(worst, abs(_force[0]))
    return worst
