import {useEffect, useMemo, useRef, Suspense, useState} from 'react';
import {Canvas, useFrame, useThree} from '@react-three/fiber';
import {CameraControls, ContactShadows, Grid, Html, Line, MeshReflectorMaterial, SoftShadows, useGLTF} from '@react-three/drei';
import {SlidersHorizontal} from 'lucide-react';
import {Bloom, BrightnessContrast, ChromaticAberration, DepthOfField, EffectComposer, HueSaturation, N8AO, Noise, ToneMapping, Vignette} from '@react-three/postprocessing';
import {BlendFunction, ToneMappingMode} from 'postprocessing';
import {WebGLPathTracer} from 'three-gpu-pathtracer';
import * as THREE from 'three';
import {clock} from './clock.js';
import {makeEnvironment, kelvinColor} from './environment.js';
import {groupOfBody} from './robot.js';
import {CATALOG, geomsFor} from './sceneconfig.jsx';

const TILT_LIMIT = 5;
const OVERLAY_LAYER = 1;   // Hilfslinien: Bodenspiegel und Kontaktschatten rendern nur Ebene 0
const mat = {
  shell: new THREE.MeshPhysicalMaterial({color: '#c8ccd1', metalness: .25, roughness: .38, clearcoat: .5, clearcoatRoughness: .3}),
  joint: new THREE.MeshStandardMaterial({color: '#23272c', metalness: .75, roughness: .42}),
  alu: new THREE.MeshStandardMaterial({color: '#aab0b7', metalness: .95, roughness: .3}),
  finger: new THREE.MeshStandardMaterial({color: '#191b1e', metalness: .2, roughness: .62}),
  table: new THREE.MeshPhysicalMaterial({color: '#2b3036', metalness: .05, roughness: .46, clearcoat: .55, clearcoatRoughness: .32}),
  leg: new THREE.MeshStandardMaterial({color: '#596069', metalness: .8, roughness: .35}),
  box: new THREE.MeshPhysicalMaterial({color: '#1f6fb5', metalness: 0, roughness: .28, clearcoat: .7, clearcoatRoughness: .2}),
  kit: new THREE.MeshPhysicalMaterial({color: '#f1f2f6', metalness: 0, roughness: .42, clearcoat: .25}),
  cap: new THREE.MeshPhysicalMaterial({color: '#2c3036', metalness: .1, roughness: .35, clearcoat: .4}),
  free: new THREE.MeshStandardMaterial({color: '#3f8fe0', metalness: .25, roughness: .4, emissive: '#123f73', emissiveIntensity: .7}),
  locked: new THREE.MeshStandardMaterial({color: '#3b4047', metalness: .1, roughness: .8}),
  lens: new THREE.MeshPhysicalMaterial({color: '#05070a', metalness: 0, roughness: .08, clearcoat: 1, clearcoatRoughness: .05}),
  holder: new THREE.MeshPhysicalMaterial({color: '#141518', metalness: 0, roughness: .42, clearcoat: .3, clearcoatRoughness: .35}),
};

