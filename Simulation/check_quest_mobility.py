"""Bounded synthetic Quest input -> live Isaac check; refuses active human input.

Leaves the simulator reset and fixed. This is not a human headset validation.
"""
import asyncio,json,time
from pathlib import Path
import numpy as np
from aiohttp import ClientSession

async def main():
    report={'kind':'synthetic-mobility-integration','human_headset_test':False}
    async with ClientSession() as client:
        async with client.get('http://127.0.0.1:18768/state') as response: state=await response.json()
        if state.get('controller_right'): raise RuntimeError('Human input active: test refused')
        if not state.get('mobility_supported'): raise RuntimeError('Mobile scene not ready')
        if state.get('sim_age') is None or state['sim_age']>.5: raise RuntimeError('Simulator stale')
        latest={}
        async with client.ws_connect('http://127.0.0.1:18768/ws') as ws:
            async def receive():
                nonlocal latest
                async for message in ws:
                    if message.type.value==1: latest=json.loads(message.data)
            receiver=asyncio.create_task(receive())
            def packet(toggle=False,back=0.,turn=0.,reset=False,grip=0.,shift=0.):
                hands={}
                for side,y in [('left',.22),('right',-.22)]:
                    m=np.eye(4);m[:3,3]=[-.35+shift,y,1.05]
                    hands[side]={'matrix':m.flatten(order='F').tolist(),'grip':grip,'trigger':0.,'reset':reset if side=='right' else False,'toggle':toggle if side=='left' else False,'axes':[0.,0.,turn if side=='right' else 0.,back if side=='left' else 0.]}
                return {'type':'input','immersive':True,**hands}
            async def send_for(duration,**kwargs):
                deadline=time.monotonic()+duration
                while time.monotonic()<deadline:
                    await ws.send_json(packet(**kwargs));await asyncio.sleep(.033)
            try:
                await send_for(.2,reset=True);await send_for(.8)
                before=np.array(latest['status']['base_pose'][:3])
                await send_for(.2,toggle=True);await send_for(.6)
                report['walk_mode']=latest['status']['mobility']=='walk'
                await send_for(2.5,back=1.)
                await send_for(1.)
                after=np.array(latest['status']['base_pose'][:3])
                report['backward_distance_m']=float(before[0]-after[0])
                report['base_height_m']=float(after[2])
                await send_for(.2,toggle=True);await send_for(.5)
                report['fixed_mode']=latest['status']['mobility']=='fixed'
                fixed=np.array(latest['status']['base_pose'][:3])
                await send_for(.6)
                report['fixed_drift_m']=float(np.linalg.norm(np.array(latest['status']['base_pose'][:3])-fixed))
                before_q=np.array(latest['status']['measured_q'])
                await send_for(.3,grip=1.)
                for i in range(1,11): await send_for(.06,grip=1.,shift=.002*i)
                await send_for(.5,grip=1.,shift=.02)
                report['arm_active']=latest['status']['active']
                report['arm_delta_rad']=float(np.max(np.abs(np.array(latest['status']['measured_q'])-before_q)))
                await send_for(.2,toggle=True);await send_for(.4)
                await asyncio.sleep(.9)
                report['timeout_fixed']=latest['status']['mobility']=='fixed'
            finally:
                await send_for(.2,reset=True);await send_for(.8)
                await ws.send_json({'type':'input','immersive':False})
                await ws.close();await receiver
    report['pass']=all([report['walk_mode'],report['fixed_mode'],report['backward_distance_m']>.1,report['base_height_m']>.6,report['fixed_drift_m']<.02,report['arm_active'],report['arm_delta_rad']>.005,report['timeout_fixed']])
    path=Path('/opt/robot/project/Simulation/quest-mobility-validation.json')
    if path.exists(): raise RuntimeError('Validation file already exists; retain previous result')
    path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not report['pass']: raise RuntimeError('Mobility integration failed')

asyncio.run(main())
