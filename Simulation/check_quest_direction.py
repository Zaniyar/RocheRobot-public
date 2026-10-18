"""Measure actual backward -> forward response; never take over active human input."""
import asyncio
import json
from pathlib import Path
import sys
import time
import math
from aiohttp import ClientSession

async def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise RuntimeError('Report already exists')
    report = {'samples': [], 'human_test': False}
    async with ClientSession() as client:
        async with client.get('http://127.0.0.1:18768/state') as response:
            initial = await response.json()
        if initial.get('controller_right') or initial.get('sim_age', 99) > .5:
            raise RuntimeError('Human input active or simulator unavailable')
        report['initial'] = {k: initial.get(k) for k in ('base_pose', 'measured_q', 'motion_note')}
        latest = initial
        async with client.ws_connect('http://127.0.0.1:18768/ws') as ws:
            async def receive():
                nonlocal latest
                async for msg in ws:
                    if msg.type.value == 1:
                        latest = json.loads(msg.data)['status']
            task = asyncio.create_task(receive())
            async def phase(name, duration, stick):
                start = time.monotonic()
                last = 0
                while time.monotonic() - start < duration:
                    hands = {side: {'matrix': [1,0,0,0,0,1,0,0,0,0,1,0,-.35,.22 if side=='left' else -.22,1.05,1],
                                    'grip': 0, 'trigger': 0, 'reset': name == 'reset' and side == 'right',
                                    'axes': [0,0,0,stick if side=='left' else 0]} for side in ('left','right')}
                    await ws.send_json({'type': 'input', 'immersive': True, **hands})
                    await asyncio.sleep(.033)
                    if time.monotonic() - last > .2:
                        report['samples'].append({'phase': name, 't': time.monotonic()-start,
                            **{k: latest.get(k) for k in ('base_pose','walk_command','motion_note','mobility','applied_walk_command')}})
                        last = time.monotonic()
            try:
                if '--reset' in sys.argv:
                    await phase('reset', .2, 0)
                    await phase('after_reset', 1, 0)
                await phase('fixed', .3, 0)
                await ws.send_json({'type': 'mobility', 'value': 'walk'})
                prepare_started=time.monotonic()
                while latest.get('mobility')!='walk' and time.monotonic()-prepare_started<8:
                    await phase('prepare', .2, 0)
                if latest.get('mobility')!='walk':
                    raise RuntimeError('Walking preparation did not complete')
                report['prepare_seconds']=time.monotonic()-prepare_started
                await phase('settle', .7, 0)
                await phase('backward', 5, 1)
                await phase('forward', 6, -1)
                await phase('stop', 1, 0)
            finally:
                await ws.send_json({'type': 'mobility', 'value': 'fixed'})
                await phase('fixed_end', .4, 0)
                await ws.send_json({'type': 'input', 'immersive': False})
                await ws.close()
                await task
    distances = {}
    for name in ('backward','forward'):
        samples = [s for s in report['samples'] if s['phase']==name and s['t']>.7]
        distance = 0
        for a,b in zip(samples,samples[1:]):
            p,q = a['base_pose'],b['base_pose']
            yaw = math.atan2(2*(p[3]*p[6]+p[4]*p[5]),1-2*(p[5]**2+p[6]**2))
            distance += (q[0]-p[0])*math.cos(yaw)+(q[1]-p[1])*math.sin(yaw)
        distances[name] = distance
    report['signed_distance_m'] = distances
    report['pass'] = distances['backward'] < -.1 and distances['forward'] > .1
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'pass': report['pass'], 'signed_distance_m': distances, 'report': str(output)}))

asyncio.run(main())
