"""Export Isaac visuals once, then read live PhysX body poses for WebXR."""
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Gf
from isaacsim.core.prims import RigidPrim

class QuestSceneGeometry:
    def __init__(self, stage, roots=None):
        roots=tuple(roots or ("/World/G1/","/World/Table/","/World/TargetBin/","/World/Object/"))
        cache=UsdGeom.XformCache()
        meshes=[]
        bodies=set()
        for prim in Usd.PrimRange(stage.GetPrimAtPath('/World'), Usd.TraverseInstanceProxies()):
            path=str(prim.GetPath())
            if not path.startswith(roots):
                continue
            if '/collisions/' in path or not (prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube)):
                continue
            imageable=UsdGeom.Imageable(prim)
            if imageable.ComputeVisibility()==UsdGeom.Tokens.invisible or imageable.ComputePurpose() in (UsdGeom.Tokens.guide,UsdGeom.Tokens.proxy):
                continue
            parent=prim
            while parent and not parent.IsPseudoRoot() and not parent.HasAPI(UsdPhysics.RigidBodyAPI):
                parent=parent.GetParent()
            body=str(parent.GetPath()) if parent and parent.HasAPI(UsdPhysics.RigidBodyAPI) else None
            transform=cache.GetLocalToWorldTransform(prim)
            if body:
                transform=transform*cache.GetLocalToWorldTransform(parent).GetInverse()
                bodies.add(body)
            color=[.68,.74,.74]
            display=UsdGeom.Gprim(prim).GetDisplayColorAttr().Get()
            if display: color=list(display[0])
            # CAD/FixedCuboid materials are not always authored as displayColor.
            # Explicit semantic palette matches the Isaac scene and preserves contrast.
            if path.startswith('/World/Object/'): color=[1.0,.22,.025]
            elif path.startswith('/World/TargetBin/'): color=[.12,.42,.65]
            elif path.startswith('/World/Table/'): color=[.16,.22,.28]
            if path.startswith('/World/G1/'):
                color=[.12,.18,.20] if any(s in path for s in ('head_link','hand_base_link','wrist_','ankle_roll')) else [.67,.73,.73]
            if prim.IsA(UsdGeom.Cube):
                size=float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2
                points=np.array([[x,y,z] for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]])*size
                indices=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,0,4,7,0,7,3,1,2,6,1,6,5]
            else:
                mesh=UsdGeom.Mesh(prim)
                points=mesh.GetPointsAttr().Get()
                counts=mesh.GetFaceVertexCountsAttr().Get()
                vertices=mesh.GetFaceVertexIndicesAttr().Get()
                indices=[]
                offset=0
                for count in counts:
                    for j in range(1,count-1): indices.extend((int(vertices[offset]),int(vertices[offset+j]),int(vertices[offset+j+1])))
                    offset+=count
                if mesh.GetOrientationAttr().Get()==UsdGeom.Tokens.leftHanded:
                    indices=np.array(indices).reshape(-1,3)[:,::-1].flatten().tolist()
            transformed=[list(transform.Transform(Gf.Vec3d(*[float(x) for x in v]))) for v in points]
            meshes.append({'name':path,'body':body,'points':np.round(transformed,7).flatten().tolist(),'indices':indices,'color':color})
        self.paths=sorted(bodies)
        self.view=RigidPrim(prim_paths_expr=self.paths,name='quest_visual_bodies',reset_xform_properties=False)
        self.view.initialize()
        self.document={'version':2,'units':'metres','up':'Z','meshes':meshes,'bodies':self.paths,'eye':[-.44,0,1.34]}
        print(f'QUEST_GEOMETRY_READY meshes={len(meshes)} bodies={len(self.paths)} triangles={sum(len(m["indices"])//3 for m in meshes)}',flush=True)

    def poses(self):
        positions,orientations=self.view.get_world_poses()
        return {path:[*p.tolist(),*q.tolist()] for path,p,q in zip(self.view.prim_paths,positions,orientations)}

    def reset(self):
        self.view.initialize()
