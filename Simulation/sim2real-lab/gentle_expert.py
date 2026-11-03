"""Sanfter Greifablauf: Kit bleibt beim Tragen aufrecht, Bewegung nach Min-Jerk-Zeitgesetz.

Unterschied zu mujoco-scene/scripted_expert.py:
- Handorientierung nach dem Griff konstant (nur Drehung um die Weltsenkrechte erlaubt).
- Vorab vollständig berechnete Gelenktrajektorie; dasselbe Format könnte später ein echter
  Arm-Client abspielen. Es gibt keine Rückmeldung aus dem Simulator während der Ausführung.
- Geplant wird auf einem unveränderten Nominalmodell (planner). Abweichungen der "Welt"
  (Basisversatz, Regler, Reibung) sieht der Planer also nicht, wie am echten Roboter.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import mujoco as mj
from selfcheck import SelfCheck
from roche_env import GRIP_OPEN, GRIP_CLOSE, TABLE_TOP, BOX_CENTER, BOX_HEIGHT, KIT_HALF_Z, SIDES

GRASP_OFFSET = .014
CLEARANCE = .025      # Kitboden über Boxkante beim Tragen
PLACE_GAP = .006      # Kitboden über Boxboden beim Loslassen
BOX_FLOOR = .004
POS_TOL, ROT_TOL = .0025, np.radians(1.5)
ELBOW_OUT = -.2       # rad, Schulterrolle rechts: Oberarm bleibt vom Körper weg
CHECK_EVERY = 5       # jeder wievielte Steuerschritt auf Selbstkollision geprüft wird
MAX_SEGMENT = 12.     # s; längere Segmente deuten auf eine Singularität hin
ALPHA = np.radians([0, 10, -10, 20, -20, 30, -30, 40, -40, 50, -50, 60, -60])
PSI = np.radians([0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180])

class PlanFail(Exception):
    pass

def min_jerk(t):
    return 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5

def grasp_yaw(q):
    w, x, y, z = q
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return (yaw + np.pi / 2) % np.pi - np.pi / 2

class GentlePlanner:
    side = 'right'

    def __init__(self, planner_env, vmax=.08, omega=.7):
        self.e, self.vmax, self.omega = planner_env, vmax, omega
        self.d = mj.MjData(self.e.model)
        s = self.side
        self.qi, self.site = self.e.arm_q[s], self.e.tcp[s]
        self.lo, self.hi = self.e.model.jnt_range[self.e.arm_j[s]].T.copy()
        self.hi[1] = min(self.hi[1], ELBOW_OUT)
        self.check = SelfCheck(self.e.model, side=s)

    def fk(self, q):
        self.d.qpos[self.qi] = q
        mj.mj_kinematics(self.e.model, self.d)
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def solve(self, xyz, R, q0, nfev=40):
        def res(q):
            p, M = self.fk(q)
            return np.r_[10 * (p - xyz), .6 * (M - R).ravel(), .004 * (q - q0)]
        r = least_squares(res, np.clip(q0, self.lo + 1e-6, self.hi - 1e-6), bounds=(self.lo, self.hi), max_nfev=nfev)
        p, M = self.fk(r.x)
        ang = np.linalg.norm(Rotation.from_matrix(M.T @ R).as_rotvec())
        return r.x, float(np.linalg.norm(p - xyz)), float(ang)

    def line(self, q, a, b, Ra, psi=0.):
        """Gerade von a nach b, dabei Drehung psi um die Weltsenkrechte. Dauer wird gestreckt,
        bis Geschwindigkeits- und Gelenkgrenzen eingehalten sind."""
        dt = self.e.control_dt
        dist = np.linalg.norm(b - a) + abs(psi) * .05
        T = max(1.875 * dist / self.vmax, .4)
        for _ in range(4):
            n = max(2, int(T / dt))
            out, qk, ok = [], q.copy(), True
            for i in range(1, n + 1):
                s = min_jerk(i / n)
                R = Rotation.from_euler('z', psi * s).as_matrix() @ Ra
                qk, perr, rerr = self.solve(a + s * (b - a), R, qk, nfev=12)
                if perr > POS_TOL or rerr > ROT_TOL:
                    qk, perr, rerr = self.solve(a + s * (b - a), R, qk, nfev=60)
                    if perr > POS_TOL or rerr > ROT_TOL:
                        raise PlanFail(f'Pfad {perr * 1000:.1f} mm / {np.degrees(rerr):.1f} Grad')
                out.append(qk.copy())
            rate = np.abs(np.diff(np.vstack([q, out]), axis=0)).max() / dt
            if rate <= self.omega * 1.05:
                return out, qk
            T *= rate / self.omega * 1.05
            if T > MAX_SEGMENT:
                raise PlanFail('Segment zu langsam (Singularität)')
        raise PlanFail('Gelenkrate nicht einhaltbar')

    def joint_move(self, q0, q1):
        dt = self.e.control_dt
        T = max(1.875 * np.abs(q1 - q0).max() / self.omega, .6)
        n = int(T / dt)
        return [q0 + min_jerk(i / n) * (q1 - q0) for i in range(1, n + 1)]

    def key(self, xyz, R, seeds):
        """Schlüsselpose mit mehreren Startwerten; None wenn nicht erreichbar."""
        for q0 in seeds:
            q, perr, rerr = self.solve(xyz, R, q0, nfev=60)
            if perr < POS_TOL and rerr < ROT_TOL:
                return q
        return None

    def clear(self, moves):
        """True, wenn die ganze Bahn ohne Selbstkollision bleibt."""
        qpos = self.d.qpos.copy()
        for seg in moves:
            for q in seg[::CHECK_EVERY] + seg[-1:]:
                qpos[self.qi] = q
                if self.check.worst(qpos)[0] < 0:
                    return False
        return True

    def try_grasp(self, grasp, lift, above, over_box, place, R, q_home):
        seeds = [q_home, *self.fixed_seeds]
        q_g = self.key(grasp, R, seeds)
        if q_g is None:
            return None
        q_pre, q_lift = self.key(above, R, [q_g]), self.key(lift, R, [q_g])
        if q_pre is None or q_lift is None:
            return None
        for psi in PSI:
            Rp = Rotation.from_euler('z', psi).as_matrix() @ R
            q_over = self.key(over_box, Rp, [q_lift, q_home])
            if q_over is None or self.key(place, Rp, [q_over]) is None:
                continue
            try:
                seg_desc, _ = self.line(q_pre, above, grasp, R)
                seg_lift, q1 = self.line(seg_desc[-1], grasp, lift, R)
                seg_carry, q2 = self.line(q1, lift, over_box, R, psi)
                seg_down, q3 = self.line(q2, over_box, place, Rp)
                seg_up, q4 = self.line(q3, place, over_box, Rp)
            except PlanFail:
                continue
            moves = self.joint_move(q_home, q_pre), seg_desc, seg_lift, seg_carry, seg_down, seg_up, self.joint_move(q4, q_home)
            if not self.clear(moves):
                continue
            self.psi = float(psi)
            return q_pre, seg_desc, seg_lift, seg_carry, seg_down, seg_up, q4
        return None

    def plan(self, kit_pose_seen, q_home, place_target=None):
        e = self.e
        self.d.qpos[:] = e.data.qpos
        self.fixed_seeds = list(np.random.default_rng(11).uniform(self.lo, self.hi, (4, 7)))
        kx, ky = kit_pose_seen[:2]
        yaw = grasp_yaw(kit_pose_seen[3:])
        tcp_kit = GRASP_OFFSET + KIT_HALF_Z
        grasp = np.array([kx, ky, TABLE_TOP + tcp_kit])
        above = grasp + [0, 0, .05]
        carry_z = TABLE_TOP + BOX_HEIGHT + CLEARANCE + tcp_kit
        lift = np.array([kx, ky, carry_z])
        bx, by = BOX_CENTER if place_target is None else place_target
        over_box = np.array([bx, by, carry_z])
        place = np.array([bx, by, TABLE_TOP + BOX_FLOOR + PLACE_GAP + tcp_kit])
        # Hand darf nur um die Schliessachse kippen; die Fingerflächen liegen dann weiter flach am Kit.
        found = None
        for alpha in ALPHA:
            for y in (yaw, yaw - np.pi if yaw > 0 else yaw + np.pi):
                R = Rotation.from_euler('z', y).as_matrix() @ Rotation.from_euler('y', np.pi / 2 + alpha).as_matrix()
                found = self.try_grasp(grasp, lift, above, over_box, place, R, q_home)
                if found:
                    self.alpha = float(alpha)
                    break
            if found:
                break
        if not found:
            raise PlanFail('kein aufrechter Gesamtweg')
        q_pre, seg_desc, seg_lift, seg_carry, seg_down, seg_up, q_end = found
        dt = e.control_dt
        hold = lambda q, sec: [q.copy()] * int(sec / dt)
        ramp = lambda a, b, sec: [a + min_jerk((i + 1) / int(sec / dt)) * (b - a) for i in range(int(sec / dt))]
        steps = []
        def add(qs, grip):
            steps.extend((q, g) for q, g in zip(qs, grip if hasattr(grip, '__len__') else [grip] * len(qs)))
        add(self.joint_move(q_home, q_pre), GRIP_OPEN)
        add(seg_desc, GRIP_OPEN)
        add(hold(seg_desc[-1], .25), GRIP_OPEN)
        add(hold(seg_desc[-1], 1.), ramp(GRIP_OPEN, GRIP_CLOSE, 1.))
        add(hold(seg_desc[-1], .3), GRIP_CLOSE)
        add(seg_lift, GRIP_CLOSE)
        add(hold(seg_lift[-1], .25), GRIP_CLOSE)
        add(seg_carry, GRIP_CLOSE)
        add(hold(seg_carry[-1], .35), GRIP_CLOSE)     # Ausschwingen vor dem Absenken
        add(seg_down, GRIP_CLOSE)
        add(hold(seg_down[-1], .4), GRIP_CLOSE)
        add(hold(seg_down[-1], 1.4), ramp(GRIP_CLOSE, GRIP_OPEN, 1.4))
        add(hold(seg_down[-1], .3), GRIP_OPEN)
        add(seg_up, GRIP_OPEN)
        add(self.joint_move(q_end, q_home), GRIP_OPEN)
        return steps