// Generierte Materialien. Die Roboter-Meshes haben keine UVs, uvFromPosition gibt ihnen eine metrische Projektion.
const loader = new THREE.TextureLoader();
const texCache = new Map();
function tex(name, repeat, color) {
  const key = `${name}:${repeat}`;
  if (!texCache.has(key)) {
    const t = loader.load(`textures/${name}.jpg`);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repeat, repeat);
    t.anisotropy = 16;
    if (color) t.colorSpace = THREE.SRGBColorSpace;
    texCache.set(key, t);
  }
  return texCache.get(key);
}
const pbr = (name, repeat, normal) => ({map: tex(`${name}_albedo`, repeat, true), normalMap: tex(`${name}_normal`, repeat), roughnessMap: tex(`${name}_rough`, repeat), normalScale: new THREE.Vector2(normal, normal)});
const SKINS = {
  table: () => ({...pbr('bench', 1.5, .5), color: '#ffffff', roughness: 1, clearcoat: .15}),
  shell: () => ({normalMap: tex('plastic_normal', 22), roughnessMap: tex('plastic_rough', 22), normalScale: new THREE.Vector2(.28, .28), roughness: 1, metalness: .05, color: '#d6d9dc', clearcoat: .12}),
  alu: () => ({...pbr('metal', 18, .3), color: '#d0d3d6', roughness: 1, metalness: .95}),
  leg: () => ({...pbr('metal', 12, .3), color: '#a4a8ad', roughness: 1, metalness: .9}),
  joint: () => ({normalMap: tex('metal_normal', 24), normalScale: new THREE.Vector2(.2, .2)}),
};
const plain = Object.fromEntries(Object.keys(SKINS).map(k => [k, {map: null, normalMap: null, roughnessMap: null, color: mat[k].color.clone(), roughness: mat[k].roughness, metalness: mat[k].metalness, ...(mat[k].isMeshPhysicalMaterial ? {clearcoat: mat[k].clearcoat} : {})}]));
function applySkins(on) {
  for (const k of Object.keys(SKINS)) {
    mat[k].setValues(on ? SKINS[k]() : plain[k]);
    mat[k].needsUpdate = true;
  }
}

function uvFromPosition(geo) {
  const p = geo.attributes.position, n = geo.attributes.normal, uv = new Float32Array(p.count * 2);
  for (let i = 0; i < p.count; i++) {
    const ax = Math.abs(n.getX(i)), ay = Math.abs(n.getY(i)), az = Math.abs(n.getZ(i));
    const [u, v] = ax >= ay && ax >= az ? [p.getY(i), p.getZ(i)] : ay >= az ? [p.getX(i), p.getZ(i)] : [p.getX(i), p.getY(i)];
    uv[i * 2] = u; uv[i * 2 + 1] = v;
  }
  geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

function pick(g, bodyName, highlight) {
  const n = g.name;
  if (n.startsWith('table_top')) return mat.table;
  if (n.startsWith('table_leg')) return mat.leg;
  if (n.startsWith('box_')) return mat.box;
  if (n.startsWith('kit_')) return g.rgba[0] < .5 ? mat.cap : mat.kit;
  if (n.endsWith('_wrist_cam_body')) return mat.finger;
  if (n.endsWith('_wrist_cam_lens')) return mat.lens;
  if (n.includes('_wrist_cam_')) return mat.alu;
  if (highlight) return highlight[groupOfBody(bodyName)] ? mat.free : mat.locked;
  if (bodyName.includes('finger')) return mat.finger;
  if (bodyName.includes('dex1')) return mat.alu;
  if (/torso|pelvis|logo|head|hip_pitch|knee|shoulder_pitch|elbow/.test(bodyName)) return mat.shell;
  return mat.joint;
}

function geometryFor(g, buffer, cache) {
  if (g.mesh) {
    const key = g.mesh.offset;
    if (!cache.has(key)) {
      // Getrennte Attribute statt Interleaving: der Path-Tracer liest sie direkt.
      const raw = new Float32Array(buffer, g.mesh.offset, g.mesh.count * 6);
      const pos = new Float32Array(g.mesh.count * 3), nor = new Float32Array(g.mesh.count * 3);
      for (let i = 0; i < g.mesh.count; i++) {
        pos.set(raw.subarray(i * 6, i * 6 + 3), i * 3);
        nor.set(raw.subarray(i * 6 + 3, i * 6 + 6), i * 3);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
      uvFromPosition(geo);
      cache.set(key, geo);
    }
    return cache.get(key);
  }
  const [a, b, c] = g.size;
  if (g.type === 6) return new THREE.BoxGeometry(a * 2, b * 2, c * 2);
  if (g.type === 5) return new THREE.CylinderGeometry(a, a, b * 2, 32).rotateX(Math.PI / 2);
  if (g.type === 2) return new THREE.SphereGeometry(a, 24, 16);
  return null;
}

// Kamera-Frustum im MuJoCo-Kamerarahmen (Blick entlang -z, y oben), am Roboterkörper befestigt.
function Frustum({parent, pos, pitch, fovy, color}) {
  const geo = useMemo(() => {
    const far = .32, h = Math.tan(fovy / 2 * Math.PI / 180) * far, w = h * 4 / 3;
    const c = [[-w, -h, -far], [w, -h, -far], [w, h, -far], [-w, h, -far]];
    const pts = [];
    c.forEach((p, i) => { pts.push(0, 0, 0, ...p, ...p, ...c[(i + 1) % 4]); });
    return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  }, [fovy]);
  const quat = useMemo(() => {
    const x = new THREE.Vector3(0, -1, 0), y = new THREE.Vector3(Math.sin(pitch), 0, Math.cos(pitch));
    return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, x.clone().cross(y)));
  }, [pitch]);
  const ref = useRef();
  useEffect(() => {
    const p = parent.current, obj = ref.current;
    if (p && obj) { p.add(obj); return () => { p.remove(obj); }; }
  }, [parent]);
  return <lineSegments ref={ref} geometry={geo} position={pos} quaternion={quat} layers={OVERLAY_LAYER}>
    <lineBasicMaterial color={color} transparent opacity={.45} depthWrite={false}/>
  </lineSegments>;
}

