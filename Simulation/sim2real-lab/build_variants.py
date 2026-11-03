"""Erzeugt Szenenvarianten, ohne mujoco-scene/scene.xml zu verändern.

    waist.xml     Becken fest, drei Taillengelenke frei und positionsgeregelt
    floating.xml  Becken frei, Beine und Taille geregelt: Gleichgewicht muss eine Policy halten

Gelenke, Achsen und Grenzen kommen aus derselben G1-URDF. Die Beinverstärkungen sind die aus
Simulation/quest_walk_policy.py, damit die Laufpolicy dieselbe Regelstrecke sieht wie beim Training.
"""
from pathlib import Path
import xml.etree.ElementTree as E

HERE = Path(__file__).resolve().parent
SCENE = HERE.parent / 'mujoco-scene'
OUT = HERE / 'scenes'
WAIST = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']
LEGS = [f'{s}_{n}_joint' for s in ('left', 'right') for n in ('hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll')]

def gains(n):
    if 'ankle' in n: return 20, 2
    if 'hip_roll' in n or 'hip_yaw' in n: return 150, 5
    if 'hip_pitch' in n or 'knee' in n: return 200, 5
    if 'waist' in n: return 200, 5
    raise ValueError(n)

def build(name, names, free):
    root = E.parse(SCENE / 'scene.xml').getroot()
    root.find('compiler').set('meshdir', '../../mujoco-scene/assets')
    urdf = E.parse(SCENE / 'assets/g1/g1.urdf').getroot()
    joints = {j.get('name'): j for j in urdf.findall('joint')}
    bodies = {b.get('name'): b for b in root.iter('body')}
    act = root.find('actuator')
    for n in names:
        j = joints[n]
        lim = j.find('limit')
        body = bodies[j.find('child').get('link')]
        el = E.Element('joint', name=n, type='hinge', axis=j.find('axis').get('xyz'),
                       range=lim.get('lower') + ' ' + lim.get('upper'), armature='.01', damping='.3')
        body.insert(0, el)
        kp, kv = gains(n)
        effort = float(lim.get('effort'))
        E.SubElement(act, 'position', name=n, joint=n, kp=str(kp), kv=str(kv),
                     forcerange=f'{-effort} {effort}', ctrlrange=lim.get('lower') + ' ' + lim.get('upper'))
    if free:
        bodies['pelvis'].insert(0, E.Element('freejoint', name='pelvis_free'))
        # Wie in der Laufpolicy: niedrigere Armverstärkungen, damit die Arme nicht gegen die Balance arbeiten.
        for a in act.findall('position'):
            n = a.get('name')
            if 'shoulder_pitch' in n or 'shoulder_roll' in n: a.set('kp', '100'); a.set('kv', '2')
            elif 'shoulder_yaw' in n or 'elbow' in n: a.set('kp', '50'); a.set('kv', '2')
            elif 'wrist' in n: a.set('kp', '40'); a.set('kv', '2')
    OUT.mkdir(exist_ok=True)
    E.ElementTree(root).write(OUT / name, encoding='utf8')

if __name__ == '__main__':
    build('waist.xml', WAIST, False)
    build('floating.xml', WAIST + LEGS, True)
    print('Varianten geschrieben:', OUT)
