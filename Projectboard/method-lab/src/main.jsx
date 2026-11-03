import {Component, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import * as Icons from 'lucide-react';
import {METHODS, STATUS} from './content.js';
import {clock} from './clock.js';
import Topic, {TOPICS} from './panels.jsx';
import Scene from './Scene.jsx';
import {DEFAULTS, RenderPanel, RobotPanel} from './settings.jsx';
import {highlightFor} from './robot.js';
import {AssetPanel, DEFAULT_SCENE, ScenePanel, sameScene} from './sceneconfig.jsx';

const FALLBACK_ROBOT = {id: 'right_arm', name: 'Nur rechter Arm', sway_mm: 0, groups: {right_arm: true, right_gripper: true}};
const remembered = (key, base) => { try { return {...base, ...JSON.parse(localStorage.getItem(key) || '{}')}; } catch { return base; } };
const remember = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* nur Komfort */ } };

const Ico = ({name, size = 20}) => { const C = Icons[name]; return C ? <C size={size} strokeWidth={1.6} aria-hidden="true"/> : null; };

function Timeline({run}) {
  const box = useRef(), head = useRef();
  const W = 1000, H = 64, last = run.frames - 1, end = last * run.dt;
  const scale = Math.min(95, Math.max(12, ...run.series.tilt, ...run.series.slosh));
  const path = key => run.series[key].map((v, i) => `${i ? 'L' : 'M'}${(i / last * W).toFixed(1)} ${(H - Math.min(v, scale) / scale * (H - 4)).toFixed(1)}`).join('');
  const air = useMemo(() => {
    const out = []; let s = null;
    run.series.height.forEach((h, i) => { const a = h > .012; if (a && s === null) s = i; if (!a && s !== null) { out.push([s, i]); s = null; } });
    if (s !== null) out.push([s, last]);
    return out;
  }, [run, last]);
  const limit = H - 5 / scale * (H - 4);
  useEffect(() => {
    let id;
    const tick = () => { if (head.current) head.current.style.left = `${clock.time(run) / end * 100}%`; id = requestAnimationFrame(tick); };
    tick();
    return () => cancelAnimationFrame(id);
  }, [run, end]);
  const scrub = e => {
    if (e.type !== 'pointerdown' && e.buttons !== 1) return;
    const r = box.current.getBoundingClientRect();
    clock.t = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * end;
  };
  return <div className="timeline" ref={box} onPointerDown={scrub} onPointerMove={scrub} aria-label="Zeitachse des Laufs">
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      {air.map(([a, b]) => <rect key={a} x={a / last * W} width={(b - a) / last * W} y="0" height={H} className="air"/>)}
      <line x1="0" x2={W} y1={limit} y2={limit} className="limit" vectorEffect="non-scaling-stroke"/>
      <path d={path('slosh')} className="s2" vectorEffect="non-scaling-stroke"/>
      <path d={path('tilt')} className="s1" vectorEffect="non-scaling-stroke"/>
    </svg>
    <div className="playhead" ref={head}/>
  </div>;
}

function Live({run}) {
  const [, force] = useState(0);
  useEffect(() => { const id = setInterval(() => force(x => x + 1), 110); return () => clearInterval(id); }, []);
  const i = Math.min(run.frames - 1, Math.round(clock.time(run) / run.dt));
  const tilt = run.series.tilt[i], speed = run.series.speed[i] * 1000, acc = run.series.acc[i];
  const slosh = run.series.height[i] > .012 ? run.series.slosh[i] : 0;
  return <div className="live">
    <div className="level" title="Kit-Neigung gegen die Senkrechte">
      <svg viewBox="0 0 60 60" aria-hidden="true">
        <circle cx="30" cy="30" r="27" className="ring"/>
        <line x1="30" y1="3" x2="30" y2="10" className="tick"/>
        <g transform={`rotate(${Math.min(tilt, 90)} 30 30)`}>
          <rect x="19" y="17" width="22" height="26" rx="2.5" className={tilt > 5 ? 'kit bad' : 'kit'}/>
          <line x1="30" y1="30" x2="30" y2="9" className={tilt > 5 ? 'axis bad' : 'axis'}/>
        </g>
      </svg>
    </div>
    <dl>
      <div><dt>Neigung</dt><dd className={tilt > 5 ? 'alert' : ''}>{tilt.toFixed(1)}<small>°</small></dd></div>
      <div><dt>Schwappen <em>Modell</em></dt><dd>{slosh.toFixed(1)}<small>°</small></dd></div>
      <div><dt>Tempo</dt><dd>{speed.toFixed(0)}<small>mm/s</small></dd></div>
      <div><dt>Beschl.</dt><dd>{acc.toFixed(2)}<small>m/s²</small></dd></div>
    </dl>
  </div>;
}

