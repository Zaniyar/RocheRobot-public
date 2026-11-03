"""Unabhängige Gegenprobe zu selfcheck.py: exakte Dreiecksnetze statt konvexer Hüllen.

Zählt Armpunkte, die innerhalb des Rumpfnetzes liegen (Strahlprobe mit ungerader Trefferzahl).
Positivkontrolle ist das alte Skript und eine absichtlich falsche Armpose.
"""
import numpy as np, mujoco as mj
import measure as M
from gentle_expert import GentlePlanner, PlanFail

def mesh_world(m, d, g):
    mid = m.geom_dataid[g]
    va, fa = m.mesh_vertadr[mid], m.mesh_faceadr[mid]
    v = m.mesh_vert[va:va + m.mesh_vertnum[mid]].astype(float)
    f = m.mesh_face[fa:fa + m.mesh_facenum[mid]]
    return v @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g], f

def inside(points, verts, faces, direction=np.array([.31, .77, .55])):
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    e1, e2 = b - a, c - a
    h = np.cross(direction, e2)
    det = (e1 * h).sum(1)
    ok = np.abs(det) > 1e-12
    a, e1, e2, h, det = a[ok], e1[ok], e2[ok], h[ok], det[ok]
    out = np.zeros(len(points), bool)
    for i, p in enumerate(points):
        s = p - a
        u = (s * h).sum(1) / det
        q = np.cross(s, e1)
        v = (direction * q).sum(1) / det
        t = (e2 * q).sum(1) / det
        out[i] = ((u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)).sum() % 2 == 1
    return out

class Exact:
    def __init__(self, model, stride=3):
        self.m, self.d, self.stride = model, mj.MjData(model), stride
        vis = [i for i in range(model.ngeom) if model.geom_type[i] == mj.mjtGeom.mjGEOM_MESH and model.geom_group[i] == 1]
        name = lambda g: model.body(model.geom_bodyid[g]).name
        self.arm = [g for g in vis if name(g).startswith('right_') and any(k in name(g) for k in ('shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist', 'dex1'))]
        self.body = [g for g in vis if any(k in name(g) for k in ('torso', 'logo', 'head', 'waist', 'pelvis'))]
        self.name = name

    def count(self, qpos):
        m, d = self.m, self.d
        d.qpos[:] = qpos
        mj.mj_kinematics(m, d)
        hits = {}
        for g in self.arm:
            pts = mesh_world(m, d, g)[0][::self.stride]
            for b in self.body:
                vb, fb = mesh_world(m, d, b)
                lo, hi = vb.min(0), vb.max(0)
                near = pts[np.all((pts > lo) & (pts < hi), axis=1)]
                if len(near):
                    n = int(inside(near, vb, fb).sum())
                    if n:
                        hits[(self.name(g), self.name(b))] = n
        return hits

if __name__ == '__main__':
    lab = M.Lab()
    e = lab.plan_env
    x = Exact(e.model)
    e.reset(seed=4000)
    q = e.data.qpos.copy()
    q[e.arm_q['right']] = [-1.2, .9, 0, 1.2, 0, 0, 0]
    print('Kontrolle, Arm absichtlich im Körper:', x.count(q))
    print('Home:', x.count(e.data.qpos))
    total, planned = {}, 0
    for seed in range(4000, 4012):
        e.reset(seed=seed)
        try:
            steps = GentlePlanner(e).plan(e.kit_pose(), e.home['right'])
        except PlanFail:
            continue
        planned += 1
        q = e.data.qpos.copy()
        for arm, _ in steps[::12]:
            q[e.arm_q['right']] = arm
            for k, n in x.count(q).items():
                total[k] = max(total.get(k, 0), n)
    print('Sanfte Bahnen', planned, 'Treffer (grösste Punktzahl):', total or 'keine')
    e.reset(seed=4000)
    rng = np.random.default_rng(14000)
    import scripted_expert as se
    old, q = {}, e.data.qpos.copy()
    for k, a in enumerate(se.ScriptedExpert(e, rng).actions()):
        if k % 12 == 0:
            q[e.arm_q['right']] = a[8:15]
            for key, n in x.count(q).items():
                old[key] = max(old.get(key, 0), n)
    print('Altes Skript, Kontrolle:', old or 'keine')
