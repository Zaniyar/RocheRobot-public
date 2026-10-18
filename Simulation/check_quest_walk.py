"""Isolated dynamics test: stand, walk, stop. Does not connect to Quest."""
import argparse,json,sys
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);parser.add_argument('--visible',action='store_true');parser.add_argument('--speed',type=float,default=.2);parser.add_argument('--toggle-check',action='store_true');args,unknown=parser.parse_known_args()
from isaacsim import SimulationApp
app=SimulationApp({'headless':not args.visible,'multi_gpu':False,'active_gpu':0,'physics_gpu':0,'fast_shutdown':True})
try:
    import numpy as np
    from isaacsim.core.api import World
    from isaacsim.core.api.robots import Robot
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.types import ArticulationAction
    from isaacsim.core.utils.viewports import set_camera_view
    from pxr import Usd,UsdPhysics,PhysxSchema,Gf
    from quest_walk_policy import QuestWalkPolicy,setup_gains,default_q
    world=World(stage_units_in_meters=1.,physics_dt=.005,rendering_dt=.02)
    world.scene.add_default_ground_plane()
    root=add_reference_to_stage('D:/RobotRuntime/unitree_sim_isaaclab/assets/robots/g1-29dof_wholebody_dex1/g1_29dof_with_dex1_rev_1_0.usd','/World/G1')
    for prim in Usd.PrimRange(root):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            props=PhysxSchema.PhysxRigidBodyAPI.Apply(prim);props.CreateDisableGravityAttr(False);props.CreateLinearDampingAttr(0.);props.CreateAngularDampingAttr(0.)
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            props=PhysxSchema.PhysxArticulationAPI.Apply(prim);props.CreateEnabledSelfCollisionsAttr(False);props.CreateSolverPositionIterationCountAttr(4);props.CreateSolverVelocityIterationCountAttr(1)
    robot=world.scene.add(Robot(prim_path='/World/G1',name='walker',position=np.array([0.,0.,.8])))
    if args.toggle_check:
        anchor=UsdPhysics.FixedJoint.Define(root.GetStage(),'/World/QuestAnchor')
        anchor.CreateBody1Rel().SetTargets(['/World/G1/pelvis'])
        anchor.CreateLocalPos0Attr(Gf.Vec3f(0,0,.8))
        anchor.CreateExcludeFromArticulationAttr(True)
    world.reset();q=default_q(robot.dof_names);robot.set_joint_positions(q);robot.set_joint_velocities(np.zeros_like(q));robot.set_world_pose(position=np.array([0.,0.,.8]))
    setup_gains(robot);policy=QuestWalkPolicy(robot);controller=robot.get_articulation_controller()
    set_camera_view(eye=np.array([3.,-3.,2.]),target=np.array([0.,0.,.8]))
    report={'run_id':args.run_id,'source':'Unitree Wholebody Dex1 policy','dt':.005,'samples':[]};heights=[];phase_positions={}
    for step in range(2400):
        t=step*.005;phase='stand' if t<3 else 'walk' if t<8 else 'stop'
        if args.toggle_check and step==600: anchor.CreateJointEnabledAttr(False);policy.reset()
        if args.toggle_check and step==2200:
            p,r=robot.get_world_pose();anchor.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in p]));anchor.CreateLocalRot0Attr(Gf.Quatf(float(r[0]),Gf.Vec3f(*[float(v) for v in r[1:]])));anchor.CreateJointEnabledAttr(True)
        if phase not in phase_positions: phase_positions[phase]=robot.get_world_pose()[0].tolist()
        if step%4==0: q=policy.action(q,[args.speed if phase=='walk' else 0.,0.,0.])
        controller.apply_action(ArticulationAction(joint_positions=q));world.step(render=args.visible and step%4==0)
        p,orientation=robot.get_world_pose();heights.append(float(p[2]))
        if step%100==0:
            sample={'t':t,'phase':phase,'position':p.tolist(),'quaternion':orientation.tolist()};report['samples'].append(sample);print('WALK_SAMPLE '+json.dumps(sample),flush=True)
        if p[2]<.45 or not np.isfinite(p).all(): report['fell']=True;break
    report.update(min_height=min(heights),end_position=robot.get_world_pose()[0].tolist(),phase_positions=phase_positions)
    if 'stop' in phase_positions:
        report['walk_dx']=phase_positions['stop'][0]-phase_positions['walk'][0]
        report['stop_drift']=float(np.linalg.norm(np.array(report['end_position'][:2])-phase_positions['stop'][:2]))
    report['pass']=not report.get('fell',False) and report.get('walk_dx',0)>.35 and report.get('stop_drift',999)<.35
    folder=Path('D:/RobotRuntime/Logs')/args.run_id;folder.mkdir(exist_ok=False);(folder/'report.json').write_text(json.dumps(report,indent=2));print('WALK_REPORT '+json.dumps(report),flush=True)
finally: app.close()