function Asset({entry, height, handlers}) {
  const c = CATALOG.find(x => x.id === entry.id);
  const {scene} = useGLTF(c.file);
  const copy = useMemo(() => {
    const o = scene.clone(true);
    o.traverse(m => {
      if (!m.isMesh) return;
      m.castShadow = m.receiveShadow = true;
      if (!c.keepMaterial) m.material = mat.holder;
      // Die CAD-Exporte haben keine Normalen, ohne sie bekäme das Objekt kein Licht.
      if (!m.geometry.attributes.normal) { m.geometry = m.geometry.toNonIndexed(); m.geometry.computeVertexNormals(); }
    });
    return o;
  }, [scene]);
  return <primitive object={copy} position={[entry.x, entry.y, entry.floor ? 0 : height]} {...handlers}/>;
}

// Nach kurzem Verweilen auf Tisch, Kiste oder Asset erscheint ein runder Knopf zu dessen Einstellungen.
const TIP_SHOW_MS = 420, TIP_MOVE_MS = 90, TIP_OUT_MS = 170;
const TIP_LABEL = {table: 'Tisch einstellen', box: 'Kiste einstellen', asset: 'Asset einstellen'};
function useHoverTip(enabled) {
  const [tip, setTip] = useState(null);
  const timers = useRef({});
  const current = useRef(null);
  current.current = tip;
  useEffect(() => { if (!enabled) setTip(null); }, [enabled]);
  useEffect(() => () => { clearTimeout(timers.current.show); clearTimeout(timers.current.hide); }, []);
  const keep = () => {
    clearTimeout(timers.current.hide);
    setTip(t => t?.leaving ? {...t, leaving: false} : t);
  };
  const shrink = then => {
    setTip(t => t && {...t, leaving: true});
    timers.current.hide = setTimeout(then, TIP_OUT_MS);
  };
  const leave = () => {
    clearTimeout(timers.current.show);
    clearTimeout(timers.current.hide);
    timers.current.hide = setTimeout(() => shrink(() => setTip(null)), 650);
  };
  const same = (a, b) => a.kind === b.kind && a.index === b.index;
  const handlers = target => !enabled ? {} : {
    onPointerOver: e => {
      e.stopPropagation();
      clearTimeout(timers.current.show);
      clearTimeout(timers.current.hide);
      const point = e.point.toArray();
      const now = current.current;
      if (now && same(now.target, target)) { keep(); return; }   // anderes Teil desselben Objekts
      const appear = () => setTip({target, point, id: performance.now()});
      if (now) timers.current.show = setTimeout(() => shrink(appear), TIP_MOVE_MS);
      else timers.current.show = setTimeout(appear, TIP_SHOW_MS);
    },
    onPointerOut: leave,
  };
  return {tip, handlers, keep, leave, close: () => setTip(null)};
}

