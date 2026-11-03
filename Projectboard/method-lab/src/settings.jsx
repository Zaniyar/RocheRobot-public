import {useEffect, useState} from 'react';
import * as Icons from 'lucide-react';
import {clock} from './clock.js';
import {ENVIRONMENTS} from './environment.js';
import {GROUPS, PROFILE_STATUS, profileStatus} from './robot.js';

const Ico = ({name, size = 15}) => { const C = Icons[name]; return C ? <C size={size} strokeWidth={1.7} aria-hidden="true"/> : null; };

export const DEFAULTS = {
  preset: 'hoch', dpr: 1.5, overlays: true, materials: true,
  envPreset: 'foto', envIntensity: 1, envRotation: 0, envVisible: true, exposure: 1,
  keyIntensity: .9, keyAzimuth: 50, keyElevation: 58, keyTemp: 5600, keySize: 1.4,
  shadowSize: 4096, shadowSoft: 4, pcss: false, pcssSize: 25, pcssSamples: 16, contact: true, contactOpacity: .55,
  floorMirror: true, floorReflect: .06, floorRough: .6, floorRes: 1024, grid: false,
  aa: 4, ao: true, aoRadius: .16, aoIntensity: 2.2, aoQuality: 'medium', bloom: true, bloomIntensity: .22, bloomThreshold: .92,
  dof: false, dofBokeh: 2, vignette: true, vignetteDark: .5, grain: false, grainAmount: .25, ca: false, caAmount: .0004,
  grade: false, saturation: 0, contrast: 0, tone: 'ACES',
  pt: false, ptBounces: 6, ptTiles: 2,
};

const PRESETS = {
  schnell: {label: 'Schnell', icon: 'Zap', values: {dpr: 1, shadowSize: 2048, pcss: false, aa: 0, ao: false, bloom: false, dof: false, grain: false, ca: false, floorMirror: false, contact: true, pt: false}},
  hoch: {label: 'Hoch', icon: 'Gauge', values: {dpr: 1.5, shadowSize: 4096, pcss: false, aa: 4, ao: true, aoQuality: 'medium', bloom: true, dof: false, grain: false, ca: false, floorMirror: true, floorRes: 1024, pt: false}},
  ultra: {label: 'Ultra', icon: 'Gem', values: {dpr: 1.5, shadowSize: 8192, pcss: true, pcssSamples: 24, aa: 4, ao: true, aoQuality: 'high', bloom: true, dof: false, grain: false, ca: false, floorMirror: true, floorRes: 2048, pt: false}},
  kino: {label: 'Path-Tracing', icon: 'Clapperboard', values: {dpr: 1.5, pt: true, ptBounces: 8, ptTiles: 2}},
};

const Group = ({title, icon, children}) => <section className="sgroup"><h3><Ico name={icon}/>{title}</h3>{children}</section>;

