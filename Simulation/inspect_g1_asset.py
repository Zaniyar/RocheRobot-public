from isaacsim import SimulationApp
app=SimulationApp({'headless':True})
from pxr import Usd,UsdPhysics,UsdGeom
s=Usd.Stage.Open(r'D:\RobotRuntime\unitree_sim_isaaclab\assets\robots\g1-29dof-dex1-base-fix-usd\g1_29dof_with_dex1_base_fix1.usd')
print('DEFAULT',s.GetDefaultPrim().GetPath(),'metric',UsdGeom.GetStageMetersPerUnit(s))
for p in s.Traverse():
    if p.IsA(UsdPhysics.FixedJoint) or p.HasAPI(UsdPhysics.ArticulationRootAPI):
        print(p.GetPath(),p.GetTypeName())
        for a in p.GetAttributes():
            if any(x in a.GetName() for x in ('localPos','localRot','xformOp:','targetPosition','stiffness','damping')):
                print(' ATTR',a.GetName(),a.Get())
        for r in p.GetRelationships(): print(' REL',r.GetName(),r.GetTargets())
import sys
sys.stdout.flush()
app.close()
