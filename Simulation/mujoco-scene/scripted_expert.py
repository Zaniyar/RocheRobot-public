"""Skriptbasierter Demonstrator (kein gelerntes Modell): rechte Hand greift das Kit und stellt es in die Box.

Nutzt nur Gelenksollwerte (wie ein Teleoperator/eine Policy); keine Teleportation, kein Weld.
Dient zum schnellen Erzeugen von Trainingsdaten und als Plausibilitätstest der Szene.
"""
import numpy as np
from roche_env import RocheKitBoxEnv, GRIP_OPEN, GRIP_CLOSE, TABLE_TOP, BOX_CENTER, KIT_HALF_Z, BOX_HEIGHT

GRASP_OFFSET = .014   # TCP liegt so viel über der Kitmitte (wie im Kontaktprüfstand)
SPEED = .15           # m/s kartesisch
MAX_JOINT_STEP = .05  # rad pro 20-ms-Schritt

def kit_yaw(kit_quat):
    w, x, y, z = kit_quat
    return np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

def grasp_yaw(kit_quat):
    # Greifer ist symmetrisch: Winkel modulo pi in [-pi/2, pi/2)
    return (kit_yaw(kit_quat) + np.pi / 2) % np.pi - np.pi / 2

class ScriptedExpert:
    side = 'right'

    def __init__(self, env: RocheKitBoxEnv, rng=None):
        self.env = env
        self.rng = rng if rng is not None else np.random.default_rng()

    def plan(self):
        k = self.env.kit_pose()
        yaw = grasp_yaw(k[3:])
        kx, ky, kz = k[:3]
        grasp_z = kz + GRASP_OFFSET
        place_z = TABLE_TOP + .008 + KIT_HALF_Z + GRASP_OFFSET + .015
        carry_z = TABLE_TOP + BOX_HEIGHT + 2 * KIT_HALF_Z + .04
        # kleine Variation der Ablage, damit die Demonstrationen nicht identisch sind
        bx, by = BOX_CENTER + self.rng.uniform(-.015, .015, 2) * [1, .5]
        # (Ziel-TCP, Gierwinkel der Greifachse, Greifer, Haltezeit s)
        return [((kx, ky, grasp_z + .10), yaw, GRIP_OPEN, .1),
                ((kx, ky, grasp_z), yaw, GRIP_OPEN, .2),
                ((kx, ky, grasp_z), yaw, GRIP_CLOSE, .5),
                ((kx, ky, carry_z), yaw, GRIP_CLOSE, .1),
                ((bx, by, carry_z), 0., GRIP_CLOSE, .1),
                ((bx, by, place_z), 0., GRIP_CLOSE, .2),
                ((bx, by, place_z), 0., GRIP_OPEN, .4),
                ((bx, by, carry_z), 0., GRIP_OPEN, .2)]

    def actions(self):
        """Generator: liefert pro Steuerschritt die 16-dim. Aktion."""
        e, s = self.env, self.side
        i = 0 if s == 'left' else 8
        action = e.action.copy()
        q = action[i:i + 7].copy()
        tcp = e.data.site_xpos[e.tcp[s]].copy()
        yaw_now = 0.
        for target, yaw, grip, hold in self.plan():
            target = np.asarray(target, float)
            key, err = e.ik(s, target, yaw, q)          # Zielpose global lösen (mit Neustarts)
            self.max_ik_error = max(getattr(self, 'max_ik_error', 0.), err)
            dist = np.linalg.norm(target - tcp)
            n = max(1, int(dist / (SPEED * e.control_dt)), int(np.abs(key - q).max() / MAX_JOINT_STEP))
            start, yaw0, q_start = tcp.copy(), yaw_now, q.copy()
            for t in range(1, n + 1):
                a = t / n
                a = a * a * (3 - 2 * a)  # sanftes Anfahren/Abbremsen
                goal, gerr = e.ik(s, start + a * (target - start), yaw0 + a * (yaw - yaw0), q, restarts=0)
                if gerr > .005 or np.abs(goal - q).max() > .3:
                    goal = q_start + a * (key - q_start)  # Rückfall: Gelenkraum-Interpolation
                q = q + np.clip(goal - q, -MAX_JOINT_STEP, MAX_JOINT_STEP)
                action[i:i + 7] = q
                yield action.copy()
            for t in range(4):  # Restfehler zur Schlüsselpose abbauen
                q = q + np.clip(key - q, -MAX_JOINT_STEP, MAX_JOINT_STEP)
                action[i:i + 7] = q
                yield action.copy()
            tcp, yaw_now = target, yaw
            for t in range(max(1, int(hold / e.control_dt))):
                action[i + 7] = action[i + 7] + np.clip(grip - action[i + 7], -.002, .002)
                yield action.copy()
