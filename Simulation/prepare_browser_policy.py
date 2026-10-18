"""Prepare and test the existing Isaac Lab G1 policy in native MuJoCo.
No retraining. Public Unitree MJCF source; Isaac joint order comes from our report.
"""
from pathlib import Path
import json, shutil, xml.etree.ElementTree as ET
import numpy as np
import mujoco
import onnxruntime as ort

ROOT=Path(__file__).resolve().parents[1]
UP=Path(r'D:\RobotRuntime\BrowserPolicy\upstream')
OUT=ROOT/'Projectboard/dist/policy'
OUT.mkdir(parents=True,exist_ok=True)
tree=ET.parse(UP/'g1.xml'); root=tree.getroot()
root.set('model','G1 Isaac policy browser transfer')
ET.SubElement(root,'option',timestep='0.005',integrator='implicitfast',gravity='0 0 -9.81')
default=root.find('default/joint')
default.set('damping','0');default.set('frictionloss','0');default.set('armature','0.01')
pelvis=root.find("worldbody/body[@name='pelvis']")
pelvis.set('pos','0 0 0.74')
ET.SubElement(pelvis,'freejoint',name='root')
ET.SubElement(root.find('worldbody'),'geom',name='floor',type='plane',size='0 0 0.1',contype='2',conaffinity='1',friction='1 0.005 0.0001',rgba='0.16 0.2 0.22 1')
for geom in pelvis.iter('geom'):
    if geom.get('contype')=='0': continue
    geom.set('contype','1');geom.set('conaffinity','2')
    geom.set('friction','1 0.005 0.0001')
names=json.loads((ROOT/'Simulation/policy-validation.json').read_text())['joint_names']
defaults=[]; gains=[]
for name in names:
    q=0.
    if 'hip_pitch' in name:q=-.2
    elif 'knee' in name:q=.42
    elif 'ankle_pitch' in name:q=-.23
    elif 'elbow_pitch' in name:q=.87
    elif name=='left_shoulder_roll_joint':q=.16
    elif name=='right_shoulder_roll_joint':q=-.16
    elif 'shoulder_pitch' in name:q=.35
    elif name=='left_one_joint':q=1.
    elif name=='right_one_joint':q=-1.
    elif name=='left_two_joint':q=.52
    elif name=='right_two_joint':q=-.52
    defaults.append(q)
    if 'ankle' in name:kp,kd,force=20.,2.,20.
    elif 'hip_pitch' in name or 'knee' in name or name=='torso_joint':kp,kd,force=200.,5.,300.
    elif 'hip' in name:kp,kd,force=150.,5.,300.
    else:kp,kd,force=40.,10.,300.
    gains.append([kp,kd,force])
    act=root.find(f"actuator/position[@joint='{name}']")
    act.set('kp',str(kp));act.set('kv',str(kd));act.set('forcerange',f'{-force} {force}')
    act.attrib.pop('ctrlrange',None);act.set('ctrllimited','false')
    joint=root.find(f".//joint[@name='{name}']")
    if any(s in name for s in ('_zero_','_one_','_two_','_three_','_four_','_five_','_six_')):joint.set('armature','0.001')
tree.write(OUT/'g1.xml',encoding='unicode')
shutil.copytree(UP/'meshes',OUT/'meshes',dirs_exist_ok=True)
export=Path(r'D:\RobotRuntime\IsaacLab-2.3.2\.pretrained_checkpoints\rsl_rl\Isaac-Velocity-Flat-G1-v0\exported')
shutil.copy2(export/'policy.onnx',OUT/'policy.onnx')
model=mujoco.MjModel.from_xml_path(str(OUT/'g1.xml'))
data=mujoco.MjData(model)
ids=[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,n) for n in names]
qids=[int(model.jnt_qposadr[i]) for i in ids];vids=[int(model.jnt_dofadr[i]) for i in ids]
aids=[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_ACTUATOR,n) for n in names]
config={'jointNames':names,'defaultPositions':defaults,'qposIndices':qids,'qvelIndices':vids,'actuatorIndices':aids,'gains':gains,'dt':.005,'decimation':4,'actionScale':.5,'rootBody':mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,'pelvis'),'meshes':[p.name for p in sorted((OUT/'meshes').glob('*.STL'))]}
(OUT/'config.json').write_text(json.dumps(config,indent=2))
options=ort.SessionOptions();options.intra_op_num_threads=1
policy=ort.InferenceSession(str(export/'policy.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
data.qpos[qids]=defaults
mujoco.mj_forward(model,data)
actions=np.zeros(37,dtype=np.float32)
samples=[];minz=10
for step in range(1000):
    R=data.xmat[config['rootBody']].reshape(3,3)
    # MuJoCo freejoint translation is world-frame; angular qvel is local-frame.
    command=[0,0,0] if step<100 or step>=500 else [0.5,0,0] if step<300 else [0.35,0,.5]
    obs=np.concatenate([R.T@data.qvel[:3],data.qvel[3:6],R.T@np.array([0,0,-1]),command,data.qpos[qids]-defaults,data.qvel[vids],actions]).astype(np.float32)
    actions=policy.run(None,{policy.get_inputs()[0].name:obs[None]})[0][0]
    data.ctrl[aids]=np.array(defaults)+.5*actions
    for sub in range(4):mujoco.mj_step(model,data)
    minz=min(minz,float(data.qpos[2]))
    if step%50==0:samples.append({'step':step,'position':data.qpos[:3].tolist(),'velocity':data.qvel[:6].tolist()})
    if data.qpos[2]<.35 or not np.isfinite(data.qpos).all():
        print('FALL',step,data.qpos[:3].tolist());break
result={'engine':'MuJoCo '+mujoco.__version__,'steps':step+1,'min_height':minz,'samples':samples,'no_fall':step==999,'criterion':'root height never below 0.35 m; not a comprehensive stability benchmark'}
(ROOT/'Simulation/browser-transfer-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
