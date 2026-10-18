import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const $=s=>document.querySelector(s),view=$('#viewport');
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor('#e9ede6');view.append(renderer.domElement);
const scene=new THREE.Scene();scene.up.set(0,0,1);
const camera=new THREE.PerspectiveCamera(42,1,.03,300);camera.up.set(0,0,1);camera.position.set(2.8,-3.2,1.9);
const orbit=new OrbitControls(camera,renderer.domElement);orbit.target.set(0,0,.7);orbit.enableDamping=true;orbit.maxDistance=15;orbit.minDistance=.8;
scene.add(new THREE.HemisphereLight(0xffffff,0x60706b,2.8));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(3,-4,7);scene.add(light);
const floor=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.MeshStandardMaterial({color:0xb9c5b7,roughness:1}));scene.add(floor);
const grid=new THREE.GridHelper(100,100,0x64786c,0x9daa9a);grid.rotation.x=Math.PI/2;grid.position.z=.002;scene.add(grid);
const meshes=new Map(),matrix=new THREE.Matrix4();let ready=false,state=null,previousBase=new THREE.Vector3(),report=null;
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();let press=null,marker=null,markerTimer;
const worker=new Worker(new URL('policy-worker.js',location.href),{type:'module'});
const status=(text,kind='')=>{$('#status').textContent=text;$('#status').dataset.kind=kind;};
const send=(type,value)=>worker.postMessage({type,value});
worker.onerror=e=>{status('Startfehler: '+e.message,'error');};
worker.onmessage=({data:m})=>{
 if(m.type==='status')status(m.message);
 if(m.type==='ready'){
  for(const g of m.geometry){const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(g.vertices,3));geo.setIndex(g.indices);geo.computeVertexNormals();const mesh=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:new THREE.Color(...g.color.slice(0,3)),metalness:.3,roughness:.48}));mesh.matrixAutoUpdate=false;mesh.userData.bodyId=g.bodyId;scene.add(mesh);meshes.set(g.id,mesh);}
  ready=true;document.querySelectorAll('[data-action]').forEach(b=>b.disabled=false);$('#backend').textContent=m.backend;status('Bereit. Starte die Demo oder gib eine Richtung vor.');send('reset');
 }
 if(m.type==='state'){
  state=m;for(const [id,mesh] of meshes){const p=id*3,r=id*9,R=m.rotations,P=m.positions;mesh.matrix.set(R[r],R[r+1],R[r+2],P[p],R[r+3],R[r+4],R[r+5],P[p+1],R[r+6],R[r+7],R[r+8],P[p+2],0,0,0,1);}
  const base=new THREE.Vector3(...m.base);if($('#follow').checked){const delta=base.clone().sub(previousBase);delta.z=0;camera.position.add(delta);orbit.target.add(delta);}previousBase.copy(base);
  $('#time').textContent=m.time.toFixed(1)+' s';$('#height').textContent=m.base[2].toFixed(3)+' m';$('#command').textContent=m.command[0].toFixed(2)+' m/s · '+m.command[2].toFixed(2)+' rad/s';$('#steps').textContent=String(m.step);
  if(m.running)status(m.demo?'Demo läuft vollständig im Browser.':'Policy läuft · Richtung steuerbar.');
 }
 if(m.type==='timing')$('#compute').textContent=m.computeMs.toFixed(1)+' ms';
 if(m.type==='pushStarted'){
  $('#push-status').textContent=(window.ROCHE_I18N?.language==='en'?'Push ':'Stoß ')+m.sequence+' · '+m.impulseNs+(window.ROCHE_I18N?.language==='en'?' N·s · at the clicked body part':' N·s · am angeklickten Körperteil');
  if(marker){scene.remove(marker);marker.dispose();}clearTimeout(markerTimer);
  marker=new THREE.ArrowHelper(new THREE.Vector3(...m.direction),new THREE.Vector3(...m.point),.35,0xe64225,.09,.055);scene.add(marker);
  markerTimer=setTimeout(()=>{if(marker){scene.remove(marker);marker.dispose();marker=null;}},700);
 }
 if(m.type==='pushResult')$('#push-result').textContent=JSON.stringify(m.report,null,2);
 if(m.type==='fallen')status('G1 ist gefallen. Mit Reset neu beginnen.','error');
 if(m.type==='error')status('Fehler: '+m.message,'error');
 if(m.type==='testResult'){report=m.report;$('#test-result').textContent=JSON.stringify(report,null,2);$('#test-details').open=true;status(report.noFall?'12-s-Test abgeschlossen: aufrecht geblieben.':'Test abgeschlossen: Sturz aufgetreten.',report.noFall?'ok':'error');$('#download').disabled=false;}
};
const commands={forward:[.5,0,0],left:[.35,0,.5],right:[.35,0,-.5],stop:[0,0,0]};
renderer.domElement.addEventListener('pointerdown',e=>{if(e.button===0&&e.isPrimary)press={id:e.pointerId,x:e.clientX,y:e.clientY,time:performance.now()};else press=null;});
renderer.domElement.addEventListener('pointermove',e=>{if(press&&Math.hypot(e.clientX-press.x,e.clientY-press.y)>5)press=null;});
renderer.domElement.addEventListener('pointercancel',()=>press=null);
renderer.domElement.addEventListener('pointerup',e=>{
 const down=press;press=null;
 if(!ready||!down||e.pointerId!==down.id||e.button!==0||performance.now()-down.time>500||Math.hypot(e.clientX-down.x,e.clientY-down.y)>5)return;
 const rect=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);
 scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);raycaster.setFromCamera(pointer,camera);
 const hit=raycaster.intersectObjects([...meshes.values()],false)[0];if(!hit)return;
 worker.postMessage({type:'push',bodyId:hit.object.userData.bodyId,point:hit.point.toArray(),direction:raycaster.ray.direction.toArray(),impulseNs:e.shiftKey?20:8});
});
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>{const action=b.dataset.action;if(commands[action])send('command',commands[action]);else{send(action);if(action==='pause')status('Pausiert.');if(action==='reset'){status('Startzustand wiederhergestellt.');$('#test-details').open=false;}if(action==='test')status('12 Sekunden Prüflauf …');}}));
const keys={KeyW:'forward',KeyA:'left',KeyD:'right',KeyS:'stop',Space:'stop'};
addEventListener('keydown',e=>{if(!ready||/INPUT|TEXTAREA/.test(e.target.tagName)||e.repeat)return;if(keys[e.code]){e.preventDefault();send('command',commands[keys[e.code]]);}if(e.code==='KeyR')send('reset');});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&ready){send('pause');status('Pausiert, weil der Tab im Hintergrund ist.');}});
$('#download').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='g1-browser-test.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
new ResizeObserver(()=>{const {width,height}=view.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}).observe(view);
function draw(){requestAnimationFrame(draw);orbit.update();renderer.render(scene,camera);}draw();worker.postMessage({type:'init'});
addEventListener('pagehide',()=>worker.terminate(),{once:true});
