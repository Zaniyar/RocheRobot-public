"""Erzeugt scene.xml: stehender Unitree G1 (Dex1) neben Tisch, feste Box, freies Reagent Kit.

Quellen: G1-URDF + Meshes aus dem Training Lab (unitree_ros, gepinnter Commit, BSD-3),
Kit-Geometrie aus kit.glb (Original-Roche-CAD, Aussenmasse 81,5 x 34,5 x 81,4 mm).
Ergebnis ist ein eigenständiger Ordner (assets/ + scene.xml) mit relativen Pfaden.

Aufruf:  python build_scene.py            (benötigt nur beim Neubau trimesh/scipy)
"""
from pathlib import Path
import json, shutil, xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / 'Projectboard/training-demo/assets'
ASSETS = HERE / 'assets'

SIDES = ['left', 'right']
ARM = [s + '_' + n + '_joint' for s in SIDES for n in
       ['shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist_roll', 'wrist_pitch', 'wrist_yaw']]
FINGERS = [s + '_dex1_finger_joint_' + i for s in SIDES for i in '12']

# Szenengeometrie (Meter, Weltkoordinaten; Roboter blickt in +x, rechts = -y)
PELVIS_Z = .79                     # stehender G1, Becken fixiert (keine Balanceregelung nötig)
TABLE_TOP = .75
TABLE_CENTER = (.67, 0.)
TABLE_SIZE = (.94, .96)
BOX_POS = (.32, -.20)              # Box steht IMMER hier (rechts vor dem Roboter)
BOX_INNER = (.15, .11)
BOX_HEIGHT = .06
BOX_WALL = .008
KIT_HALF = (.04075, .01725, .0407)  # Kit aufrecht: 81,5 mm (x) x 34,5 mm (y) x 81,4 mm (z)
KIT_MASS = .1

def vec(s): return np.fromstring(s, sep=' ')
def fmt(v): return ' '.join(f'{float(x):.6g}' for x in v)
def origin(node):
    o = node.find('origin')
    p = '0 0 0' if o is None else o.get('xyz', '0 0 0')
    r = '0 0 0' if o is None else o.get('rpy', '0 0 0')
    q = Rotation.from_euler('xyz', vec(r)).as_quat()
    return {'pos': fmt(vec(p)), 'quat': fmt([q[3], *q[:3]])}

def copy_assets():
    if not SRC.exists():  # z. B. im öffentlichen Export: mitgelieferte assets/ direkt verwenden
        return sorted(p.name for p in (ASSETS / 'kit').glob('kit_part*.stl'))
    (ASSETS / 'g1/meshes').mkdir(parents=True, exist_ok=True)
    for f in ['g1.urdf', 'LICENSE-Unitree.txt', 'provenance.json']:
        shutil.copy2(SRC / f, ASSETS / 'g1' / f)
    for f in (SRC / 'meshes').iterdir():
        shutil.copy2(f, ASSETS / 'g1/meshes' / f.name)
    # Kit: glTF ist Y-up -> MuJoCo Z-up, Teile einzeln für Farben, Mittelpunkt im Ursprung.
    import trimesh
    scene = trimesh.load(SRC / 'kit.glb')
    (ASSETS / 'kit').mkdir(parents=True, exist_ok=True)
    R = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)
    parts = []
    for i, (name, geom) in enumerate(scene.geometry.items()):
        m = geom.copy()
        m.vertices = m.vertices @ R.T
        out = ASSETS / 'kit' / f'kit_part{i}.stl'
        m.export(out)
        parts.append(out.name)
    return parts

