"""Exportiert Szene, echte MuJoCo-Läufe und Messwerte für das Dashboard Projectboard/method-lab.

Der Browser rechnet keine Physik: er spielt die hier aufgezeichneten Körperposen ab.
"""
import json, sys
from pathlib import Path
import numpy as np
import measure as M
import mujoco as mj

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'Projectboard/method-lab/public/data'
OUT.mkdir(parents=True, exist_ok=True)
FPS = 25

# id, Titel, Beschreibung, Seed, Parameter
RUNS = json.load(open(HERE / 'runs.json', encoding='utf8'))

def export_scene(lab):
    m = lab.env.model
    geoms, blobs, offset, cache = [], [], 0, {}
    for i in range(m.ngeom):
        body = m.body(m.geom_bodyid[i]).name
        name = m.geom(i).name
        if 'collision' in name or name == 'floor':
            continue
        g = dict(name=name, body=int(m.geom_bodyid[i]) - 1, pos=m.geom_pos[i].tolist(), quat=m.geom_quat[i].tolist(),
                 type=int(m.geom_type[i]), size=m.geom_size[i].tolist(), rgba=(m.mat_rgba[m.geom_matid[i]] if m.geom_matid[i] >= 0 else m.geom_rgba[i]).tolist())
        if m.geom_type[i] == mj.mjtGeom.mjGEOM_MESH:
            mid = int(m.geom_dataid[i])
            if mid not in cache:
                va, fa = m.mesh_vertadr[mid], m.mesh_faceadr[mid]
                na = m.mesh_normaladr[mid]
                faces = m.mesh_face[fa:fa + m.mesh_facenum[mid]]
                fnorm = m.mesh_facenormal[fa:fa + m.mesh_facenum[mid]]
                pos = m.mesh_vert[va:va + m.mesh_vertnum[mid]][faces].astype(np.float32).reshape(-1, 3)
                nor = m.mesh_normal[na:na + m.mesh_normalnum[mid]][fnorm].astype(np.float32).reshape(-1, 3)
                blob = np.hstack([pos, nor]).astype(np.float32).tobytes()
                cache[mid] = dict(offset=offset, count=len(pos))
                blobs.append(blob)
                offset += len(blob)
            g['mesh'] = cache[mid]
        geoms.append(g)
    (OUT / 'meshes.bin').write_bytes(b''.join(blobs))
    return dict(bodies=[m.body(i).name for i in range(1, m.nbody)], geoms=geoms)

def main():
    lab = M.Lab()
    scene = export_scene(lab)
    runs = []
    for r in RUNS:
        p = dict(M.NOMINAL, **r['params'])
        res, trace = lab.episode(r['seed'], p, keep_trace=True)
        step = max(1, round(1 / FPS / lab.env.control_dt))
        tr = trace[::step]
        arr = np.stack([np.hstack([f['xpos'], f['xquat']]) for f in tr]).astype(np.float32)
        (OUT / f"run_{r['id']}.bin").write_bytes(arr.tobytes())
        keys = ('tilt', 'slosh', 'acc', 'height', 'speed', 'track', 'grip')
        series = {k: [round(float(f[k]), 4) for f in tr] for k in keys}
        runs.append(dict(id=r['id'], title=r['title'], note=r['note'], group=r['group'], seed=r['seed'], params=r['params'],
                         frames=len(tr), bodies=arr.shape[1], dt=step * lab.env.control_dt, series=series,
                         result={k: v for k, v in res.items() if k != 'kit_start'}, kit_start=res['kit_start']))
        print(r['id'], {k: res[k] for k in ('placed', 'gentle', 'tilt_max', 'slosh_max', 'acc_max', 'duration', 'plan_fail')})
    # Ohne Messreihe zeigt das Dashboard nur Szene und Läufe; die Tafeln melden dann "läuft noch".
    path = HERE / (sys.argv[1] if len(sys.argv) > 1 else 'results.json')
    results = None
    if path.exists():
        results = json.load(open(path, encoding='utf8'))
        episodes = results.pop('episodes')
        results['workspace'] = [dict(x=e['kit_start'][0], y=e['kit_start'][1], yaw=e['kit_start'][2], ok=not e['plan_fail'], placed=e['placed'])
                                for e in episodes if e['sweep'] == 'compare' and e['value'] == 'gentle']
    profiles = json.load(open(HERE / 'dof_profiles.json', encoding='utf8'))
    json.dump(dict(scene=scene, runs=runs, results=results, profiles=profiles), open(OUT / 'data.json', 'w', encoding='utf8'))
    print('MB', sum(f.stat().st_size for f in OUT.iterdir()) / 1e6)

if __name__ == '__main__':
    main()
