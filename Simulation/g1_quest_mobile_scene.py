"""Quest spatial scene with a switchable anchor and Unitree walking policy.

The original fixed scene remains in g1_quest_scene.py. No native ONNX imports.
"""
import argparse
import os
import json
import time
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--headless',action='store_true')
parser.add_argument('--spatial',action='store_true')
parser.add_argument('--frames',type=int,default=0)
parser.add_argument('--run-id',default='manual')
parser.add_argument('--self-test',action='store_true',help='Isolated scripted mode test; does not connect to the live Quest bridge')
parser.add_argument('--initial-arm-pose',help='Diagnostic only: replay initial.measured_q from a direction-check report')
args,unknown=parser.parse_known_args()
from isaacsim import SimulationApp
app=SimulationApp({'headless':args.headless,'width':1280,'height':800,'multi_gpu':False,'active_gpu':0,'physics_gpu':0,'fast_shutdown':True})
try:
    import numpy as np
    import omni.usd
    import omni.ui as ui
    from pxr import Usd,UsdGeom,UsdPhysics,UsdLux,UsdShade,Sdf,PhysxSchema,Gf
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import FixedCuboid
    from isaacsim.core.api.robots import Robot
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.core.utils.types import ArticulationAction

    runtime=Path(os.environ.get('ROBOT_RUNTIME', r'D:\RobotRuntime'))
    robot_usd=runtime/'unitree_sim_isaaclab/assets/robots/g1-29dof_wholebody_dex1/g1_29dof_with_dex1_rev_1_0.usd'
    cad_usd=runtime/'ObjectAssets/example_object.usd'
    for file in (robot_usd,cad_usd):
        if not file.is_file(): raise FileNotFoundError(file)
    world=World(stage_units_in_meters=1.0,physics_dt=.005,rendering_dt=.02)
    stage=omni.usd.get_context().get_stage()
    world.scene.add_default_ground_plane(z_position=0.0)
    light=UsdLux.DomeLight.Define(stage,'/World/Light')
    light.CreateIntensityAttr(1000.0)
    light.CreateColorAttr(Gf.Vec3f(0.95,0.97,1.0))
    table_color=np.array([0.16,0.22,0.28])
    world.scene.add(FixedCuboid(prim_path='/World/Table/Top',name='table_top',position=np.array([0.12,0.0,0.725]),scale=np.array([1.05,0.72,0.05]),color=table_color))
    for i,(x,y) in enumerate([(-0.32,-0.29),(-0.32,0.29),(0.56,-0.29),(0.56,0.29)]):
        world.scene.add(FixedCuboid(prim_path=f'/World/Table/Leg{i}',name=f'table_leg{i}',position=np.array([x,y,0.35]),scale=np.array([0.045,0.045,0.7]),color=np.array([0.3,0.34,0.38])))
    # Offener Behälter aus fünf separaten Kollisionsquadern, Innenraum frei.
    bx,by=-0.23,-0.18
    blue=np.array([0.12,0.42,0.65])
    parts=[('Bottom',(bx,by,0.757),(0.25,0.23,0.014)),
           ('Left',(bx-0.12,by,0.818),(0.01,0.23,0.12)),
           ('Right',(bx+0.12,by,0.818),(0.01,0.23,0.12)),
           ('Front',(bx,by-0.11,0.818),(0.23,0.01,0.12)),
           ('Back',(bx,by+0.11,0.818),(0.23,0.01,0.12))]
    for name,pos,scale in parts:
        world.scene.add(FixedCuboid(prim_path=f'/World/TargetBin/{name}',name=f'bin_{name}',position=np.array(pos),scale=np.array(scale),color=blue))
    g1_prim=add_reference_to_stage(str(robot_usd),'/World/G1')
    base_position=np.array([-1.8,-1.,.8] if args.self_test else [-.63,0.,.8])
    robot=world.scene.add(Robot(prim_path='/World/G1',name='g1_dex1',position=base_position))
    anchor=UsdPhysics.FixedJoint.Define(stage,'/World/QuestAnchor')
    anchor.CreateBody1Rel().SetTargets(['/World/G1/pelvis'])
    anchor.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in base_position]))
    anchor.CreateExcludeFromArticulationAttr(True)
    for prim in Usd.PrimRange(g1_prim):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            props=PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
            props.CreateDisableGravityAttr(False);props.CreateLinearDampingAttr(0.);props.CreateAngularDampingAttr(0.)
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            props=PhysxSchema.PhysxArticulationAPI.Apply(prim)
            props.CreateEnabledSelfCollisionsAttr(False);props.CreateSolverPositionIterationCountAttr(4);props.CreateSolverVelocityIterationCountAttr(1)
    # Referenzdatei ist laut Konverter in Millimetern: explizite Skalierung nach Metern.
    kit_root=UsdGeom.Xform.Define(stage,'/World/Object')
    kit_root.AddTranslateOp().Set(Gf.Vec3d(-0.30,0.15,0.753))
    kit_visual=UsdGeom.Xform.Define(stage,'/World/Object/CAD')
    kit_visual.GetPrim().GetReferences().AddReference(str(cad_usd))
    kit_visual.AddScaleOp().Set(Gf.Vec3f(0.001,0.001,0.001))
    UsdPhysics.RigidBodyAPI.Apply(kit_root.GetPrim())
    UsdPhysics.MassAPI.Apply(kit_root.GetPrim()).CreateMassAttr(0.10) # Schätzung, keine Roche-Messung.
    mesh_paths=[]
    kit_color=Gf.Vec3f(1.0,0.22,0.025)
    kit_material=UsdShade.Material.Define(stage,'/World/Looks/QuestKitOrange')
    kit_shader=UsdShade.Shader.Define(stage,'/World/Looks/QuestKitOrange/Shader')
    kit_shader.CreateIdAttr('UsdPreviewSurface')
    kit_shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(kit_color)
    kit_shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.65)
    kit_material.CreateSurfaceOutput().ConnectToSource(kit_shader.ConnectableAPI(),'surface')
    for prim in Usd.PrimRange(kit_visual.GetPrim()):
        if prim.IsA(UsdGeom.Mesh):
            UsdGeom.Gprim(prim).CreateDisplayColorAttr([kit_color])
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(kit_material,UsdShade.Tokens.strongerThanDescendants)
            mesh_paths.append(str(prim.GetPath()))
            UsdPhysics.CollisionAPI.Apply(prim)
            UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('convexHull')
    kit=world.scene.add(SingleRigidPrim(prim_path='/World/Object',name='roche_kit'))
    def overview():
        set_camera_view(eye=np.array([2.05,-2.35,1.8]),target=np.array([-0.2,0.0,0.87]))
    def closeup():
        set_camera_view(eye=np.array([0.24,0.52,1.01]),target=np.array([-0.11,0.15,0.79]))
    overview()
    world.reset()
    # Bei einer festen PhysX-Artikulation die Basis nach Initialisierung setzen.
    # Die USD-Xform-Position allein wird beim Reset vom PhysX-Startzustand ersetzt.
    robot.set_world_pose(position=base_position)
    robot.set_default_state(position=base_position)
    from quest_walk_policy import QuestWalkPolicy,setup_gains,default_q
    from isaacsim.core.utils.rotations import quat_to_rot_matrix
    q=default_q(robot.dof_names)
    setup_gains(robot)
    policy=QuestWalkPolicy(robot)
    robot.set_joint_positions(q)
    robot.set_joint_velocities(np.zeros_like(q))
    controller=robot.get_articulation_controller()
    if not args.self_test:
        from quest_spatial_link import QuestSpatialLink
        quest=QuestSpatialLink(robot,stage,mobile=True)
        # Creating a new PhysX view can refresh articulation transforms.
        robot.set_world_pose(position=base_position)
        robot.set_joint_positions(q)
        robot.set_joint_velocities(np.zeros_like(q))
        setup_gains(robot)
    initial_q=q.copy()
    walking_upper=[i for i,n in enumerate(robot.dof_names) if 'waist' in n or n in [robot.dof_names[j] for j in policy.obs_ids[12:]]]
    walking_proximal=[i for i in walking_upper if 'wrist' not in robot.dof_names[i]]
    waist_ids=[i for i,n in enumerate(robot.dof_names) if 'waist' in n]
    if args.initial_arm_pose:
        replay=np.asarray(json.loads(Path(args.initial_arm_pose).read_text())['initial']['measured_q'],dtype=float)
        if replay.shape!=(14,) or not np.isfinite(replay).all(): raise ValueError('Invalid diagnostic arm pose')
        q[policy.obs_ids[12:]]=replay
        robot.set_joint_positions(q)
    mobility='fixed'
    motion_note='Fixiert · X links: Laufen'
    mode_events=[]
    force_fixed=False
    def set_mobility(value):
        global mobility,motion_note
        if value==mobility: return
        if value=='walk':
            policy.reset()
            # Check inference before releasing the physical anchor.
            policy.action(q,[0.,0.,0.])
            anchor.CreateJointEnabledAttr(False)
            motion_note='Laufen · linker Stick: bewegen · rechter Stick: drehen'
        else:
            p,r=robot.get_world_pose()
            anchor.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in p]))
            anchor.CreateLocalRot0Attr(Gf.Quatf(float(r[0]),Gf.Vec3f(*[float(v) for v in r[1:]])))
            anchor.CreateJointEnabledAttr(True)
            q[:]=robot.get_joint_positions()
            policy.reset()
            motion_note='Fixiert · Grip: Arme · X links: Laufen'
        mobility=value
        mode_events.append({'mode':value,'position':robot.get_world_pose()[0].tolist()})
        print('QUEST_MODE '+json.dumps(mode_events[-1]),flush=True)
    pending={'reset':False}
    def request_reset():
        pending['reset']=True
    def reset():
        global mobility,motion_note,force_fixed
        anchor.CreateJointEnabledAttr(True)
        anchor.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in base_position]))
        anchor.CreateLocalRot0Attr(Gf.Quatf(1.,Gf.Vec3f(0.,0.,0.)))
        world.reset()
        q[:]=initial_q
        if not args.self_test: quest.reset()
        setup_gains(robot);policy.reset()
        robot.set_world_pose(position=base_position,orientation=np.array([1.,0.,0.,0.]))
        robot.set_joint_positions(q)
        robot.set_joint_velocities(np.zeros_like(q))
        robot.set_linear_velocity(np.zeros(3));robot.set_angular_velocity(np.zeros(3))
        mobility='fixed';motion_note='Startzustand · Fixiert'
        force_fixed=True
        pending['reset']=False
    panel=None
    if not args.headless:
        panel=ui.Window('Quest 3 | G1 Teleoperation',width=370,height=210)
        panel.position_x=1030
        panel.position_y=120
        with panel.frame:
            with ui.VStack(spacing=8):
                ui.Label('G1 / Dex1 · Roche-Kit · Zielbehälter',height=24)
                ui.Label('X links: Fixiert/Laufen. Sticks: gehen/drehen. Grip: Arme in beiden Modi. B: Reset.',word_wrap=True,height=48)
                ui.Button('Gesamte Szene ansehen',clicked_fn=overview,height=28)
                ui.Button('Roche-Kit aus der Nähe',clicked_fn=closeup,height=28)
                ui.Button('Startzustand wiederherstellen',clicked_fn=request_reset,height=28)
    # Kontaktprüfung: Objekt soll nach dem Fallen auf der Tischplatte ruhen.
    for step in range(400):
        controller.apply_action(ArticulationAction(joint_positions=q))
        world.step(render=False)
        if step%4==0: world.render()
        if pending['reset']: reset()
    bbox=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_]).ComputeWorldBound(kit_root.GetPrim()).ComputeAlignedRange()
    pos=kit.get_world_pose()[0]
    robot_base_position=robot.get_world_pose()[0]
    robot_pose_ok=bool(np.linalg.norm(robot_base_position-base_position) < 0.03)
    state={'run_id':args.run_id,'robot_asset':str(robot_usd),'robot_dof_count':robot.num_dof,'dof_names':list(robot.dof_names),
           'cad_asset':str(cad_usd),'cad_mesh_count':len(mesh_paths),'cad_scale':0.001,
           'kit_extent_m':list(bbox.GetSize()),'kit_position_m':pos.tolist(),
           'kit_mass_kg_assumed':0.1,'kit_stable_on_table':bool(0.74 < pos[2] < 0.79),
           'robot_base_position_m':robot_base_position.tolist(),'robot_base_pose_pass':robot_pose_ok,
           'autonomous_manipulation':False,'isaaclab_task_executed':False}
    out_dir=runtime/'QuestScenes'/args.run_id
    out_dir.mkdir(parents=True,exist_ok=True)
    # Speichere den wiederherstellbaren Startzustand mit lokalen Assetreferenzen.
    scene_path=out_dir/'G1_RocheKit_scene.usd'
    stage.GetRootLayer().Export(str(scene_path))
    (out_dir/'scene-validation.json').write_text(json.dumps(state,indent=2),encoding='utf8')
    print('ROCHE_SCENE_READY '+json.dumps(state),flush=True)
    if not state['kit_stable_on_table'] or not robot_pose_ok:
        raise RuntimeError('Kit-Tischkontakt oder Roboterverankerung fehlgeschlagen.')
    frames=0;start_time=time.monotonic();samples=[];failure=None
    applied_command=[0.,0.,0.]
    limit=2400 if args.self_test else args.frames
    while app.is_running() and (not limit or frames < limit):
        if pending['reset']: reset()
        if world.is_playing():
            if frames%4==0:
                if args.self_test:
                    requested='fixed' if frames<400 or frames>=2000 else 'walk'
                    command=[.5 if 600<=frames<1600 else 0.,0.,0.]
                else:
                    quest.telemetry={'mobility_supported':True,'mobility':mobility,'motion_note':motion_note,'force_fixed':force_fixed,'applied_walk_command':applied_command}
                    quest.update(q,request_reset)
                    requested,command=quest.mobility_command()
                    if requested=='fixed': force_fixed=False
                    if force_fixed: requested='fixed'
                try:
                    if requested=='walk' and mobility=='fixed':
                        # Arbitrary teleoperated arm poses can drive this policy backwards
                        # even for positive velocity commands. Prepare its neutral pose
                        # while the anchor is still engaged; never teleport the joints.
                        q[walking_upper]+=np.clip(initial_q[walking_upper]-q[walking_upper],-.015,.015)
                        target_error=np.max(np.abs(q[walking_upper]-initial_q[walking_upper]))
                        # Wrist contact/gravity near the table can prevent exact target
                        # tracking. Gate on the proximal arm/waist pose, with tolerance
                        # for the measured load deflection; do not wait forever for wrists.
                        actual_error=np.max(np.abs(robot.get_joint_positions()[walking_proximal]-initial_q[walking_proximal]))
                        if target_error>.01 or actual_error>.30:
                            requested='fixed'
                            motion_note='Laufhaltung vorbereiten · Arme werden angelegt'
                    set_mobility(requested)
                    if mobility=='walk':
                        # Wholebody policy controls legs; retain the rate-limited
                        # teleoperation arm/gripper targets in walking mode too.
                        q[waist_ids]=initial_q[waist_ids]
                        p,r=robot.get_world_pose()
                        velocity=quat_to_rot_matrix(r)@np.array([command[0],command[1],0.])
                        future=p[:2]+velocity[:2]*.25
                        # Conservative torso clearance, not a collision-free planner.
                        if -.625<future[0]<.865 and -.58<future[1]<.58:
                            command=[0.,0.,command[2]]
                            motion_note='Tisch im Weg · zuerst rückwärts oder seitlich gehen'
                        else: motion_note='Laufen + Arme · Sticks: gehen · Grip rechts: Arme'
                        applied_command=list(command)
                        q[:]=policy.action(q,command)
                    else: applied_command=[0.,0.,0.]
                except Exception as e:
                    set_mobility('fixed');motion_note='Policy-Fehler: '+str(e);failure=str(e);force_fixed=True
                    if args.self_test: raise
            controller.apply_action(ArticulationAction(joint_positions=q))
        # step(render=True) advances rendering_dt and would add extra physics
        # steps here. Render separately to retain the policy's exact 200/50 Hz.
        world.step(render=False)
        if frames%4==0: world.render()
        if frames%100==0:
            p,r=robot.get_world_pose()
            sample={'t':frames*.005,'mode':mobility,'position':p.tolist()}
            if args.self_test: samples.append(sample)
            if p[2]<.45 or not np.isfinite(p).all():
                failure='Roboter gestürzt';reset();motion_note='Sturz: auf Startposition zurückgesetzt'
                if args.self_test: break
        frames+=1
        if not args.self_test:
            delay=frames*.005-(time.monotonic()-start_time)
            if delay>0: time.sleep(min(delay,.01))
            elif delay<-.2: start_time=time.monotonic()-frames*.005
    if args.self_test:
        distance=mode_events[-1]['position'][0]-mode_events[0]['position'][0] if len(mode_events)==2 else 0.
        stop_start=next((s['position'] for s in samples if s['t']==8.),None)
        stop_end=next((s['position'] for s in samples if s['t']==10.),None)
        stop_drift=float(np.linalg.norm(np.array(stop_start[:2])-stop_end[:2])) if stop_start and stop_end else 999.
        fixed_drift=float(np.linalg.norm(robot.get_world_pose()[0]-mode_events[-1]['position'])) if mode_events else 999.
        report={'pass':failure is None and distance>.35 and len(mode_events)==2 and stop_drift<.35 and fixed_drift<.02,'events':mode_events,'distance_m':distance,'stop_drift_m':stop_drift,'fixed_drift_m':fixed_drift,'failure':failure,'samples':samples,'scene':state}
        (out_dir/'mobility-test.json').write_text(json.dumps(report,indent=2))
        print('QUEST_MOBILITY_TEST '+json.dumps(report),flush=True)
finally:
    if 'quest' in locals(): quest.close()
    app.close()