function World({data, buffer, run, frames, method, overlays, highlight, kitWorld, scene3, onPick, interactive, wristCams}) {
  const {bodies} = data.scene;
  const geoms = useMemo(() => geomsFor(data.scene.geoms, scene3), [data.scene.geoms, scene3]);
  const meshCache = useRef(new Map());
  const groups = useMemo(() => bodies.map(() => ({current: null})), [bodies]);
  const geometries = useMemo(() => {
    return geoms.map(g => geometryFor(g, buffer, meshCache.current));
  }, [geoms, buffer]);
  const hover = useHoverTip(interactive);
  const hasBox = !!scene3.box;
  const meshes = useMemo(() => geoms.map((g, i) => geometries[i] && (hasBox || !g.name.startsWith('box_')) && (wristCams || !g.name.includes('_wrist_cam_')) && {g, geometry: geometries[i], material: pick(g, g.body >= 0 ? bodies[g.body] : 'world', highlight)}).filter(Boolean),
    [geoms, geometries, bodies, highlight, hasBox, wristCams]);
  const kitIndex = bodies.indexOf('kit');
  const kitAxis = useRef();
  const q0 = useMemo(() => new THREE.Quaternion(), []), q1 = useMemo(() => new THREE.Quaternion(), []);
  const up = useMemo(() => new THREE.Vector3(), []);
  const nb = run.bodies;
  const {points, colors} = useMemo(() => {
    const good = new THREE.Color('#37d6a4'), bad = new THREE.Color('#ff6b5e'), points = [], colors = [];
    for (let f = 0; f < run.frames; f += 2) {
      const i = (f * nb + kitIndex) * 7;
      if (run.series.height[f] > .004) { points.push([frames[i], frames[i + 1], frames[i + 2]]); colors.push(run.series.tilt[f] > TILT_LIMIT ? bad : good); }
    }
    return {points, colors};
  }, [frames, run, nb, kitIndex]);

  useFrame((_, dt) => {
    clock.advance(dt, run);
    const pos = clock.time(run) / run.dt, f0 = Math.min(Math.floor(pos), run.frames - 1), f1 = Math.min(f0 + 1, run.frames - 1), a = pos - f0;
    for (let b = 0; b < nb; b++) {
      const grp = groups[b].current;
      if (!grp) continue;
      const i = (f0 * nb + b) * 7, j = (f1 * nb + b) * 7;
      grp.position.set(frames[i] + (frames[j] - frames[i]) * a, frames[i + 1] + (frames[j + 1] - frames[i + 1]) * a, frames[i + 2] + (frames[j + 2] - frames[i + 2]) * a);
      q0.set(frames[i + 4], frames[i + 5], frames[i + 6], frames[i + 3]);
      q1.set(frames[j + 4], frames[j + 5], frames[j + 6], frames[j + 3]);
      grp.quaternion.slerpQuaternions(q0, q1, a);
    }
    const boxGroup = groups[bodies.indexOf('box')]?.current;
    if (boxGroup && scene3.box) boxGroup.position.set(scene3.box.x, scene3.box.y, scene3.table.height);
    const kit = groups[kitIndex].current;
    if (kit) {
      kitWorld.set(kit.position.x, kit.position.z, -kit.position.y);
      if (kitAxis.current) {
        up.set(0, 0, 1).applyQuaternion(kit.quaternion);
        const p = kit.position, attr = kitAxis.current.geometry.attributes.position;
        attr.setXYZ(0, p.x, p.y, p.z);
        attr.setXYZ(1, p.x + up.x * .14, p.y + up.y * .14, p.z + up.z * .14);
        attr.needsUpdate = true;
        kitAxis.current.material.color.set(run.series.tilt[f0] > TILT_LIMIT ? '#ff6b5e' : '#37d6a4');
      }
    }
  });

  const place = m => <mesh key={m.g.name} geometry={m.geometry} material={m.material} position={m.g.pos}
    quaternion={[m.g.quat[1], m.g.quat[2], m.g.quat[3], m.g.quat[0]]} castShadow receiveShadow
    {...(m.g.name.startsWith('table_') ? hover.handlers({kind: 'table'}) : m.g.name.startsWith('box_') ? hover.handlers({kind: 'box'}) : {})}/>;
  return <><group rotation={[-Math.PI / 2, 0, 0]}>
    {bodies.map((name, b) => <group key={name} ref={el => { groups[b].current = el; }}>{meshes.filter(m => m.g.body === b).map(place)}</group>)}
    {meshes.filter(m => m.g.body < 0).map(place)}
    <Suspense fallback={null}>{scene3.assets.map((a, i) => <Asset key={i} entry={a} height={scene3.table.height} handlers={hover.handlers({kind: 'asset', index: i})}/>)}</Suspense>
    {overlays && points.length > 1 && <Line key={run.id} points={points} vertexColors={colors} lineWidth={1.6} transparent opacity={.85} layers={OVERLAY_LAYER}/>}
    {overlays && <line ref={kitAxis} layers={OVERLAY_LAYER}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[new Float32Array(6), 3]}/></bufferGeometry>
      <lineBasicMaterial color="#37d6a4"/>
    </line>}
    {overlays && method.cams.includes('head') && <Frustum parent={groups[bodies.indexOf('torso_link')]} pos={[.0576, .0175, .4299]} pitch={.8308} fovy={58} color="#7cc4ff"/>}
    {overlays && wristCams && method.cams.includes('wrist') && <Frustum parent={groups[bodies.indexOf('right_dex1_base_link')]} pos={[.06, 0, .062]} pitch={.65} fovy={64} color="#f0b64d"/>}
  </group>
  {hover.tip && <Html position={hover.tip.point} center zIndexRange={[30, 20]}>
    <button key={hover.tip.id} className={`scene-tip${hover.tip.leaving ? ' leaving' : ''}`} aria-label={TIP_LABEL[hover.tip.target.kind]} title={TIP_LABEL[hover.tip.target.kind]}
      onPointerEnter={hover.keep} onPointerLeave={hover.leave} onClick={() => { onPick(hover.tip.target); hover.close(); }}><SlidersHorizontal size={17} strokeWidth={1.8} aria-hidden="true"/></button>
  </Html>}
  </>;
}

