"""Position-only kinematic reach check; not a collision/grasp guarantee."""
import os,sys,json
from pathlib import Path
import numpy as np
import pinocchio as pin
from scipy.optimize import least_squares
root='/mnt/d/RobotRuntime/xr_teleoperate';sys.path.insert(0,root);os.chdir(root+'/teleop')
from teleop.robot_control.robot_arm_ik import G1_29_ArmIK
ik=G1_29_ArmIK(Visualization=False);model=ik.reduced_robot.model;data=model.createData()
results=[]
for name,side,target in [('box_old','R_ee',[.93,-.18,.18]),('box_near','R_ee',[.40,-.18,.18]),('kit_old','L_ee',[.52,.15,.06]),('kit_near','L_ee',[.40,.15,.06])]:
    frame=model.getFrameId(side);offset=0 if side=='L_ee' else 7
    base=np.array([.12,0,0,.8,0,0,0]*2,dtype=float)
    def residual(q):
        allq=base.copy();allq[offset:offset+7]=q;pin.framesForwardKinematics(model,data,allq)
        return data.oMf[frame].translation-np.asarray(target)
    result=least_squares(residual,base[offset:offset+7],bounds=(model.lowerPositionLimit[offset:offset+7]+.001,model.upperPositionLimit[offset:offset+7]-.001),max_nfev=1000)
    results.append({'target':name,'position_m_in_pelvis':target,'residual_m':float(np.linalg.norm(result.fun)),'position_reachable_1cm':bool(np.linalg.norm(result.fun)<.01),'orientation_and_collision_checked':False})
report={'base_world_m':[-.63,0,.76],'reference':'Unitree G1_29 IK L_ee/R_ee; 5 cm wrist offset, not calibrated Dex1 grasp centre','results':results}
Path('/opt/robot/project/Simulation/quest-reach-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
