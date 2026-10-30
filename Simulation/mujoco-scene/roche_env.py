"""Simulationsumgebung für Datensammlung: G1 steht am Tisch, Box fest, Reagent Kit zufällig.

    env = RocheKitBoxEnv(render=True)
    obs = env.reset(seed=3)          # Kit bekommt eine neue zufällige Pose, Box bleibt fest
    obs, info = env.step(action)     # action: 16 Werte, siehe ACTION_NAMES

Aktion = absolute Sollwerte (Positionsregler) mit 50 Hz:
    [linker Arm 7 Gelenke, linker Greifer, rechter Arm 7 Gelenke, rechter Greifer]
Greifer: ein Sollwert für beide Dex1-Finger (Meter); OPEN = offen, CLOSE = geschlossen.
"""
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import mujoco as mj

HERE = Path(__file__).resolve().parent
SIDES = ('left', 'right')
ARM_JOINTS = {s: [f'{s}_{n}_joint' for n in ['shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow',
                                             'wrist_roll', 'wrist_pitch', 'wrist_yaw']] for s in SIDES}
FINGER_JOINTS = {s: [f'{s}_dex1_finger_joint_1', f'{s}_dex1_finger_joint_2'] for s in SIDES}
ACTION_NAMES = ARM_JOINTS['left'] + ['left_gripper'] + ARM_JOINTS['right'] + ['right_gripper']
GRIP_OPEN, GRIP_CLOSE = .012, -.014
CAMERAS = ('head_cam', 'left_wrist_cam', 'right_wrist_cam', 'overview')

TABLE_TOP = .75
BOX_CENTER = np.array([.32, -.20])
BOX_INNER = np.array([.15, .11])
BOX_HEIGHT = .06
KIT_HALF_Z = .0407
# Zufallsbereich für das Kit (Tischkoordinaten in Weltframe). Disjunkt zur Box.
KIT_X_RANGE = (.28, .37)
KIT_Y_RANGE = (-.08, .08)
HOME_TCP = {'left': (.30, .26, .97), 'right': (.30, -.26, .97)}

def down_rotation(yaw):
    """Hand zeigt nach unten (Hand-x = -z Welt); Finger schliessen entlang Kit-y bei Gierwinkel yaw."""
    return Rotation.from_euler('z', yaw).as_matrix() @ Rotation.from_euler('y', np.pi / 2).as_matrix()

