// Browser-local MuJoCo + unchanged ONNX policy. No Isaac server connection.
import loadMujoco from '../vendor/mujoco/mujoco.js';
import * as ort from '../vendor/ort/ort.wasm.min.mjs';
let mj,model,data,config,policy,last=new Float32Array(37),running=false,ready=false;
let command=[0,0,0],demo=false,step=0,timer,test=null,next=0,generation=0;
let push=null,pushCount=0;
const files=new URL('../policy/',import.meta.url);
const send=(type,value={})=>postMessage({type,...value});
const json=async name=>{const r=await fetch(new URL(name,files));if(!r.ok)throw Error(name+': HTTP '+r.status);return r.json();};
function reset(){generation++;push=null;pushCount=0;mj.mj_resetData(model,data);config.qposIndices.forEach((q,i)=>data.qpos[q]=config.defaultPositions[i]);mj.mj_forward(model,data);last.fill(0);step=0;sendState();}
function finishPush(){
 if(!push)return;
 const {localPoint,force,end,...report}=push;
 send('pushResult',{report:{...report,endTime:data.time,endBase:Array.from(data.qpos.slice(0,3)),endRootVelocity:Array.from(data.qvel.slice(0,6)),actualDuration:data.time-report.startTime}});
 push=null;data.qfrc_applied.fill(0);
}
function applyPush(){
 data.qfrc_applied.fill(0);
 if(!push)return;
 if(data.time>=push.end-1e-9){finishPush();return;}
 const b=push.bodyId,p=b*3,r=b*9,R=data.xmat;
 // Keep the clicked surface point attached to the struck body as it moves.
 const point=[0,1,2].map(i=>data.xpos[p+i]+R[r+i*3]*push.localPoint[0]+R[r+i*3+1]*push.localPoint[1]+R[r+i*3+2]*push.localPoint[2]);
 mj.mj_applyFT(model,data,push.force,[0,0,0],point,b,data.qfrc_applied);
 push.maxGeneralizedForce=Math.max(push.maxGeneralizedForce,...Array.from(data.qfrc_applied,Math.abs));
 push.deliveredImpulseNs+=push.impulseNs/.08*model.opt.timestep;
}
function startPush(m){
 const b=Number(m.bodyId),point=m.point,direction=m.direction;
 if(!Number.isInteger(b)||b<=0||b>=model.nbody||![point,direction].every(v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite)))return;
 const norm=Math.hypot(...direction);if(norm<1e-9)return;
 if(data.qpos[2]<.35){send('fallen');return;}
 if(push)finishPush();
 test=null;
 const p=b*3,r=b*9,R=data.xmat,delta=point.map((v,i)=>v-data.xpos[p+i]);
 const localPoint=[0,1,2].map(i=>R[r+i]*delta[0]+R[r+3+i]*delta[1]+R[r+6+i]*delta[2]);
 const impulseNs=Math.max(1,Math.min(20,Number(m.impulseNs)||8));
 const unit=direction.map(v=>v/norm);
 push={bodyId:b,hitPoint:[...point],direction:unit,localPoint,impulseNs,force:unit.map(v=>v*impulseNs/.08),startTime:data.time,end:data.time+.08,startBase:Array.from(data.qpos.slice(0,3)),startRootVelocity:Array.from(data.qvel.slice(0,6)),sequence:++pushCount,deliveredImpulseNs:0,maxGeneralizedForce:0};
 send('pushStarted',{bodyId:b,point:[...point],direction:unit,impulseNs,sequence:pushCount});play();
}
function observation(){
 const obs=new Float32Array(123),r=config.rootBody*9,R=data.xmat,q=data.qvel;
 for(let i=0;i<3;i++){obs[i]=R[r+i]*q[0]+R[r+3+i]*q[1]+R[r+6+i]*q[2];obs[3+i]=q[3+i];obs[6+i]=-R[r+6+i];obs[9+i]=command[i];}
 config.qposIndices.forEach((q,i)=>obs[12+i]=data.qpos[q]-config.defaultPositions[i]);
 config.qvelIndices.forEach((q,i)=>obs[49+i]=data.qvel[q]);obs.set(last,86);return obs;
}
function sendState(){send('state',{positions:Array.from(data.geom_xpos),rotations:Array.from(data.geom_xmat),base:Array.from(data.qpos.slice(0,3)),time:data.time,command,step,running,demo});}
async function tick(){
 if(!running)return;
 const activeGeneration=generation;
 try{
  const start=performance.now();
  if(demo||test){const t=(step*.02)%12;command=t<2||t>=10?[0,0,0]:t<6?[.5,0,0]:[.35,0,.5];}
  const input=new ort.Tensor('float32',observation(),[1,123]);
  const result=await policy.run({[policy.inputNames[0]]:input});
  const output=result[policy.outputNames[0]];
  if(activeGeneration!==generation||!running){input.dispose();output.dispose();return;}
  last.set(output.data);input.dispose();output.dispose();
  if(!last.every(Number.isFinite))throw Error('Nicht endliche Policy-Aktionen');
  config.actuatorIndices.forEach((id,i)=>data.ctrl[id]=config.defaultPositions[i]+.5*last[i]);
  for(let i=0;i<4;i++){applyPush();mj.mj_step(model,data);}
  if(push&&data.time>=push.end-1e-9)finishPush();
  step++;
  if(test){
   test.minHeight=Math.min(test.minHeight,data.qpos[2]);
   if(step%10===0)test.samples.push({step,position:Array.from(data.qpos.slice(0,3)),velocity:Array.from(data.qvel.slice(0,6)),command:[...command]});
   if(step>=600){test.finished=true;test.noFall=test.minHeight>.45;send('testResult',{report:test});test=null;command=[0,0,0];running=false;}
  }
  if(data.qpos[2]<.35){running=false;finishPush();if(test){test.finished=true;test.noFall=false;send('testResult',{report:test});test=null;}send('fallen');}
  if(step%2===0||!running)sendState();
  if(step%50===0)send('timing',{computeMs:performance.now()-start});
  next+=20;if(next<performance.now()-80)next=performance.now();
  if(running)timer=setTimeout(tick,Math.max(0,next-performance.now()));
 }catch(error){running=false;send('error',{message:String(error.stack||error)});}
}
function play(){if(!running){running=true;next=performance.now();tick();}}
async function init(){
 send('status',{message:'Physik und Policy werden lokal geladen …'});
 config=await json('config.json');
 send('status',{message:'MuJoCo-Physik wird initialisiert …'});
 mj=await loadMujoco({locateFile:name=>new URL('../vendor/mujoco/'+name,import.meta.url).href});
 send('status',{message:'G1-Geometrie wird geladen …'});
 mj.FS.mkdir('/g1');mj.FS.mkdir('/g1/meshes');
 await Promise.all(['g1.xml',...config.meshes.map(n=>'meshes/'+n)].map(async name=>{const r=await fetch(new URL(name,files));if(!r.ok)throw Error(name+': HTTP '+r.status);mj.FS.writeFile('/g1/'+name,new Uint8Array(await r.arrayBuffer()));}));
 send('status',{message:'Robotermodell wird für die Physik vorbereitet …'});
 model=mj.MjModel.from_xml_path('/g1/g1.xml');data=new mj.MjData(model);
 ort.env.wasm.numThreads=1;ort.env.wasm.wasmPaths=new URL('../vendor/ort/',import.meta.url).href;
 send('status',{message:'Vortrainierte Policy wird geladen …'});
 policy=await ort.InferenceSession.create(new URL('policy.onnx',files).href,{executionProviders:['wasm'],graphOptimizationLevel:'all'});
 const geometry=[];
 for(let g=0;g<model.ngeom;g++){
  if(model.geom_group[g]!==1)continue;
  const mesh=model.geom_dataid[g];if(mesh<0)continue;
  const va=model.mesh_vertadr[mesh],vn=model.mesh_vertnum[mesh],fa=model.mesh_faceadr[mesh],fn=model.mesh_facenum[mesh];
  geometry.push({id:g,bodyId:model.geom_bodyid[g],vertices:Array.from(model.mesh_vert.slice(va*3,(va+vn)*3)),indices:Array.from(model.mesh_face.slice(fa*3,(fa+fn)*3)),color:Array.from(model.geom_rgba.slice(g*4,g*4+4))});
 }
 ready=true;reset();send('ready',{geometry,backend:'MuJoCo 3.15.0 WASM · ONNX CPU/WASM · Three.js WebGL',policyInputs:123,policyOutputs:37});
}
onmessage=event=>{
 const m=event.data;if(m.type==='init'){init().catch(e=>send('error',{message:String(e.stack||e)}));return;}if(!ready)return;
 if(m.type==='push'){startPush(m);return;}
 if(m.type==='command'){demo=false;test=null;command=m.value.map((v,i)=>Math.max(i===2?-.5:0,Math.min(i===2?.5:.5,Number(v)||0)));play();}
 if(m.type==='demo'){running=false;clearTimeout(timer);demo=true;test=null;reset();play();}
 if(m.type==='pause'){generation++;running=false;clearTimeout(timer);sendState();}
 if(m.type==='reset'){running=false;clearTimeout(timer);test=null;demo=false;command=[0,0,0];reset();}
 if(m.type==='test'){running=false;clearTimeout(timer);demo=false;reset();test={engine:'MuJoCo 3.15.0 WASM',policy:'Isaac-Velocity-Flat-G1-v0',criterion:'Minimum base height > 0.45 m; single demo run, not a comprehensive stability benchmark',minHeight:10,samples:[],finished:false};play();}
};
