"""Lateral walking and yaw regression, synthetic controllers, refuses a human owner.

Run in WSL teleop Python. Report path is required and never overwritten.
"""
import asyncio, json, math, sys, time
from pathlib import Path
import numpy as np
from aiohttp import ClientSession

async def main():
    output=Path(sys.argv[1])
    if output.exists(): raise RuntimeError('Report already exists')
    arms='--arms' in sys.argv
    report={'human_headset_test':False,'arm_teleoperation':arms,'samples':[]}
    async with ClientSession() as client:
        async with client.get('http://127.0.0.1:18768/state') as r: latest=await r.json()
        if latest.get('controller_right'):
            raise RuntimeError('Human input active')
        if latest.get('sim_age') is None or latest['sim_age']>.5:
            raise RuntimeError('Simulation stale: '+str(latest.get('sim_age')))
        async with client.ws_connect('http://127.0.0.1:18768/ws') as ws:
            async def receive():
                nonlocal latest
                async for msg in ws:
                    if msg.type.value==1: latest=json.loads(msg.data)['status']
            receiver=asyncio.create_task(receive())
            async def phase(name,duration,stick=0,grip=0,amplitude=0,side_axis=0,turn=0):
                start=time.monotonic();last=0
                while time.monotonic()-start<duration:
                    t=time.monotonic()-start
                    hands={}
                    for side,y in [('left',.22),('right',-.22)]:
                        matrix=np.eye(4)
                        matrix[:3,3]=[.3+amplitude*math.sin(t*1.5),y,.25+amplitude*.5*math.sin(t*1.5)]
                        hands[side]={'matrix':matrix.flatten(order='F').tolist(),'arm_matrix':matrix.flatten(order='F').tolist(),
                            'grip':grip,'trigger':.5 if grip else 0,'reset':name=='reset' and side=='right','axes':[0,0,side_axis if side=='left' else turn,stick if side=='left' else 0]}
                    await ws.send_json({'type':'input','immersive':True,'arm_frame':'body-yaw-v1',**hands})
                    await asyncio.sleep(.033)
                    if time.monotonic()-last>.15:
                        report['samples'].append({'phase':name,'t':t,**{k:latest.get(k) for k in ('base_pose','measured_q','active','ik_count','error','mobility','motion_note','applied_walk_command','walk_command')}})
                        last=time.monotonic()
            try:
                await phase('reset',.2);await phase('fixed',.8)
                await ws.send_json({'type':'mobility','value':'walk'})
                for _ in range(40):
                    await phase('prepare',.2)
                    if latest.get('mobility')=='walk': break
                if latest.get('mobility')!='walk': raise RuntimeError('Walking preparation failed')
                await phase('clear_table',3,1)
                await phase('settle',1)
                await phase('left',5,side_axis=-1,grip=int(arms),amplitude=.06 if arms else 0)
                await phase('right',6,side_axis=1,grip=int(arms),amplitude=.06 if arms else 0)
                await phase('turn_left',5,turn=-1,grip=int(arms),amplitude=.06 if arms else 0)
                await phase('turn_right',6,turn=1,grip=int(arms),amplitude=.06 if arms else 0)
                await phase('release',.5)
                await asyncio.sleep(.9)
                report['timeout_fixed']=latest['mobility']=='fixed'
            finally:
                await phase('reset',.2);await phase('final_fixed',.8)
                await ws.send_json({'type':'input','immersive':False})
                await ws.close();await receiver
    checks={}
    for name in ('left','right','turn_left','turn_right'):
        rows=[s for s in report['samples'] if s['phase']==name and s['t']>.7]
        distance=0; angle=0
        def yaw(p): return math.atan2(2*(p[3]*p[6]+p[4]*p[5]),1-2*(p[5]**2+p[6]**2))
        for a,b in zip(rows,rows[1:]):
            p,q=a['base_pose'],b['base_pose']; heading=yaw(p)
            distance+=-(q[0]-p[0])*math.sin(heading)+(q[1]-p[1])*math.cos(heading)
            angle+=math.atan2(math.sin(yaw(q)-heading),math.cos(yaw(q)-heading))
        checks[name]={'lateral_m':distance,'yaw_deg':math.degrees(angle),
            'arm_active_fraction':sum(bool(s['active']) for s in rows)/len(rows),
            'arm_range_rad':float(np.ptp([s['measured_q'] for s in rows],axis=0).max()),
            'min_height_m':min(s['base_pose'][2] for s in rows),
            'all_walk':all(s['mobility']=='walk' for s in rows),
            'command':rows[-1]['walk_command'],'applied':rows[-1]['applied_walk_command']}
    report['checks']=checks
    report['pass']=bool(checks['left']['lateral_m']>.1 and checks['right']['lateral_m']<-.1 and
        checks['turn_left']['yaw_deg']>15 and checks['turn_right']['yaw_deg']<-15 and report['timeout_fixed'] and
        all(s['all_walk'] and s['min_height_m']>.6 and (not arms or (s['arm_active_fraction']>.9 and s['arm_range_rad']>.05)) for s in checks.values()))
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
    if not report['pass']: raise RuntimeError('Lateral/yaw check failed')

asyncio.run(main())