export const VIEWS = {
  overview: {pos: [2.25, 1.62, 1.62], target: [.36, .74, .04]},
  grasp: {pos: [1.02, 1.16, .72], target: [.33, .79, .1]},
  side: {pos: [.35, 1.05, 2.45], target: [.3, .74, 0]},
  head: {pos: [.09, 1.3, -.02], target: [.34, .76, .08]},
};

function Controls({view}) {
  const ref = useRef();
  useEffect(() => {
    const v = VIEWS[view];
    ref.current?.setLookAt(...v.pos, ...v.target, true);
  }, [view]);
  return <CameraControls ref={ref} makeDefault minDistance={.25} maxDistance={4.5} maxPolarAngle={Math.PI * .495} smoothTime={.5}/>;
}

// Eine Umgebung für Rasterizer und Path-Tracer, daher ohne vorgefilterte Drei-Environment.
function Lighting({s}) {
  const {scene} = useThree();
  const env = useMemo(() => makeEnvironment(s.envPreset), [s.envPreset]);
  useEffect(() => {
    scene.environment = env;
    scene.environmentIntensity = s.envIntensity * s.exposure;
    scene.environmentRotation.set(0, s.envRotation * Math.PI / 180, 0);
    scene.background = s.envVisible ? env : new THREE.Color('#0a0d11');
    scene.backgroundRotation.set(0, s.envRotation * Math.PI / 180, 0);
    scene.backgroundIntensity = s.envIntensity * s.exposure;
    scene.backgroundBlurriness = s.envVisible ? (s.envPreset === 'foto' ? .015 : .35) : 0;
  }, [scene, env, s.envPreset, s.envIntensity, s.envRotation, s.envVisible, s.exposure]);
  useEffect(() => () => env.dispose(), [env]);
  const az = s.keyAzimuth * Math.PI / 180, el = s.keyElevation * Math.PI / 180;
  const pos = [5.2 * Math.cos(el) * Math.sin(az), 5.2 * Math.sin(el), 5.2 * Math.cos(el) * Math.cos(az)];
  const color = useMemo(() => kelvinColor(s.keyTemp), [s.keyTemp]);
  const rect = useRef();
  useEffect(() => { rect.current?.lookAt(.3, .8, 0); });
  if (s.pt) return <rectAreaLight ref={rect} position={pos} width={s.keySize} height={s.keySize} intensity={s.keyIntensity * s.exposure * 2.2} color={color}/>;
  return <directionalLight key={s.shadowSize} castShadow position={pos} intensity={s.keyIntensity * s.exposure} color={color} shadow-mapSize={[s.shadowSize, s.shadowSize]}
    shadow-bias={-.00012} shadow-normalBias={.012} shadow-radius={s.shadowSoft} shadow-camera-left={-1.5} shadow-camera-right={1.5} shadow-camera-top={1.5} shadow-camera-bottom={-1.5} shadow-camera-far={11}/>;
}