def build():
    parts = copy_assets()
    urdf = E.parse(ASSETS / 'g1/g1.urdf').getroot()
    links = {l.get('name'): l for l in urdf.findall('link')}
    children = {}
    for j in urdf.findall('joint'):
        children.setdefault(j.find('parent').get('link'), []).append(j)

    root = E.Element('mujoco', model='roche_g1_table_box_kit')
    E.SubElement(root, 'compiler', angle='radian', inertiafromgeom='false', meshdir='assets', autolimits='true')
    E.SubElement(root, 'option', timestep='.002', integrator='implicitfast', iterations='60',
                 noslip_iterations='5', cone='elliptic')
    vis = E.SubElement(root, 'visual')
    E.SubElement(vis, 'global', offwidth='1280', offheight='960')
    E.SubElement(vis, 'quality', shadowsize='4096')
    E.SubElement(vis, 'headlight', ambient='.35 .35 .35', diffuse='.5 .5 .5')
    default = E.SubElement(root, 'default')
    E.SubElement(default, 'geom', friction='.8 .005 .0001', solref='.008 1', solimp='.95 .99 .001', condim='4')

    asset = E.SubElement(root, 'asset')
    E.SubElement(asset, 'texture', name='grid', type='2d', builtin='checker', rgb1='.32 .34 .36',
                 rgb2='.26 .28 .30', width='512', height='512')
    E.SubElement(asset, 'material', name='floor', texture='grid', texrepeat='8 8', reflectance='.05')
    E.SubElement(asset, 'texture', name='sky', type='skybox', builtin='gradient', rgb1='.85 .88 .92',
                 rgb2='.55 .6 .66', width='256', height='256')
    E.SubElement(asset, 'material', name='table', rgba='.78 .74 .66 1')
    E.SubElement(asset, 'material', name='box', rgba='.16 .42 .66 1')
    E.SubElement(asset, 'material', name='kit_body', rgba='.82 .82 1 1')
    E.SubElement(asset, 'material', name='kit_cap', rgba='.25 .27 .3 1')
    world = E.SubElement(root, 'worldbody')
    act = E.SubElement(root, 'actuator')
    meshes = set()

    E.SubElement(world, 'light', name='key', pos='1.2 -.8 2.4', dir='-.4 .3 -1', diffuse='.7 .7 .7', castshadow='true')
    E.SubElement(world, 'geom', name='floor', type='plane', size='3 3 .05', material='floor', contype='2', conaffinity='5')

    def geometry(parent, g, name, attrs):
        shape = list(g)[0]
        kw = dict(attrs, name=name)
        if shape.tag == 'mesh':
            file = shape.get('filename').replace('package://g1_description/', '')
            key = Path(file).stem
            if key not in meshes:
                E.SubElement(asset, 'mesh', name=key, file='g1/' + file)
                meshes.add(key)
            kw.update(type='mesh', mesh=key)
        elif shape.tag == 'box': kw.update(type='box', size=fmt(vec(shape.get('size')) / 2))
        elif shape.tag == 'cylinder': kw.update(type='cylinder', size=shape.get('radius') + ' ' + str(float(shape.get('length')) / 2))
        elif shape.tag == 'sphere': kw.update(type='sphere', size=shape.get('radius'))
        else: raise ValueError(shape.tag)
        return E.SubElement(parent, 'geom', **kw)

    def recurse(parent, name, joint=None):
        attrs = origin(joint) if joint is not None else {'pos': fmt([0, 0, PELVIS_Z])}
        body = E.SubElement(parent, 'body', name=name, **attrs)
        l = links[name]
        inert = l.find('inertial')
        if inert is not None:
            i = inert.find('inertia')
            o = origin(inert)
            q = vec(o.pop('quat'))
            I = np.array([[float(i.get(a)) for a in r] for r in
                          [('ixx', 'ixy', 'ixz'), ('ixy', 'iyy', 'iyz'), ('ixz', 'iyz', 'izz')]])
            Rm = Rotation.from_quat([*q[1:], q[0]]).as_matrix()
            I = Rm @ I @ Rm.T
            E.SubElement(body, 'inertial', mass=inert.find('mass').get('value'),
                         fullinertia=fmt([I[0, 0], I[1, 1], I[2, 2], I[0, 1], I[0, 2], I[1, 2]]), **o)
        if joint is not None and joint.get('name') in ARM + FINGERS:
            n = joint.get('name')
            lim = joint.find('limit')
            finger = n in FINGERS
            E.SubElement(body, 'joint', name=n, type='slide' if finger else 'hinge', axis=joint.find('axis').get('xyz'),
                         range=lim.get('lower') + ' ' + lim.get('upper'),
                         armature='.002' if finger else '.02', damping='.1' if finger else '.3')
            effort = float(lim.get('effort'))
            kp = 800 if finger else (100 if 'wrist' in n else 160)
            E.SubElement(act, 'position', name=n, joint=n, kp=str(kp), kv='8',
                         forcerange=fmt([-effort, effort]), ctrlrange=lim.get('lower') + ' ' + lim.get('upper'))
        hand = 'dex1' in name
        color = '.79 .82 .93 1' if hand else '.62 .66 .66 1'
        for k, v in enumerate(l.findall('visual')):
            geometry(body, v.find('geometry'), f'{name}_visual_{k}',
                     dict(origin(v), contype='0', conaffinity='0', group='1', rgba=color))
        for k, c in enumerate(l.findall('collision')):
            # Roboter kollidiert mit Umgebung (2) und Kit (4), keine Selbstkollision.
            geometry(body, c.find('geometry'), f'{name}_collision_{k}',
                     dict(origin(c), contype='1', conaffinity='6', group='3', rgba='.8 .3 .2 .3'))
        if name.endswith('_dex1_base_link'):
            side = name.split('_')[0]
            E.SubElement(body, 'site', name=side + '_tcp', pos='.135 0 0', size='.004', rgba='1 .2 .2 .6', group='4')
            # Handgelenkkamera, blickt entlang der Finger (+x der Hand)
            E.SubElement(body, 'camera', name=side + '_wrist_cam', pos='.03 0 .08', fovy='75',
                         xyaxes=fmt([0, -1, 0, np.sin(.35), 0, np.cos(.35)]))
        if name == 'torso_link':
            # D435-Kopfkamera gemäss URDF (d435_joint), Neigung 0,83 rad nach unten
            p = .8307767239493009
            E.SubElement(body, 'camera', name='head_cam', pos='.0576235 .01753 .42987', fovy='58',
                         xyaxes=fmt([0, -1, 0, np.sin(p), 0, np.cos(p)]))
        for j in children.get(name, []):
            recurse(body, j.find('child').get('link'), j)

    robot = recurse(world, 'pelvis')

    def static_box(name, pos, half, material):
        E.SubElement(world, 'geom', name=name, type='box', pos=fmt(pos), size=fmt(half), material=material,
                     contype='2', conaffinity='5')

    tx, ty = TABLE_CENTER
    static_box('table_top', [tx, ty, TABLE_TOP - .025], [TABLE_SIZE[0] / 2, TABLE_SIZE[1] / 2, .025], 'table')
    for sx in (-1, 1):
        for sy in (-1, 1):
            static_box(f'table_leg_{sx}_{sy}', [tx + sx * (TABLE_SIZE[0] / 2 - .05), ty + sy * (TABLE_SIZE[1] / 2 - .05),
                                                (TABLE_TOP - .05) / 2], [.025, .025, (TABLE_TOP - .05) / 2], 'table')

    # Offene Box, fest auf dem Tisch (statisch -> Position bei jedem Reset identisch)
    box = E.SubElement(world, 'body', name='box', pos=fmt([*BOX_POS, TABLE_TOP]))
    bx, by = BOX_INNER
    w, h = BOX_WALL, BOX_HEIGHT
    E.SubElement(box, 'geom', name='box_floor', type='box', pos=fmt([0, 0, w / 4]), size=fmt([bx / 2 + w, by / 2 + w, w / 4]),
                 material='box', contype='2', conaffinity='5')
    for axis in range(2):
        for sign in (-1, 1):
            p = [0., 0., h / 2]
            p[axis] = sign * ((BOX_INNER[axis] + w) / 2)
            half = [bx / 2 + w, by / 2 + w, h / 2]
            half[axis] = w / 2
            E.SubElement(box, 'geom', name=f'box_wall_{axis}_{"p" if sign > 0 else "n"}', type='box', pos=fmt(p),
                         size=fmt(half), material='box', contype='2', conaffinity='5')
    E.SubElement(box, 'site', name='box_center', pos=fmt([0, 0, w / 2]), size=fmt([bx / 2, by / 2, .001]),
                 type='box', rgba='0 1 0 .15', group='4')

    # Reagent Kit: frei beweglich, Startpose wird bei jedem Reset zufällig gesetzt
    kit = E.SubElement(world, 'body', name='kit', pos=fmt([.33, .08, TABLE_TOP + KIT_HALF[2]]))
    E.SubElement(kit, 'freejoint', name='kit_free')
    hx, hy, hz = (2 * np.array(KIT_HALF)) ** 2
    E.SubElement(kit, 'inertial', pos='0 0 0', mass=str(KIT_MASS),
                 diaginertia=fmt(KIT_MASS / 12 * np.array([hy + hz, hx + hz, hx + hy])))
    for k, part in enumerate(parts):
        E.SubElement(asset, 'mesh', name=f'kit_part{k}', file='kit/' + part)
        mat = 'kit_body' if k == 0 else 'kit_cap'
        E.SubElement(kit, 'geom', name=f'kit_visual_{k}', type='mesh', mesh=f'kit_part{k}', material=mat,
                     contype='0', conaffinity='0', group='1')
    # Kollision: konvexe Hülle des Hauptkörpers (MuJoCo bildet sie automatisch)
    E.SubElement(kit, 'geom', name='kit_collision', type='mesh', mesh='kit_part0', group='3', rgba='1 .5 0 .3',
                 contype='4', conaffinity='3', friction='1.1 .005 .0001')

    E.SubElement(world, 'camera', name='overview', pos='1.55 -1.05 1.55', xyaxes='.56 .83 0 -.42 .28 .86', fovy='50')
    E.SubElement(world, 'camera', name='front', pos='1.6 0 1.25', xyaxes='0 1 0 -.38 0 .92', fovy='45')

    E.indent(root)
    path = HERE / 'scene.xml'
    E.ElementTree(root).write(path, encoding='unicode')
    return path

if __name__ == '__main__':
    print(build())
