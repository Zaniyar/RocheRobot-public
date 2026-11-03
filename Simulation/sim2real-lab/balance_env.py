"""Freistehender G1 in MuJoCo: Unitrees Wholebody-Dex1-Laufpolicy hält Gleichgewicht und geht.

Sim-zu-Sim-Übertragung einer in Isaac trainierten Policy. Beobachtung und Takt wie in
Simulation/quest_walk_policy.py. Bestehen hier belegt nichts über den echten Roboter.
"""
import os
from collections import deque
from pathlib import Path
import numpy as np
import mujoco as mj

HERE = Path(__file__).resolve().parent
POLICY = os.environ.get('ROCHE_WALK_POLICY', 'D:/RocheRuntime/unitree_sim_isaaclab/assets/model/policy.onnx')
LEGS = [f'{s}_{j}_joint' for j in ('hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll') for s in ('left', 'right')]
ARMS = [f'{s}_{j}_joint' for s in ('left', 'right') for j in ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist_roll', 'wrist_pitch', 'wrist_yaw')]
WAIST = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']
BODY = ['left_hip_pitch_joint', 'right_hip_pitch_joint', 'waist_yaw_joint', 'left_hip_roll_joint', 'right_hip_roll_joint', 'waist_roll_joint', 'left_hip_yaw_joint', 'right_hip_yaw_joint', 'waist_pitch_joint', 'left_knee_joint', 'right_knee_joint', 'left_shoulder_pitch_joint', 'right_shoulder_pitch_joint', 'left_ankle_pitch_joint', 'right_ankle_pitch_joint', 'left_shoulder_roll_joint', 'right_shoulder_roll_joint', 'left_ankle_roll_joint', 'right_ankle_roll_joint', 'left_shoulder_yaw_joint', 'right_shoulder_yaw_joint', 'left_elbow_joint', 'right_elbow_joint', 'left_wrist_roll_joint', 'right_wrist_roll_joint', 'left_wrist_pitch_joint', 'right_wrist_pitch_joint', 'left_wrist_yaw_joint', 'right_wrist_yaw_joint']
DEFAULTS = [('hip_pitch', -.2), ('knee', .42), ('ankle_pitch', -.23), ('elbow', .87), ('shoulder_pitch', .35), ('left_shoulder_roll', .18), ('right_shoulder_roll', -.18)]

def default_q(name):
    for pattern, value in DEFAULTS:
        if pattern in name:
            return value
    return 0.

class Balance:
    """Schritt = 20 ms: ein Policy-Aufruf, danach zehn Physikschritte zu je 2 ms."""
    def __init__(self, model, data, base=(0, 0), z=.80):
        self.m, self.d = model, data
        import onnxruntime as ort  # nur für Balance-Profile nötig
        self.session = ort.InferenceSession(POLICY, providers=['CPUExecutionProvider'])
        j = lambda n: model.jnt_qposadr[model.joint(n).id]
        v = lambda n: model.jnt_dofadr[model.joint(n).id]
        a = lambda n: model.actuator(n).id
        self.q_obs = np.array([j(n) for n in LEGS + ARMS])
        self.v_obs = np.array([v(n) for n in LEGS + ARMS])
        self.def_obs = np.array([default_q(n) for n in LEGS + ARMS], np.float32)
        self.leg_a = np.array([a(n) for n in LEGS])
        self.leg_def = np.array([default_q(n) for n in LEGS])
        self.arm_a = np.array([a(n) for n in ARMS])
        self.waist_a = np.array([a(n) for n in WAIST])
        self.body = BODY
        self.arm_targets = np.array([default_q(n) for n in ARMS])
        self.z0, self.base0 = z, base
        self.free_q = model.jnt_qposadr[model.joint('pelvis_free').id]
        self.free_v = model.jnt_dofadr[model.joint('pelvis_free').id]
        self.pelvis = model.body('pelvis').id
        self.reset()

    def reset(self):
        m, d = self.m, self.d
        d.qpos[self.free_q:self.free_q + 7] = [*self.base0, self.z0, 1, 0, 0, 0]
        for n in LEGS + ARMS + WAIST:
            d.qpos[m.jnt_qposadr[m.joint(n).id]] = default_q(n)
        d.ctrl[self.leg_a] = self.leg_def
        d.ctrl[self.arm_a] = self.arm_targets
        d.ctrl[self.waist_a] = 0
        self.history = deque(maxlen=10)
        self.previous = np.zeros(29, np.float32)
        mj.mj_forward(m, d)

    def obs(self, command):
        d = self.d
        R = d.xmat[self.pelvis].reshape(3, 3)
        omega = d.qvel[self.free_v + 3:self.free_v + 6]   # freejoint: Winkelgeschwindigkeit im Körperrahmen
        gravity = R.T @ np.array([0, 0, -1.])
        o = np.concatenate((omega, gravity, [*command, .8], d.qpos[self.q_obs] - self.def_obs, d.qvel[self.v_obs], self.previous)).astype(np.float32)
        return o

    def policy(self, command):
        o = self.obs(command)
        if not self.history:
            self.history.extend([o.copy()] * 10)
        else:
            self.history.append(o)
        x = np.clip(np.concatenate(self.history)[None], -100, 100).astype(np.float32)
        raw = self.session.run(None, {'obs': x})[0][0]
        self.d.ctrl[self.leg_a] = np.clip(raw, -100, 100) * .25 + self.leg_def
        self.d.ctrl[self.arm_a] = self.arm_targets
        # Wie in quest_walk_policy.py: Nicht-Beingelenke liefern ihr absolutes Ziel.
        full = {n: t for n, t in zip(ARMS, self.arm_targets)}
        full.update({n: 0. for n in WAIST})
        full.update({n: r for n, r in zip(LEGS, raw)})
        self.previous = np.array([full[n] for n in self.body], np.float32)

    def step(self, command=(0, 0, 0), before_physics=None):
        self.policy(command)
        for _ in range(10):
            if before_physics:
                before_physics()
            mj.mj_step(self.m, self.d)

    def pose(self):
        q = self.d.qpos[self.free_q:self.free_q + 7]
        yaw = np.arctan2(2 * (q[3] * q[6] + q[4] * q[5]), 1 - 2 * (q[5] ** 2 + q[6] ** 2))
        up = self.d.xmat[self.pelvis][8]
        return q[:3].copy(), float(yaw), float(np.degrees(np.arccos(np.clip(up, -1, 1))))
