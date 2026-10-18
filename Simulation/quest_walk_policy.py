"""Unitree's published 12-leg-action policy, matching its Wholebody Dex1 task.

Observation/history layout follows action_provider/action_provider_wh_dds.py.
This controller never handles a real robot.
"""
import json, os, urllib.request
from collections import deque
import numpy as np
from isaacsim.core.utils.rotations import quat_to_rot_matrix

LEGS=[f'{side}_{joint}_joint' for joint in ('hip_pitch','hip_roll','hip_yaw','knee','ankle_pitch','ankle_roll') for side in ('left','right')]
ARMS=[f'{side}_{joint}_joint' for side in ('left','right') for joint in ('shoulder_pitch','shoulder_roll','shoulder_yaw','elbow','wrist_roll','wrist_pitch','wrist_yaw')]
BODY=['left_hip_pitch_joint','right_hip_pitch_joint','waist_yaw_joint','left_hip_roll_joint','right_hip_roll_joint','waist_roll_joint','left_hip_yaw_joint','right_hip_yaw_joint','waist_pitch_joint','left_knee_joint','right_knee_joint','left_shoulder_pitch_joint','right_shoulder_pitch_joint','left_ankle_pitch_joint','right_ankle_pitch_joint','left_shoulder_roll_joint','right_shoulder_roll_joint','left_ankle_roll_joint','right_ankle_roll_joint','left_shoulder_yaw_joint','right_shoulder_yaw_joint','left_elbow_joint','right_elbow_joint','left_wrist_roll_joint','right_wrist_roll_joint','left_wrist_pitch_joint','right_wrist_pitch_joint','left_wrist_yaw_joint','right_wrist_yaw_joint']

def default_q(names):
    q=np.zeros(len(names),dtype=np.float32)
    for i,n in enumerate(names):
        for pattern,value in [('hip_pitch',-.2),('knee',.42),('ankle_pitch',-.23),('elbow',.87),('shoulder_pitch',.35),('left_shoulder_roll',.18),('right_shoulder_roll',-.18),('hand_Joint',.024)]:
            if pattern in n: q[i]=value;break
    return q

def setup_gains(robot):
    kps=[];kds=[];limits=[]
    for n in robot.dof_names:
        if 'ankle' in n: values=(20,2,35)
        elif 'hip_roll' in n: values=(150,5,139)
        elif 'hip_yaw' in n: values=(150,5,88)
        elif 'hip_pitch' in n: values=(200,5,88)
        elif 'knee' in n: values=(200,5,139)
        elif 'waist' in n: values=(200,5,88 if 'yaw' in n else 35)
        elif 'shoulder_pitch' in n or 'shoulder_roll' in n: values=(100,2,25)
        elif 'shoulder_yaw' in n or 'elbow' in n: values=(50,2,25)
        elif 'wrist' in n: values=(40,2,25 if 'roll' in n else 5)
        else: values=(800,3,100)
        kp,kd,limit=values;kps.append(kp);kds.append(kd);limits.append(limit)
    controller=robot.get_articulation_controller()
    controller.set_gains(np.array(kps),np.array(kds))
    controller.set_max_efforts(np.array(limits))
    armatures=np.array([[0. if 'hand_Joint' in n else .01 for n in robot.dof_names]],dtype=np.float32)
    robot._articulation_view.set_armatures(armatures)

class QuestWalkPolicy:
    def __init__(self,robot):
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.robot=robot;self.names=list(robot.dof_names)
        self.legs=[self.names.index(n) for n in LEGS]
        self.obs_ids=[self.names.index(n) for n in LEGS+ARMS]
        self.body_ids=[self.names.index(n) for n in BODY]
        self.default=default_q(self.names)
        self.history=deque(maxlen=10);self.previous=np.zeros(29,dtype=np.float32)

    def reset(self):
        self.history.clear();self.previous[:]=0

    def action(self,targets,command):
        robot=self.robot
        rotation=quat_to_rot_matrix(robot.get_world_pose()[1])
        omega=rotation.T@robot.get_angular_velocity()
        gravity=rotation.T@np.array([0,0,-1])
        obs=np.concatenate((omega,gravity,[*command,.8],robot.get_joint_positions()[self.obs_ids]-self.default[self.obs_ids],robot.get_joint_velocities()[self.obs_ids],self.previous)).astype(np.float32)
        assert obs.shape==(91,)
        if not self.history:
            for _ in range(10): self.history.append(obs.copy())
        else: self.history.append(obs)
        payload=np.clip(np.concatenate(self.history)[None,:],-100,100).tolist()
        request=urllib.request.Request(os.environ.get('TELEOP_POLICY_URL','http://127.0.0.1:18769/'),data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with self.opener.open(request,timeout=1) as response: raw=np.asarray(json.load(response)[0],dtype=np.float32)
        if raw.shape!=(12,) or not np.isfinite(raw).all(): raise RuntimeError('Invalid walking action')
        q=targets.copy();q[self.legs]=np.clip(raw,-100,100)*.25+self.default[self.legs]
        raw_full=targets.copy();raw_full[self.legs]=raw
        self.previous=raw_full[self.body_ids].copy()
        return q
