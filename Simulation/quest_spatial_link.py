"""Isaac client: publish real body poses; apply rate-limited arm targets."""
import json, os, threading, time, urllib.request
import numpy as np
from quest_scene_geometry import QuestSceneGeometry

class QuestSpatialLink:
    def __init__(self,robot,stage,mobile=False,bridge_url=None,geometry_roots=None):
        self.bridge_url=(bridge_url or os.environ.get("TELEOP_SIM_URL","http://127.0.0.1:18768")).rstrip("/")
        self.robot=robot
        self.names=[f'{s}_{j}_joint' for s in ('left','right') for j in ('shoulder_pitch','shoulder_roll','shoulder_yaw','elbow','wrist_roll','wrist_pitch','wrist_yaw')]
        self.ids=[robot.get_dof_index(n) for n in self.names]
        self.grippers=[[robot.get_dof_index(f'{s}_hand_Joint{i}_1') for i in (1,2)] for s in ('left','right')]
        self.geometry=QuestSceneGeometry(stage,roots=geometry_roots)
        if mobile:
            self.geometry.document['version']='mobile-3-concurrent-arms'
            self.geometry.document['eye']=[-.44,0,1.38]
        self.telemetry={}
        self.lock=threading.Lock();self.stopped=threading.Event()
        self.snapshot=None;self.command={};self.received=0.;self.last_capture=0.;self.reset_seq=0;self.last_error=0.
        self.thread=threading.Thread(target=self.network,daemon=True);self.thread.start()

    def network(self):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        sent=False
        while not self.stopped.is_set():
            try:
                with self.lock: snapshot=self.snapshot
                path='/simulation' if sent else '/scene'
                data=snapshot if sent else self.geometry.document
                if data is not None:
                    request=urllib.request.Request(self.bridge_url+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                    with opener.open(request,timeout=5 if not sent else .5) as response: result=json.load(response)
                    if sent:
                        with self.lock: self.command=result;self.received=time.monotonic()
                    sent=result.get('scene_available',True)
            except Exception as e:
                sent=False
                if time.monotonic()-self.last_error>5:
                    print(f'QUEST_SPATIAL_LINK_ERROR {e}',flush=True);self.last_error=time.monotonic()
            self.stopped.wait(.03)

    def update(self,q,request_reset):
        with self.lock: command=self.command.copy();fresh=time.monotonic()-self.received<.3
        if fresh and command.get('reset_seq',0)!=self.reset_seq:
            self.reset_seq=command['reset_seq'];request_reset()
        elif fresh and command.get('active'):
            arm=np.asarray(command.get('arm_q',[]))
            if command.get('arm_names')==self.names and arm.shape==(14,) and np.isfinite(arm).all():
                q[self.ids]+=np.clip(arm-q[self.ids],-.012,.012)
                for ids,grip in zip(self.grippers,command.get('grip',[0,0])):
                    q[ids]+=np.clip(-.02+.044*np.clip(grip,0,1)-q[ids],-.001,.001)
        if time.monotonic()-self.last_capture>.04:
            p,r=self.robot.get_world_pose()
            data={'q':self.robot.get_joint_positions()[self.ids].tolist(),'poses':self.geometry.poses(),'base_pose':[*p.tolist(),*r.tolist()],**self.telemetry}
            with self.lock: self.snapshot=data
            self.last_capture=time.monotonic()

    def reset(self): self.geometry.reset()
    def mobility_command(self):
        with self.lock:
            if time.monotonic()-self.received>.3: return 'fixed',[0.,0.,0.]
            command=self.command.copy()
        # A disconnected headset stops and anchors the simulation.
        if command.get('input_age') is None or command['input_age']>.3: return 'fixed',[0.,0.,0.]
        values=np.asarray(command.get('walk_command',[0.,0.,0.]),dtype=float)
        if values.shape!=(3,) or not np.isfinite(values).all(): return 'fixed',[0.,0.,0.]
        return command.get('requested_mobility','fixed'),np.clip(values,[-.5,-.5,-1.2],[.5,.5,1.2]).tolist()
    def close(self): self.stopped.set();self.thread.join(timeout=6)