function PathTrace({s, runId}) {
  const {gl, scene, camera} = useThree();
  const state = useRef({tracer: null, ready: false, t: null, timer: 0, cam: new THREE.Matrix4()});
  useEffect(() => {
    const st = state.current;
    const tracer = new WebGLPathTracer(gl);
    tracer.renderDelay = 0; tracer.fadeDuration = 0; tracer.minSamples = 1;
    tracer.filterGlossyFactor = .5;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    st.tracer = tracer;
    st.build = () => { scene.updateMatrixWorld(true); tracer.setScene(scene, camera); st.ready = true; st.t = clock.t; };
    st.timer = setTimeout(st.build, 120);    // nachdem Linien und Effekte aus dem Graph sind
    return () => {
      clearTimeout(st.timer);
      st.ready = false;
      try { tracer.dispose(); } catch { /* Bibliothek räumt nicht alle Teile auf, die Oberfläche muss weiterlaufen */ }
      gl.toneMapping = THREE.NoToneMapping;
      clock.ptSamples = 0;
    };
  }, [gl, scene, camera]);
  useEffect(() => {
    const st = state.current;
    if (st.tracer) { st.tracer.bounces = s.ptBounces; st.tracer.tiles.set(s.ptTiles, s.ptTiles); if (st.ready) st.tracer.reset(); }
  }, [s.ptBounces, s.ptTiles]);
  useEffect(() => {
    const st = state.current;
    if (st.ready) { clearTimeout(st.timer); st.timer = setTimeout(st.build, 150); }
  }, [runId, s.envPreset, s.keyAzimuth, s.keyElevation, s.keySize, s.keyTemp, s.keyIntensity, s.exposure, s.envIntensity, s.envRotation, s.envVisible, s.floorRough]);
  useFrame(() => {
    const st = state.current;
    if (!st.ready) return;
    if (st.t !== clock.t) {              // Zeit verschoben: Posen haben sich geändert, Szene neu aufbauen
      st.t = clock.t;
      clearTimeout(st.timer);
      st.timer = setTimeout(st.build, 250);
    }
    if (!st.cam.equals(camera.matrixWorld)) { st.cam.copy(camera.matrixWorld); st.tracer.updateCamera(); }
    st.tracer.renderSample();
    clock.ptSamples = st.tracer.samples;
  }, 1);
  return null;
}

const TONE = {ACES: ToneMappingMode.ACES_FILMIC, AGX: ToneMappingMode.AGX, NEUTRAL: ToneMappingMode.NEUTRAL, REINHARD: ToneMappingMode.REINHARD2};

