"""Quest test scene derived from g1_roche_scene.py; manual control, no training."""
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
args,unknown=parser.parse_known_args()
from isaacsim import SimulationApp
app=SimulationApp({'headless':args.headless,'width':1280,'height':800,'multi_gpu':False,'active_gpu':0,'physics_gpu':0,'fast_shutdown':True})
try:
    import numpy as np
    import omni.usd
    import omni.ui as ui
    from pxr import Usd,UsdGeom,UsdPhysics,UsdLux,PhysxSchema,Gf
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import FixedCuboid
    from isaacsim.core.api.robots import Robot
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.core.utils.types import ArticulationAction

    runtime=Path(os.environ.get('ROBOT_RUNTIME', r'D:\RobotRuntime'))
    robot_usd=runtime/'unitree_sim_isaaclab/assets/robots/g1-29dof-dex1-base-fix-usd/g1_29dof_with_dex1_base_fix1.usd'
    cad_usd=runtime/'ObjectAssets/example_object.usd'
    for file in (robot_usd,cad_usd):
        if not file.is_file(): raise FileNotFoundError(file)
    world=World(stage_units_in_meters=1.0,physics_dt=1/60,rendering_dt=1/60)
    stage=omni.usd.get_context().get_stage()
    world.scene.add_default_ground_plane(z_position=0.0)
    light=UsdLux.DomeLight.Define(stage,'/World/Light')
    light.CreateIntensityAttr(1000.0)
    light.CreateColorAttr(Gf.Vec3f(0.95,0.97,1.0))
    table_color=np.array([0.72,0.76,0.79])
    world.scene.add(FixedCuboid(prim_path='/World/Table/Top',name='table_top',position=np.array([0.12,0.0,0.725]),scale=np.array([1.05,0.72,0.05]),color=table_color))
    for i,(x,y) in enumerate([(-0.32,-0.29),(-0.32,0.29),(0.56,-0.29),(0.56,0.29)]):
        world.scene.add(FixedCuboid(prim_path=f'/World/Table/Leg{i}',name=f'table_leg{i}',position=np.array([x,y,0.35]),scale=np.array([0.045,0.045,0.7]),color=np.array([0.3,0.34,0.38])))
    # Offener Behälter aus fünf separaten Kollisionsquadern, Innenraum frei.
    bx,by=0.30,-0.18
    blue=np.array([0.12,0.42,0.65])
    parts=[('Bottom',(bx,by,0.757),(0.25,0.23,0.014)),
           ('Left',(bx-0.12,by,0.818),(0.01,0.23,0.12)),
           ('Right',(bx+0.12,by,0.818),(0.01,0.23,0.12)),
           ('Front',(bx,by-0.11,0.818),(0.23,0.01,0.12)),
           ('Back',(bx,by+0.11,0.818),(0.23,0.01,0.12))]
    for name,pos,scale in parts:
        world.scene.add(FixedCuboid(prim_path=f'/World/TargetBin/{name}',name=f'bin_{name}',position=np.array(pos),scale=np.array(scale),color=blue))
    g1_prim=add_reference_to_stage(str(robot_usd),'/World/G1')
    robot=world.scene.add(Robot(prim_path='/World/G1',name='g1_dex1',position=np.array([-0.63,0.0,0.76])))
    # Die Weltseite des festen Gelenks muss dieselbe Position wie die Basis haben.
    root_joint=UsdPhysics.FixedJoint(stage.GetPrimAtPath('/World/G1/root_joint'))
    root_joint.GetLocalPos0Attr().Set(Gf.Vec3f(-0.63,0.0,0.76))
    for prim in Usd.PrimRange(g1_prim):
        if prim.IsA(UsdPhysics.RevoluteJoint):
            drive=UsdPhysics.DriveAPI.Apply(prim,'angular')
            drive.CreateStiffnessAttr(800.0)
            drive.CreateDampingAttr(80.0)
            drive.CreateMaxForceAttr(300.0)
    # Referenzdatei ist laut Konverter in Millimetern: explizite Skalierung nach Metern.
    kit_root=UsdGeom.Xform.Define(stage,'/World/Object')
    kit_root.AddTranslateOp().Set(Gf.Vec3d(-0.11,0.15,0.753))
    kit_visual=UsdGeom.Xform.Define(stage,'/World/Object/CAD')
    kit_visual.GetPrim().GetReferences().AddReference(str(cad_usd))
    kit_visual.AddScaleOp().Set(Gf.Vec3f(0.001,0.001,0.001))
    UsdPhysics.RigidBodyAPI.Apply(kit_root.GetPrim())
    UsdPhysics.MassAPI.Apply(kit_root.GetPrim()).CreateMassAttr(0.10) # Schätzung, keine Roche-Messung.
    mesh_paths=[]
    for prim in Usd.PrimRange(kit_visual.GetPrim()):
        if prim.IsA(UsdGeom.Mesh):
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
    base_position=np.array([-0.63,0.0,0.76])
    robot.set_world_pose(position=base_position)
    robot.set_default_state(position=base_position)
    q=np.zeros(robot.num_dof,dtype=np.float32)
    for index,name in enumerate(robot.dof_names):
        if 'hip_pitch' in name: q[index]=-0.05
        elif 'knee' in name: q[index]=0.20
        elif 'ankle_pitch' in name: q[index]=-0.15
        elif 'elbow' in name: q[index]=0.8
        elif 'shoulder_pitch' in name: q[index]=0.12
    robot.set_joint_positions(q)
    robot.set_joint_velocities(np.zeros_like(q))
    controller=robot.get_articulation_controller()
    if args.spatial:
        from quest_spatial_link import QuestSpatialLink
        quest=QuestSpatialLink(robot,stage)
        # Creating a new PhysX view can refresh articulation transforms.
        robot.set_world_pose(position=base_position)
        robot.set_joint_positions(q)
        robot.set_joint_velocities(np.zeros_like(q))
    else:
        from quest_isaac_link import QuestIsaacLink
        quest=QuestIsaacLink(robot)
    initial_q=q.copy()
    pending={'reset':False}
    def request_reset():
        pending['reset']=True
    def reset():
        world.reset()
        q[:]=initial_q
        if args.spatial: quest.reset()
        else: quest.camera.initialize()
        robot.set_world_pose(position=base_position)
        robot.set_joint_positions(q)
        robot.set_joint_velocities(np.zeros_like(q))
        pending['reset']=False
    panel=None
    if not args.headless:
        panel=ui.Window('Quest 3 | G1 Teleoperation',width=370,height=210)
        panel.position_x=1030
        panel.position_y=120
        with panel.frame:
            with ui.VStack(spacing=8):
                ui.Label('G1 / Dex1 · Roche-Kit · Zielbehälter',height=24)
                ui.Label('Rechten Grip halten: Arme bewegen. Trigger: greifen. B: Reset.',word_wrap=True,height=34)
                ui.Button('Gesamte Szene ansehen',clicked_fn=overview,height=28)
                ui.Button('Roche-Kit aus der Nähe',clicked_fn=closeup,height=28)
                ui.Button('Startzustand wiederherstellen',clicked_fn=request_reset,height=28)
    # Kontaktprüfung: Objekt soll nach dem Fallen auf der Tischplatte ruhen.
    for _ in range(180):
        controller.apply_action(ArticulationAction(joint_positions=q))
        world.step(render=True)
        if pending['reset']: reset()
    bbox=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_]).ComputeWorldBound(kit_root.GetPrim()).ComputeAlignedRange()
    pos=kit.get_world_pose()[0]
    pelvis=SingleRigidPrim(prim_path='/World/G1/pelvis',name='pelvis_probe')
    pelvis.initialize()
    robot_base_position=pelvis.get_world_pose()[0]
    robot_pose_ok=bool(np.linalg.norm(robot_base_position-np.array([-0.63,0.0,0.76])) < 0.03)
    state={'run_id':args.run_id,'robot_asset':str(robot_usd),'robot_dof_count':robot.num_dof,'dof_names':list(robot.dof_names),
           'cad_asset':str(cad_usd),'cad_mesh_count':len(mesh_paths),'cad_scale':0.001,
           'kit_extent_m':list(bbox.GetSize()),'kit_position_m':pos.tolist(),
           'kit_mass_kg_assumed':0.1,'kit_stable_on_table':bool(0.74 < pos[2] < 0.79),
           'robot_base_position_m':robot_base_position.tolist(),'robot_base_pose_pass':robot_pose_ok,
           'autonomous_manipulation':False,'isaaclab_task_executed':False}
    out_dir=runtime/'QuestScenes'
    out_dir.mkdir(parents=True,exist_ok=True)
    # Speichere den wiederherstellbaren Startzustand mit lokalen Assetreferenzen.
    scene_path=out_dir/'G1_RocheKit_scene.usd'
    stage.GetRootLayer().Export(str(scene_path))
    (out_dir/'scene-validation.json').write_text(json.dumps(state,indent=2),encoding='utf8')
    print('ROCHE_SCENE_READY '+json.dumps(state),flush=True)
    if not state['kit_stable_on_table'] or not robot_pose_ok:
        raise RuntimeError('Kit-Tischkontakt oder Roboterverankerung fehlgeschlagen.')
    frames=180
    while app.is_running() and (not args.frames or frames < args.frames):
        if pending['reset']: reset()
        if world.is_playing():
            quest.update(q, request_reset)
            controller.apply_action(ArticulationAction(joint_positions=q))
        world.step(render=True)
        frames+=1
        if not args.headless: time.sleep(0.008)
finally:
    if 'quest' in locals(): quest.close()
    app.close()

