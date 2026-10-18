"""Synthetic controller integration check, not a human Quest validation."""
import asyncio, json, time
from pathlib import Path
import numpy as np
from aiohttp import ClientSession

async def main():
    report={'kind':'synthetic-controller-integration','human_headset_test':False}
    async with ClientSession() as client:
        async with client.get('http://127.0.0.1:18768/state') as response: initial=await response.json()
        if initial.get('controller_right'): raise RuntimeError('A human controller is active; do not interrupt.')
        latest={}
        async with client.ws_connect('http://127.0.0.1:18768/ws') as ws:
            async def receive():
                nonlocal latest
                async for message in ws:
                    if message.type.value==1: latest=json.loads(message.data)
            receiver=asyncio.create_task(receive())
            def packet(shift=0,grip=1,reset=False):
                hands={}
                for side,y in [('left',.22),('right',-.22)]:
                    m=np.eye(4);m[:3,3]=[.25+(shift if side=='left' else 0),y,1.05]
                    hands[side]={'matrix':m.flatten(order='F').tolist(),'grip':grip,'trigger':0.,'reset':reset}
                return {'type':'input','immersive':True,**hands}
            async def send_for(duration,shift=0,grip=1,reset=False):
                deadline=time.monotonic()+duration
                while time.monotonic()<deadline:
                    await ws.send_json(packet(shift,grip,reset));await asyncio.sleep(.033)
            await send_for(.15,grip=0,reset=True)
            await send_for(.7,grip=0)
            before=latest['status']['measured_q']
            before_pose=latest['poses'].get('/World/G1/left_wrist_yaw_link')
            await send_for(.3)
            for step in range(1,16): await send_for(.06,shift=.002*step)
            await send_for(.8,shift=.03)
            after=latest['status']['measured_q']
            after_pose=latest['poses'].get('/World/G1/left_wrist_yaw_link')
            report.update(ik_count=latest['status']['ik_count'],active_during_command=latest['status']['active'],max_actual_joint_delta_rad=float(np.max(np.abs(np.array(after)-before))),wrist_before=before_pose,wrist_after=after_pose)
            # Let the watchdog expire while keeping the socket connected.
            await asyncio.sleep(.65)
            report['stops_on_input_timeout']=not latest['status']['active']
            report['actual_wrist_displacement_m']=float(np.linalg.norm(np.array(after_pose[:3])-before_pose[:3]))
            await send_for(.12,grip=0,reset=True)
            await send_for(.4,grip=0)
            report['reset_seq']=latest['status']['reset_seq']
            await ws.send_json({'type':'input','immersive':False})
            await ws.close();await receiver
    report['pass']=report['active_during_command'] and report['max_actual_joint_delta_rad']>.01 and report['actual_wrist_displacement_m']>.005 and report['stops_on_input_timeout']
    Path('/opt/robot/project/Simulation/quest-spatial-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not report['pass']: raise RuntimeError('Controller to actual joint integration check failed')

asyncio.run(main())