function Post({s, kitWorld}) {
  const key = [s.aa, s.ao, s.aoHalf, s.bloom, s.dof, s.vignette, s.grain, s.ca, s.tone, s.grade].join('|');
  const ca = useMemo(() => new THREE.Vector2(s.caAmount, s.caAmount), [s.caAmount]);
  return <EffectComposer key={key} multisampling={s.aa} enableNormalPass={false}>
    {s.ao && <N8AO aoRadius={s.aoRadius} distanceFalloff={.6} intensity={s.aoIntensity} quality={s.aoQuality} color="#04060a"/>}
    {s.dof && <DepthOfField target={kitWorld} focalLength={.1} bokehScale={s.dofBokeh}/>}
    {s.bloom && <Bloom luminanceThreshold={s.bloomThreshold} intensity={s.bloomIntensity} mipmapBlur/>}
    {s.ca && <ChromaticAberration offset={ca} radialModulation={false} modulationOffset={0}/>}
    {s.grade && <HueSaturation saturation={s.saturation}/>}
    {s.grade && <BrightnessContrast contrast={s.contrast}/>}
    <ToneMapping mode={TONE[s.tone]}/>
    {s.vignette && <Vignette offset={.32} darkness={s.vignetteDark}/>}
    {s.grain && <Noise premultiply opacity={s.grainAmount} blendFunction={BlendFunction.SOFT_LIGHT}/>}
  </EffectComposer>;
}

export default function Scene({data, buffer, run, frames, method, view, settings: s, highlight, scene3, onPick, wristCams}) {
  const kitWorld = useMemo(() => new THREE.Vector3(.3, .8, 0), []);
  useEffect(() => applySkins(s.materials), [s.materials]);
  const floorProps = useMemo(() => s.materials ? pbr('floor', 14, .4) : {}, [s.materials]);
  return <Canvas shadows={s.pcss ? true : 'soft'} dpr={s.dpr} gl={{antialias: false, powerPreference: 'high-performance', preserveDrawingBuffer: true}}
    camera={{position: VIEWS.overview.pos, fov: 34, near: .03, far: 30}} onCreated={state => { state.gl.toneMapping = THREE.NoToneMapping; state.camera.layers.enable(OVERLAY_LAYER); window.__lab3d = state; }}>
    {s.pcss && !s.pt && <SoftShadows key={`${s.pcssSize}-${s.pcssSamples}`} size={s.pcssSize} samples={s.pcssSamples} focus={.6}/>}
    {!s.pt && <fog key={s.envVisible ? 'hell' : 'dunkel'} attach="fog" args={s.envVisible ? ['#8d9196', 4, 13] : ['#0a0d11', 5, 11]}/>}
    <Lighting s={s}/>
    <World scene3={scene3} onPick={onPick} wristCams={wristCams} interactive={!s.pt} data={data} buffer={buffer} run={run} frames={frames} method={method} overlays={s.overlays && !s.pt} highlight={s.pt ? null : highlight} kitWorld={kitWorld}/>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -.001, 0]} receiveShadow>
      <planeGeometry args={[24, 24]}/>
      {s.pt || !s.floorMirror
        ? <meshStandardMaterial key={s.materials ? 'tex' : 'plain'} {...floorProps} color={s.materials ? '#7d8084' : '#12161b'} roughness={s.materials ? 1 : s.floorRough} metalness={s.materials ? 0 : .3}/>
        : <MeshReflectorMaterial key={s.materials ? 'tex' : 'plain'} {...floorProps} resolution={s.floorRes} blur={[420, 120]} mixBlur={1} mixStrength={s.floorReflect * 3.3} mirror={s.floorReflect} roughness={s.floorRough} metalness={s.materials ? 0 : .5} color={s.materials ? '#7d8084' : '#12161b'} depthScale={.8} minDepthThreshold={.4} maxDepthThreshold={1.3}/>}
    </mesh>
    {!s.pt && s.grid && <Grid position={[0, .001, 0]} args={[20, 20]} cellSize={.25} cellThickness={.5} cellColor="#2a333d" sectionSize={1} sectionThickness={.9} sectionColor="#3d4a58" fadeDistance={7} fadeStrength={1.6} infiniteGrid/>}
    {!s.pt && s.contact && <ContactShadows position={[0, .002, 0]} scale={7} blur={2.4} far={1.6} opacity={s.contactOpacity} resolution={512}/>}
    <Controls view={view}/>
    {s.pt ? <PathTrace s={s} runId={run.id}/> : <Post s={s} kitWorld={kitWorld}/>}
  </Canvas>;
}
