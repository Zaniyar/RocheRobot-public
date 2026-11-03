// Liefert dist/ nur auf Loopback aus und startet auf Wunsch eine MuJoCo-Rechnung: node serve.mjs [port]
import {createServer} from 'node:http';
import {readFile, writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const dist=path.join(root,'dist');
const lab=path.join(root,'../../Simulation/sim2real-lab');
const python=process.env.ROCHE_METHODLAB_PYTHON||path.join(root,'../../Simulation/mujoco-scene/.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const port=Number(process.argv[2]||8774);
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.bin':'application/octet-stream','.jpg':'image/jpeg','.png':'image/png','.glb':'model/gltf-binary'};
const job={state:'idle',error:null,started:0};

const num=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
function valid(c){
  const t=c?.table,b=c?.box;
  return t&&b&&num(t.width,.3,2)&&num(t.depth,.3,2)&&num(t.height,.4,1.2)&&num(b.x,0,2)&&num(b.y,-1,1)&&num(b.inner_x,.05,.8)&&num(b.inner_y,.05,.8)&&num(b.height,.02,.4)
    &&Array.isArray(c.assets)&&c.assets.length<=8&&c.assets.every(a=>/^[a-z0-9_]+$/.test(a.id)&&num(a.x,-2,3)&&num(a.y,-2,2)&&num(a.collision?.radius,.01,1)&&num(a.collision?.height,.001,1));
}

async function simulate(req,res){
  // Nur die eigene Seite darf rechnen lassen, nicht eine fremde Webseite im selben Browser.
  if(req.headers.origin!==`http://127.0.0.1:${port}`){res.writeHead(403).end();return;}
  if(job.state==='running'){res.writeHead(409).end('läuft schon');return;}
  let body='';
  for await(const chunk of req){body+=chunk;if(body.length>20000){res.writeHead(413).end();return;}}
  let cfg;
  try{cfg=JSON.parse(body);}catch{res.writeHead(400).end('kein JSON');return;}
  if(!valid(cfg)){res.writeHead(400).end('Werte ausserhalb des erlaubten Bereichs');return;}
  const file=path.join(dist,'data/custom_config.json');
  await writeFile(file,JSON.stringify(cfg));
  Object.assign(job,{state:'running',error:null,started:Date.now()});
  const p=spawn(python,['-X','utf8','simulate_config.py','--out',path.join(dist,'data'),'--episodes','40'],{cwd:lab,env:{...process.env,ROCHE_SCENE_CONFIG:file},windowsHide:true});
  let err='';
  p.stderr.on('data',d=>{err=(err+d).slice(-1500);});
  p.on('error',e=>Object.assign(job,{state:'failed',error:String(e)}));
  p.on('close',code=>{if(job.state==='running')Object.assign(job,code===0?{state:'done'}:{state:'failed',error:err||`Exitcode ${code}`});});
  res.writeHead(202,{'Content-Type':'application/json'}).end(JSON.stringify(job));
}

createServer(async(req,res)=>{
  const url=decodeURIComponent(new URL(req.url,'http://x').pathname);
  if(url==='/api/simulate'){
    if(req.method==='POST')return simulate(req,res);
    res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'}).end(JSON.stringify({...job,seconds:job.started?Math.round((Date.now()-job.started)/1000):0}));
    return;
  }
  const file=path.join(dist,url==='/'?'index.html':url);
  if(!file.startsWith(dist)){res.writeHead(403).end();return;}
  try{
    const body=await readFile(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'}).end(body);
  }catch{res.writeHead(404).end('Nicht gefunden');}
}).listen(port,'127.0.0.1',()=>console.log(`Method Lab: http://127.0.0.1:${port}/`));
