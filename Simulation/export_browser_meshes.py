"""Export visible USD meshes in metres; retains separate CAD parts. Local only."""
import json
from pathlib import Path
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'fast_shutdown':False})
try:
    from pxr import Usd, UsdGeom, UsdShade, Gf
    out=Path(r'D:\RobotRuntime\ProjectboardModels')
    out.mkdir(parents=True,exist_ok=True)
    assets={
        'g1':Path(r'D:\RobotRuntime\unitree_sim_isaaclab\assets\robots\g1-29dof-dex1-base-fix-usd\g1_29dof_with_dex1_base_fix1.usd'),
        'kit':Path(r'D:\RobotRuntime\ObjectAssets\example_object.usd')}
    for name,path in assets.items():
        stage=Usd.Stage.Open(str(path))
        cache=UsdGeom.XformCache()
        unit=UsdGeom.GetStageMetersPerUnit(stage)
        meshes=[]
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Mesh): continue
            p=str(prim.GetPath())
            imageable=UsdGeom.Imageable(prim)
            if imageable.ComputeVisibility()==UsdGeom.Tokens.invisible or imageable.ComputePurpose()==UsdGeom.Tokens.guide: continue
            if 'collisions' in p.lower() or '/collision/' in p.lower(): continue
            mesh=UsdGeom.Mesh(prim)
            transform=cache.GetLocalToWorldTransform(prim)
            points=[list(transform.Transform(Gf.Vec3d(v))*unit) for v in mesh.GetPointsAttr().Get()]
            counts=mesh.GetFaceVertexCountsAttr().Get()
            indices=mesh.GetFaceVertexIndicesAttr().Get()
            triangles=[]
            cursor=0
            for count in counts:
                face=indices[cursor:cursor+count]
                for k in range(1,count-1): triangles.extend((face[0],face[k],face[k+1]))
                cursor+=count
            color=[0.55,0.59,0.60] if name=='g1' else [0.84,0.88,0.86]
            display=mesh.GetDisplayColorAttr().Get()
            if display: color=list(display[0])
            material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if material:
                shader,_name,_type=material.ComputeSurfaceSource()
                if shader:
                    value=shader.GetInput('diffuseColor').Get()
                    if value is not None: color=list(value)
            meshes.append({'name':prim.GetName(),'path':p,'points':points,'indices':triangles,'color':color})
        result={'name':name,'source':str(path),'source_meters_per_unit':unit,'up_axis':str(UsdGeom.GetStageUpAxis(stage)), 'meshes':meshes}
        (out/(name+'.json')).write_text(json.dumps(result),encoding='utf8')
        print('BROWSER_MESH_EXPORT',name,len(meshes),sum(len(m['indices'])//3 for m in meshes),flush=True)
finally:
    app.close()