class RocheKitBoxEnv:
    control_dt = .02  # 50 Hz

    def __init__(self, render=False, width=320, height=240, cameras=CAMERAS[:3], xml=HERE / 'scene.xml'):
        self.model = mj.MjModel.from_xml_path(str(xml))
        self.data = mj.MjData(self.model)
        m = self.model
        self.substeps = round(self.control_dt / m.opt.timestep)
        self.arm_q, self.arm_v, self.arm_a, self.grip_a, self.grip_q, self.arm_j = {}, {}, {}, {}, {}, {}
        for s in SIDES:
            j = np.array([m.joint(n).id for n in ARM_JOINTS[s]])
            self.arm_j[s] = j
            self.arm_q[s] = m.jnt_qposadr[j]
            self.arm_v[s] = m.jnt_dofadr[j]
            self.arm_a[s] = np.array([m.actuator(n).id for n in ARM_JOINTS[s]])
            self.grip_a[s] = np.array([m.actuator(n).id for n in FINGER_JOINTS[s]])
            self.grip_q[s] = np.array([m.jnt_qposadr[m.joint(n).id] for n in FINGER_JOINTS[s]])
        self.all_v = np.concatenate([self.arm_v[s] for s in SIDES] +
                                    [m.jnt_dofadr[[m.joint(n).id for n in FINGER_JOINTS[s]]] for s in SIDES])
        self.tcp = {s: m.site(s + '_tcp').id for s in SIDES}
        self.kit = m.body('kit').id
        self.kit_q = m.jnt_qposadr[m.joint('kit_free').id]
        self.kit_v = m.jnt_dofadr[m.joint('kit_free').id]
        self.cameras = list(cameras)
        self.renderer = mj.Renderer(m, height, width) if render else None
        self.rng = np.random.default_rng()
        self.home = None
        self.action = np.zeros(len(ACTION_NAMES))

    # ---------- Kinematik ----------
    def ik(self, side, xyz, yaw, q0=None, restarts=8, tol=2e-3, down_weight=.04):
        """Greif-IK mit Gelenkgrenzen und Neustarts; verändert die Simulation nicht.
        Ziel: TCP auf xyz, Fingerschliessachse (Hand-y) parallel zur schmalen Kitachse bei Gierwinkel yaw.
        Senkrechtes Greifen von oben wird nur weich bevorzugt; die Hand darf kippen (G1-Reichweite).
        Gibt (Gelenkwinkel, Positionsfehler m) zurück; self.last_ik zeigt Achsfehler und Neigung."""
        from scipy.optimize import least_squares
        m = self.model
        d = mj.MjData(m)
        d.qpos[:] = self.data.qpos
        qi, site = self.arm_q[side], self.tcp[side]
        lo, hi = m.jnt_range[self.arm_j[side]].T
        q0 = d.qpos[qi].copy() if q0 is None else np.clip(np.asarray(q0, float), lo, hi)
        xyz = np.asarray(xyz, float)
        axis = np.array([-np.sin(yaw), np.cos(yaw), 0.])
        reg = .01

        def fk(q):
            d.qpos[qi] = q
            mj.mj_kinematics(m, d)
            M = d.site_xmat[site].reshape(3, 3)
            return d.site_xpos[site].copy(), M[:, 0].copy(), M[:, 1].copy()

        def res(q):
            p, hx, hy = fk(q)
            return np.r_[10 * (p - xyz), .15 * np.cross(hy, axis), down_weight * (hx + [0, 0, 1]), reg * (q - q0)]

        best = None
        seeds = [q0] + ([self.home[side]] if self.home and side in self.home else []) + \
            list(np.random.default_rng(7).uniform(lo, hi, (restarts, len(qi))))
        for k, s in enumerate(seeds):
            r = least_squares(res, np.clip(s, lo + 1e-6, hi - 1e-6), bounds=(lo, hi), max_nfev=200, xtol=1e-9)
            p, hx, hy = fk(r.x)
            pos = float(np.linalg.norm(p - xyz))
            axis_err = float(np.linalg.norm(np.cross(hy, axis)))
            tilt = float(np.degrees(np.arccos(np.clip(-hx[2], -1, 1))))
            score = pos + .02 * axis_err + (0 if k == 0 else .003 * np.linalg.norm(r.x - q0))
            if best is None or score < best[0]:
                best = (score, r.x.copy(), pos, axis_err, tilt)
            if pos < tol and axis_err < .1 and k <= 1:
                break  # nahe Lösung gefunden -> kontinuierliche Bewegung
        self.last_ik = {'pos_err': best[2], 'axis_err': best[3], 'tilt_deg': best[4]}
        return best[1], best[2]

    def _home_pose(self):
        if self.home is None:
            guess = {'left': [-1.8247, .582, -.1402, 2.083, .8685, 1.1374, -1.1637],
                     'right': [-1.8247, -.582, .1402, 2.083, -.8685, 1.1374, 1.1637]}  # aus dem Kontaktprüfstand
            self.home = {}
            for s in SIDES:
                q, err = self.ik(s, HOME_TCP[s], 0., guess[s])
                assert err < .005, (s, err)
                self.home[s] = q
        return self.home

    # ---------- Episoden ----------
    def reset(self, seed=None, kit_pose=None):
        """Neue Episode. Box fix; Kit zufällig (x, y, Gierwinkel) innerhalb des Tischbereichs."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        m, d = self.model, self.data
        mj.mj_resetData(m, d)
        home = self._home_pose()
        for s in SIDES:
            d.qpos[self.arm_q[s]] = home[s]
            d.ctrl[self.arm_a[s]] = home[s]
            d.qpos[self.grip_q[s]] = GRIP_OPEN
            d.ctrl[self.grip_a[s]] = GRIP_OPEN
        if kit_pose is None:
            kit_pose = (self.rng.uniform(*KIT_X_RANGE), self.rng.uniform(*KIT_Y_RANGE), self.rng.uniform(-np.pi, np.pi))
        x, y, yaw = kit_pose
        self.kit_start = np.array(kit_pose, float)
        d.qpos[self.kit_q:self.kit_q + 3] = [x, y, TABLE_TOP + KIT_HALF_Z + .001]
        d.qpos[self.kit_q + 3:self.kit_q + 7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        self.action = np.r_[home['left'], GRIP_OPEN, home['right'], GRIP_OPEN]
        mj.mj_forward(m, d)
        for _ in range(10):  # Kit setzt sich ab
            self._physics(self.action)
        return self.observation()

    def _physics(self, action):
        m, d = self.model, self.data
        a = np.asarray(action, float)
        for i, s in enumerate(SIDES):
            d.ctrl[self.arm_a[s]] = a[8 * i:8 * i + 7]
            d.ctrl[self.grip_a[s]] = a[8 * i + 7]
        for _ in range(self.substeps):
            # Ideale Schwerkraft-/Bias-Vorsteuerung für Arme und Finger (unkalibrierte Annahme)
            d.qfrc_applied[:] = 0
            d.qfrc_applied[self.all_v] = d.qfrc_bias[self.all_v]
            mj.mj_step(m, d)

    def step(self, action):
        self.action = np.clip(action, self.model.actuator_ctrlrange[self._ctrl_order(), 0],
                              self.model.actuator_ctrlrange[self._ctrl_order(), 1])
        self._physics(self.action)
        return self.observation(), self.info()

    def _ctrl_order(self):
        return np.r_[self.arm_a['left'], self.grip_a['left'][0], self.arm_a['right'], self.grip_a['right'][0]]

    # ---------- Beobachtungen ----------
    def qpos16(self):
        d = self.data
        return np.r_[d.qpos[self.arm_q['left']], d.qpos[self.grip_q['left']].mean(),
                     d.qpos[self.arm_q['right']], d.qpos[self.grip_q['right']].mean()]

    def qvel16(self):
        d = self.data
        fv = {s: self.model.jnt_dofadr[[self.model.joint(n).id for n in FINGER_JOINTS[s]]] for s in SIDES}
        return np.r_[d.qvel[self.arm_v['left']], d.qvel[fv['left']].mean(),
                     d.qvel[self.arm_v['right']], d.qvel[fv['right']].mean()]

    def kit_pose(self):
        return self.data.qpos[self.kit_q:self.kit_q + 7].copy()  # xyz + Quaternion (w, x, y, z)

    def observation(self):
        obs = {'qpos': self.qpos16(), 'qvel': self.qvel16(), 'kit_pose': self.kit_pose(),
               'tcp_left': self.data.site_xpos[self.tcp['left']].copy(),
               'tcp_right': self.data.site_xpos[self.tcp['right']].copy(), 'time': float(self.data.time)}
        if self.renderer is not None:
            obs['images'] = {}
            for c in self.cameras:
                self.renderer.update_scene(self.data, camera=c)
                obs['images'][c] = self.renderer.render().copy()
        return obs

    def kit_in_box(self):
        p = self.data.xpos[self.kit]
        rel = np.abs(p[:2] - BOX_CENTER)
        return bool(np.all(rel < BOX_INNER / 2) and p[2] < TABLE_TOP + BOX_HEIGHT + KIT_HALF_Z)

    def info(self):
        return {'success': self.kit_in_box(), 'kit_height': float(self.data.xpos[self.kit][2] - TABLE_TOP)}