function Slider({s, set, k, label, min, max, step, unit = '', digits = 2}) {
  const id = `s-${k}`;
  return <div className="sl"><label htmlFor={id}>{label}</label><output>{Number(s[k]).toFixed(digits)}{unit}</output>
    <input id={id} type="range" min={min} max={max} step={step} value={s[k]} onChange={e => set({[k]: Number(e.target.value)})}/></div>;
}
const Toggle = ({s, set, k, label}) => <label className="tg"><span>{label}</span><input type="checkbox" checked={!!s[k]} onChange={e => set({[k]: e.target.checked})}/><i/></label>;
const Choice = ({s, set, k, label, options}) => <label className="ch"><span>{label}</span><select value={s[k]} onChange={e => set({[k]: isNaN(options[0][0]) ? e.target.value : Number(e.target.value)})}>
  {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>;

function saveImage() {
  const canvas = window.__lab3d?.gl.domElement;
  if (!canvas) return;
  const a = document.createElement('a');
  a.href = canvas.toDataURL('image/png');
  a.download = `method-lab-${Date.now()}.png`;
  a.click();
}

export function RenderPanel({settings: s, setSettings}) {
  const set = patch => setSettings(c => ({...c, ...patch, preset: 'eigen'}));
  const [samples, setSamples] = useState(0);
  useEffect(() => { const id = setInterval(() => setSamples(clock.ptSamples || 0), 300); return () => clearInterval(id); }, []);
  const native = window.devicePixelRatio || 1;
  return <>
    <p className="eyebrow">Render-Einstellungen</p>
    <h2>Bildqualität</h2>
    <div className="presets" role="group" aria-label="Qualitätsstufe">
      {Object.entries(PRESETS).map(([k, p]) => <button key={k} className={s.preset === k ? 'on' : ''} onClick={() => setSettings(c => ({...c, ...p.values, preset: k}))}><Ico name={p.icon} size={17}/>{p.label}</button>)}
    </div>
    {s.pt && <p className="ptnote"><b>{Math.floor(samples)} Samples.</b> Das Bild wird mit der Zeit rauschfrei. Die Wiedergabe pausiert, weil Path-Tracing ein stehendes Bild sammelt.</p>}
    <div className="sactions">
      <button onClick={saveImage}><Ico name="Camera"/>Bild speichern</button>
      <button onClick={() => setSettings({...DEFAULTS})}><Ico name="RotateCcw"/>Zurücksetzen</button>
    </div>

    <Group title="Path-Tracing" icon="Sparkles">
      <Toggle s={s} set={set} k="pt" label="Licht physikalisch berechnen"/>
      <Slider s={s} set={set} k="ptBounces" label="Lichtsprünge" min={2} max={16} step={1} digits={0}/>
      <Choice s={s} set={set} k="ptTiles" label="Kacheln, mehr hält die Oberfläche flüssig" options={[[1, '1'], [2, '2 × 2'], [3, '3 × 3'], [4, '4 × 4']]}/>
    </Group>
    <Group title="Umgebung" icon="Globe">
      <Choice s={s} set={set} k="envPreset" label="Lichtumgebung" options={Object.entries(ENVIRONMENTS).map(([k, v]) => [k, v.label])}/>
      <Slider s={s} set={set} k="envIntensity" label="Intensität" min={0} max={3} step={.01}/>
      <Slider s={s} set={set} k="envRotation" label="Drehung" min={0} max={360} step={1} unit="°" digits={0}/>
      <Slider s={s} set={set} k="exposure" label="Belichtung" min={.2} max={3} step={.01}/>
      <Toggle s={s} set={set} k="envVisible" label="Umgebung als Hintergrund"/>
    </Group>
    <Group title="Materialien" icon="Layers">
      <Toggle s={s} set={set} k="materials" label="Generierte Texturen für Boden, Tisch, Roboter"/>
    </Group>
    <Group title="Hauptlicht" icon="Sun">
      <Slider s={s} set={set} k="keyIntensity" label="Stärke" min={0} max={6} step={.01}/>
      <Slider s={s} set={set} k="keyAzimuth" label="Richtung" min={0} max={360} step={1} unit="°" digits={0}/>
      <Slider s={s} set={set} k="keyElevation" label="Höhe" min={5} max={89} step={1} unit="°" digits={0}/>
      <Slider s={s} set={set} k="keyTemp" label="Farbtemperatur" min={2000} max={10000} step={100} unit=" K" digits={0}/>
      <Slider s={s} set={set} k="keySize" label="Grösse, nur Path-Tracing" min={.2} max={4} step={.05} unit=" m"/>
    </Group>
    <Group title="Schatten" icon="Moon">
      <Choice s={s} set={set} k="shadowSize" label="Schattenauflösung" options={[[1024, '1024'], [2048, '2048'], [4096, '4096'], [8192, '8192']]}/>
      <Slider s={s} set={set} k="shadowSoft" label="Weichheit" min={0} max={16} step={.5} digits={1}/>
      <Toggle s={s} set={set} k="pcss" label="Kontaktabhängige Halbschatten (PCSS)"/>
      {s.pcss && <Slider s={s} set={set} k="pcssSize" label="Lichtgrösse" min={2} max={80} step={1} digits={0}/>}
      {s.pcss && <Slider s={s} set={set} k="pcssSamples" label="Abtastungen" min={4} max={48} step={1} digits={0}/>}
      <Toggle s={s} set={set} k="contact" label="Kontaktschatten am Boden"/>
      {s.contact && <Slider s={s} set={set} k="contactOpacity" label="Stärke" min={0} max={1} step={.01}/>}
    </Group>
    <Group title="Boden" icon="Layers2">
      <Toggle s={s} set={set} k="floorMirror" label="Spiegelung"/>
      {s.floorMirror && <Slider s={s} set={set} k="floorReflect" label="Spiegelstärke" min={0} max={1} step={.01}/>}
      {s.floorMirror && <Choice s={s} set={set} k="floorRes" label="Spiegelauflösung" options={[[512, '512'], [1024, '1024'], [2048, '2048'], [4096, '4096']]}/>}
      <Slider s={s} set={set} k="floorRough" label="Rauheit" min={.02} max={1} step={.01}/>
      <Toggle s={s} set={set} k="grid" label="Raster"/>
    </Group>
    <Group title="Postproduktion" icon="Aperture">
      <Toggle s={s} set={set} k="ao" label="Umgebungsverdeckung (AO)"/>
      {s.ao && <Slider s={s} set={set} k="aoRadius" label="AO-Radius" min={.02} max={.6} step={.01}/>}
      {s.ao && <Slider s={s} set={set} k="aoIntensity" label="AO-Stärke" min={0} max={6} step={.05}/>}
      {s.ao && <Choice s={s} set={set} k="aoQuality" label="AO-Qualität" options={[['performance', 'Schnell'], ['medium', 'Mittel'], ['high', 'Hoch'], ['ultra', 'Ultra']]}/>}
      <Toggle s={s} set={set} k="bloom" label="Bloom"/>
      {s.bloom && <Slider s={s} set={set} k="bloomIntensity" label="Bloom-Stärke" min={0} max={2} step={.01}/>}
      {s.bloom && <Slider s={s} set={set} k="bloomThreshold" label="Bloom-Schwelle" min={0} max={1.5} step={.01}/>}
      <Toggle s={s} set={set} k="dof" label="Tiefenschärfe, Fokus aufs Kit"/>
      {s.dof && <Slider s={s} set={set} k="dofBokeh" label="Bokeh" min={0} max={12} step={.1} digits={1}/>}
      <Choice s={s} set={set} k="tone" label="Tone Mapping" options={[['ACES', 'ACES Filmic'], ['AGX', 'AgX'], ['NEUTRAL', 'Khronos Neutral'], ['REINHARD', 'Reinhard']]}/>
      <Toggle s={s} set={set} k="grade" label="Farbkorrektur"/>
      {s.grade && <Slider s={s} set={set} k="saturation" label="Sättigung" min={-1} max={1} step={.01}/>}
      {s.grade && <Slider s={s} set={set} k="contrast" label="Kontrast" min={-.5} max={.5} step={.01}/>}
      <Toggle s={s} set={set} k="vignette" label="Vignette"/>
      {s.vignette && <Slider s={s} set={set} k="vignetteDark" label="Vignettenstärke" min={0} max={1} step={.01}/>}
      <Toggle s={s} set={set} k="grain" label="Filmkorn"/>
      {s.grain && <Slider s={s} set={set} k="grainAmount" label="Kornstärke" min={0} max={1} step={.01}/>}
      <Toggle s={s} set={set} k="ca" label="Chromatische Aberration"/>
      {s.ca && <Slider s={s} set={set} k="caAmount" label="Stärke" min={0} max={.005} step={.0001} digits={4}/>}
    </Group>
    <Group title="Ausgabe" icon="MonitorCog">
      <Slider s={s} set={set} k="dpr" label={`Auflösung, ${native.toFixed(2)} ist nativ`} min={.5} max={3} step={.25}/>
      <Choice s={s} set={set} k="aa" label="Kantenglättung (MSAA)" options={[[0, 'Aus'], [2, '2×'], [4, '4×'], [8, '8×']]}/>
      <Toggle s={s} set={set} k="overlays" label="Kit-Pfad, Achse und Kamerakegel"/>
    </Group>
    <p className="foot">Grenze: Die Modelle haben Formen und Materialwerte, aber keine fotografierten Texturen. Das Licht kann fotorealistisch werden, die Oberflächen erst mit echten Materialien.</p>
  </>;
}

export function RobotPanel({data, robot, setRobot}) {
  const profiles = data.profiles || [];
  const status = PROFILE_STATUS[profileStatus(robot)];
  const wrist = robot.wrist_cameras !== false;
  const dim = GROUPS.reduce((n, g) => n + (robot.groups[g.id] ? g.action : 0), 0);
  const toggle = id => setRobot(r => ({...r, id: 'custom', name: 'Eigene Auswahl', hint: '', sway_mm: 0, groups: {...r.groups, [id]: !r.groups[id]}}));
  const download = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify({id: robot.id, name: robot.name, sway_mm: robot.sway_mm || 0, groups: robot.groups, wrist_cameras: wrist}, null, 1)], {type: 'application/json'}));
    a.download = `profil-${robot.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return <>
    <p className="eyebrow">Bewegungsprofil</p>
    <h2>Was darf sich bewegen?</h2>
    <p className="lead">Gilt fürs Sammeln und Trainieren: Gesperrte Gelenke bleiben auf der Ausgangspose und fehlen im Aktionsraum. Die Wiedergabe in der Mitte bleibt ein aufgezeichneter Lauf.</p>
    <div className="profiles" role="radiogroup" aria-label="Profil">
      {profiles.map(p => {
        const st = PROFILE_STATUS[profileStatus(p)];
        return <button key={p.id} role="radio" aria-checked={robot.id === p.id} className={robot.id === p.id ? 'on' : ''} onClick={() => setRobot(r => ({...p, wrist_cameras: r.wrist_cameras, show: r.show}))}>
          <b>{p.name}</b><span className={`tag ${st.tone}`}>{st.label}</span>
        </button>;
      })}
    </div>
    {robot.hint && <p>{robot.hint}</p>}
    <h3>Einzelne Gelenkgruppen</h3>
    <div className="joints">
      {GROUPS.map(g => <label key={g.id} className="tg"><span>{g.label}<em>{g.action} {g.action === 1 ? 'Aktion' : 'Aktionen'}{g.scene === false ? ', nicht in der Szene' : ''}</em></span>
        <input type="checkbox" checked={!!robot.groups[g.id]} onChange={() => toggle(g.id)}/><i/></label>)}
    </div>
    <h3>Kameras</h3>
    <div className="joints">
      <label className="tg"><span>Handkameras<em>Am Greifer montiert, sichtbar in der Szene</em></span><input type="checkbox" checked={wrist} onChange={e => setRobot(r => ({...r, wrist_cameras: e.target.checked}))}/><i/></label>
    </div>
    <p className="hint">Im Datensatz gespeichert: {wrist ? 'Kopfkamera und beide Handkameras' : 'nur die Kopfkamera'}.</p>
    <div className="dim"><b>{dim}</b><span>Werte pro Aktion<br/>für Policy und Datensatz</span></div>
    <p className={`pstat ${status.tone}`}><span className={`tag ${status.tone}`}>{status.label}</span>{status.text}</p>
    <label className="tg"><span>Freie Teile im 3D-Bild färben</span><input type="checkbox" checked={!!robot.show} onChange={e => setRobot(r => ({...r, show: e.target.checked}))}/><i/></label>
    <div className="sactions"><button onClick={download}><Ico name="Download"/>Profil speichern</button></div>
    <p className="code">python collect_gentle.py --profile {robot.id === 'custom' ? 'profil-custom.json' : robot.id} --episodes 50 --out data/run01 --images{!wrist && robot.id !== 'custom' ? ' --no-wrist-cameras' : ''}</p>
    <p className="foot">Fürs Labor empfohlen: nur rechter Arm. Kleinster Aktionsraum und genau das, was gemessen ist.</p>
  </>;
}
