"""Wandelt ausgewählte NVIDIA-SimReady-Modelle (OpenUSD) in kleine GLB-Dateien für das Dashboard.

Läuft in einer eigenen Umgebung mit usd-core, trimesh, numpy und pillow:
    D:/RocheRuntime/AssetConvert/.venv/Scripts/python.exe tools/convert_simready.py

Quelle: huggingface.co/datasets/nvidia/simready-assets, CC BY 4.0. Die Originale liegen ausserhalb des
Repositories unter D:/RocheRuntime/SimReadyAssets. Ausgabe in Metern, z oben, Boden auf z = 0, xy zentriert.
"""
import json, sys
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade, Gf

SRC = Path('D:/RocheRuntime/SimReadyAssets')
OUT = Path(__file__).resolve().parents[1] / 'public/assets/nvidia'
TEX = 512
ASSETS = {
    'bottle_laboratory_b01': ('Laborflasche', 'table'),
    'container_vial_glass_a01': ('Glasfläschchen', 'table'),
    'medicine_b01': ('Medikamentenpackung', 'table'),
    'container_system_sterilising_a02': ('Sterilisationsbehälter', 'table'),
    'trolley_instrument_b01': ('Instrumentenwagen', 'floor'),
}

def texture_of(prim_material):
    """Sucht im Material die Albedo-Textur und eine konstante Grundfarbe."""
    tex, color = None, None
    for p in Usd.PrimRange(prim_material.GetPrim()):
        shader = UsdShade.Shader(p)
        if not shader:
            continue
        for i in shader.GetInputs():
            v = i.Get()
            n = i.GetBaseName().lower()
            if hasattr(v, 'resolvedPath') and v.resolvedPath:
                name = Path(v.resolvedPath).name.lower()
                if '_alb' in name or 'diffuse' in n or 'albedo' in n or 'basecolor' in n:
                    tex = tex or v.resolvedPath
            elif isinstance(v, Gf.Vec3f) and ('color' in n or 'albedo' in n or 'diffuse' in n) and 'emissive' not in n and color is None:
                color = list(v)
    return tex, color

def triangulate(counts, indices):
    tris, faces = [], []
    k = 0
    for f, c in enumerate(counts):
        for j in range(1, c - 1):
            tris.append((k, k + j, k + j + 1))
            faces.append(f)
        k += c
    return np.array(tris), np.array(faces)

def convert(name):
    root = next((SRC / name / 'simready_usd').glob('sm_*.usd'))
    stage = Usd.Stage.Open(str(root))
    mpu = UsdGeom.GetStageMetersPerUnit(stage)
    z_up = UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    cache = UsdGeom.XformCache()
    parts = []
    for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh) or UsdGeom.Imageable(prim).ComputeVisibility() == UsdGeom.Tokens.invisible:
            continue
        purpose = UsdGeom.Imageable(prim).ComputePurpose()
        if purpose not in (UsdGeom.Tokens.default_, UsdGeom.Tokens.render):
            continue
        mesh = UsdGeom.Mesh(prim)
        pts, counts, idx = mesh.GetPointsAttr().Get(), mesh.GetFaceVertexCountsAttr().Get(), mesh.GetFaceVertexIndicesAttr().Get()
        if not pts or not counts:
            continue
        pts = np.array(pts, float)
        idx = np.array(idx)
        M = np.array(cache.GetLocalToWorldTransform(prim), float)     # USD: Zeilenvektoren
        world = (np.c_[pts, np.ones(len(pts))] @ M)[:, :3] * mpu
        if not z_up:
            world = world[:, [0, 2, 1]] * [1, -1, 1]
        tri, _ = triangulate(counts, idx)
        corner = world[idx]                                            # je Ecke eigene Punkte: UV bleibt erhalten
        uv = None
        st = UsdGeom.PrimvarsAPI(prim).GetPrimvar('st')
        if st and st.HasValue():
            raw = np.array(st.ComputeFlattened(), float)
            if len(raw) == len(idx):
                uv = raw
            elif len(raw) == len(pts):
                uv = raw[idx]
        mat, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        tex, color = texture_of(mat) if mat else (None, None)
        parts.append(dict(v=corner, f=tri, uv=uv, tex=tex, color=color, name=prim.GetName()))
    if not parts:
        raise ValueError("keine Geometrie")
    allv = np.vstack([p['v'] for p in parts])
    lo, hi = allv.min(0), allv.max(0)
    shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    scene = trimesh.Scene()
    cache_img = {}
    for i, p in enumerate(parts):
        pbr = dict(metallicFactor=0., roughnessFactor=.55)
        if p['tex'] and p['uv'] is not None:
            if p['tex'] not in cache_img:
                img = Image.open(p['tex']).convert('RGB')
                img.thumbnail((TEX, TEX))
                cache_img[p['tex']] = img
            pbr['baseColorTexture'] = cache_img[p['tex']]
        else:
            c = p['color'] or [.8, .8, .8]
            pbr['baseColorFactor'] = [*c, 1.]
        visual = trimesh.visual.TextureVisuals(uv=p['uv'] if p['uv'] is not None else None, material=trimesh.visual.material.PBRMaterial(**pbr))
        m = trimesh.Trimesh(vertices=p['v'] + shift, faces=p['f'], visual=visual, process=False)
        scene.add_geometry(m, geom_name=f"{p['name']}_{i}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{name}.glb').write_bytes(scene.export(file_type='glb'))
    thumb = next((SRC / name / 'simready_usd/.thumbs').glob('*_thumbnail.png'), None)
    if thumb:
        im = Image.open(thumb).convert('RGB')
        im.thumbnail((128, 128))
        im.save(OUT / f'{name}.jpg', quality=85)
    size = hi - lo
    print(name, 'Teile', len(parts), 'Dreiecke', sum(len(p['f']) for p in parts), 'Masse', np.round(size, 3), 'kB', (OUT / f'{name}.glb').stat().st_size // 1024)
    return dict(id=name, name=ASSETS[name][0], place=ASSETS[name][1], size=[float(x) for x in size])

if __name__ == '__main__':
    out = []
    for n in ASSETS:
        try:
            out.append(convert(n))
        except Exception as e:
            print('FEHLER', n, repr(e), file=sys.stderr)
    json.dump(out, open(OUT / 'catalog.json', 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    (OUT / 'ATTRIBUTION.txt').write_text('3D-Modelle aus NVIDIA SimReady Assets, https://huggingface.co/datasets/nvidia/simready-assets\nLizenz: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/\nGeändert: von OpenUSD nach GLB gewandelt, zentriert, Texturen verkleinert.\n', encoding='utf8')