function Dock({runs, run, setRun, view, setView, locked}) {
  const [playing, setPlaying] = useState(true);
  const [rate, setRate] = useState(1);
  useEffect(() => { clock.playing = playing; }, [playing]);
  useEffect(() => { clock.rate = rate; }, [rate]);
  useEffect(() => { if (locked) setPlaying(false); }, [locked]);
  const groups = useMemo(() => { const m = {}; runs.forEach(r => (m[r.group] ??= []).push(r)); return m; }, [runs]);
  return <section className="dock" aria-label="Wiedergabe">
    <div className="dock-top">
      <button className="play" disabled={locked} onClick={() => setPlaying(p => !p)} aria-label={playing ? 'Pause' : 'Abspielen'}><Ico name={playing ? 'Pause' : 'Play'} size={18}/></button>
      <label className="select"><span>Lauf</span>
        <select value={run.id} onChange={e => { clock.t = 0; setRun(e.target.value); }}>
          {Object.entries(groups).map(([g, list]) => <optgroup key={g} label={g}>{list.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</optgroup>)}
        </select>
      </label>
      <div className="seg" role="group" aria-label="Wiedergabetempo">{[.5, 1, 2, 4].map(v => <button key={v} className={rate === v ? 'on' : ''} onClick={() => setRate(v)}>{v}×</button>)}</div>
      <div className="seg" role="group" aria-label="Kameraansicht">
        {[['overview', 'Übersicht'], ['grasp', 'Griff'], ['side', 'Seite'], ['head', 'Kopf']].map(([k, l]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{l}</button>)}
      </div>
      <Live run={run}/>
    </div>
    <Timeline run={run}/>
    <div className="dock-foot">
      <span className="lg"><i className="k1"/>Kit-Neigung</span>
      <span className="lg"><i className="k2"/>Schwappen (Modell)</span>
      <span className="lg"><i className="k3"/>5° Arbeitsannahme</span>
      <span className="lg"><i className="k4"/>Kit in der Luft</span>
      <span className="run-note">{run.note}</span>
    </div>
  </section>;
}

function MethodPanel({method, onClose}) {
  const st = STATUS[method.status];
  return <aside className="panel left" aria-label={method.name}>
    <button className="close" onClick={onClose} aria-label="Schliessen"><Ico name="X" size={16}/></button>
    <p className="eyebrow">Methode</p>
    <h2>{method.name}</h2>
    <p className="tags"><span className={`tag ${st.tone}`}>{st.label}</span>{method.recommended && <span className="tag rec">{method.recommended}</span>}</p>
    <p className="lead">{method.what}</p>
    <h3>In der Simulation einstellbar</h3>
    <ul className="clean">{method.sim.map(x => <li key={x}>{x}</li>)}</ul>
    <h3>Braucht den echten Roboter</h3>
    <ul className="clean">{method.real.map(x => <li key={x}>{x}</li>)}</ul>
    <h3>Für den Test in einer Woche</h3>
    <p>{method.week}</p>
    <h3>Hauptrisiko</h3>
    <p>{method.risk}</p>
    <h3>Stand der Belege</h3>
    <p className="evidence">{method.evidence}</p>
  </aside>;
}

function App() {
  const [data, setData] = useState(null);
  const [buffer, setBuffer] = useState(null);
  const [frameStore, setFrameStore] = useState({});
  const [runId, setRunId] = useState(null);
  const [methodId, setMethodId] = useState('skill');
  const [topic, setTopic] = useState('verdict');
  const [leftOpen, setLeftOpen] = useState(true);
  const [view, setView] = useState('overview');
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState(() => remembered('methodlab.render3', DEFAULTS));
  const [robot, setRobot] = useState(() => remembered('methodlab.robot', FALLBACK_ROBOT));
  useEffect(() => remember('methodlab.render3', settings), [settings]);
  useEffect(() => remember('methodlab.robot', robot), [robot]);
  const [scene3, setScene3] = useState(() => remembered('methodlab.scene', DEFAULT_SCENE));
  useEffect(() => remember('methodlab.scene', scene3), [scene3]);
  const [focus, setFocus] = useState(null);
  const onPick = useCallback(target => { setTopic(target.kind === 'asset' ? 'assets' : 'scene'); setFocus({...target, stamp: Date.now()}); }, []);
  const onSimulated = useCallback(async d => {
    if (!d.run) return;
    const frames = new Float32Array(await (await fetch('data/run_custom.bin', {cache: 'no-store'})).arrayBuffer());
    setFrameStore(f => ({...f, custom: frames}));
    setData(old => ({...old, runs: [...old.runs.filter(r => r.id !== 'custom'), d.run]}));
    setRunId('custom');
  }, []);
  const highlight = useMemo(() => robot.show ? highlightFor(robot.groups) : null, [robot.show, robot.groups]);
  useEffect(() => {
    Promise.all([fetch('data/data.json').then(r => r.json()), fetch('data/meshes.bin').then(r => r.arrayBuffer())])
      .then(([d, b]) => { setData(d); setBuffer(b); setRunId(d.runs[0].id); }).catch(e => setError(String(e)));
  }, []);
  useEffect(() => {
    if (!runId || frameStore[runId]) return;
    fetch(`data/run_${runId}.bin`).then(r => r.arrayBuffer()).then(b => setFrameStore(s => ({...s, [runId]: new Float32Array(b)}))).catch(e => setError(String(e)));
  }, [runId, frameStore]);
  useEffect(() => { window.__lab = {clock, setRunId, setTopic, setMethodId, setView}; }, []);
  const method = METHODS.find(m => m.id === methodId);
  const run = data?.runs.find(r => r.id === runId);
  const frames = frameStore[runId];
  const ready = data && buffer && run && frames;
  const fresh = method.status !== 'measured';
  const stale = !!run && !sameScene(run.sceneConfig || DEFAULT_SCENE, scene3);
  return <div className="app">
    <main className="stage" aria-label="3D-Ansicht">
      {ready ? <Scene data={data} buffer={buffer} run={run} frames={frames} method={method} view={view} settings={settings} highlight={highlight} scene3={scene3} onPick={onPick} wristCams={robot.wrist_cameras !== false}/> : <div className="loading">{error ? `Daten fehlen: ${error}` : 'Szene und Läufe werden geladen'}</div>}
    </main>
    <header className="brand">
      <div className="logos">
        <a href="https://swissmade.xyz/realite" target="_blank" rel="noopener noreferrer"><img src="logos/realiteSuisseGmbh_logo.png" alt="Réalité Suisse GmbH"/></a>
        <a href="https://www.zhaw.ch/" target="_blank" rel="noopener noreferrer"><img src="logos/ZHAW_Logo.png" alt="ZHAW"/></a>
        <a href="https://metaroom.city/" target="_blank" rel="noopener noreferrer"><img className="color" src="logos/metaroomcity_logo.png" alt="MetaRoom"/></a>
        <a href="https://3dclone.me/" target="_blank" rel="noopener noreferrer"><img src="logos/3dclone_logo.png" alt="3DClone.me"/></a>
        <strong>Method Lab</strong>
      </div>
      <span>Roche-Kit greifen, aufrecht tragen, in die Box stellen</span>
    </header>
    <div className={`banner ${fresh || stale ? 'warn' : ''}`}>
      <Ico name={fresh || stale ? 'TriangleAlert' : 'CircleCheck'} size={15}/>
      <span>{stale ? 'Vorschau: Der Lauf wurde mit anderen Massen berechnet. Unter „Szene“ neu berechnen.' : fresh ? `„${method.name}“ fährt hier nicht selbst. Zu sehen ist ein aufgezeichneter Referenzlauf.` : 'Aufgezeichneter MuJoCo-Lauf. Keine Animation, kein echter Roboter.'}</span>
    </div>
    <nav className="rail left" aria-label="Methoden">
      {METHODS.map(m => <button key={m.id} className={m.id === methodId ? 'on' : ''} onClick={() => { setLeftOpen(o => m.id === methodId ? !o : true); setMethodId(m.id); }} aria-pressed={m.id === methodId} title={m.name}>
        <span className="icon"><Ico name={m.icon}/><i className={`dot ${STATUS[m.status].tone}`}/></span>
        <span className="lbl">{m.short}</span>
      </button>)}
    </nav>
    {leftOpen && <MethodPanel method={method} onClose={() => setLeftOpen(false)}/>}
    <nav className="rail right" aria-label="Themen">
      {TOPICS.map(t => <button key={t.id} className={t.id === topic ? 'on' : ''} onClick={() => setTopic(c => c === t.id ? null : t.id)} aria-pressed={t.id === topic}>
        <span className="icon"><Ico name={t.icon}/></span><span className="lbl">{t.short}</span>
      </button>)}
    </nav>
    {topic && data && <aside className="panel right" aria-label="Thema"><button className="close" onClick={() => setTopic(null)} aria-label="Schliessen"><Ico name="X" size={16}/></button>{topic === 'scene' ? <ScenePanel scene={scene3} setScene={setScene3} stale={stale} onResult={onSimulated} focus={focus}/> : topic === 'assets' ? <AssetPanel scene={scene3} setScene={setScene3} focus={focus}/> : topic === 'render' ? <RenderPanel settings={settings} setSettings={setSettings}/> : topic === 'robot' ? <RobotPanel data={data} robot={robot} setRobot={setRobot}/> : <Topic id={topic} data={data}/>}</aside>}
    {ready && <Dock runs={data.runs} run={run} setRun={setRunId} view={view} setView={setView} locked={settings.pt}/>}
  </div>;
}

class Guard extends Component {
  state = {error: null};
  static getDerivedStateFromError(error) { return {error}; }
  reset = () => { try { localStorage.removeItem('methodlab.render3'); } catch { /* nur Komfort */ } location.reload(); };
  render() {
    if (!this.state.error) return this.props.children;
    return <div className="crash"><h2>Die Ansicht ist abgestürzt</h2><p>{String(this.state.error.message || this.state.error)}</p><button onClick={this.reset}>Render-Einstellungen zurücksetzen und neu laden</button></div>;
  }
}

createRoot(document.getElementById('root')).render(<Guard><App/></Guard>);
