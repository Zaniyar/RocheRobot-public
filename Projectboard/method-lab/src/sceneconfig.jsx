// Einstellbare Szene: Tisch, Box und Zusatzobjekte. Die Vorschau ändert nur das Bild, „Berechnen“ rechnet in MuJoCo.
import {useEffect, useState} from 'react';
import * as Icons from 'lucide-react';

export const DEFAULT_SCENE = {
  table: {width: .96, depth: .94, height: .75},
  box: {x: .32, y: -.2, inner_x: .15, inner_y: .11, height: .06},
  assets: [],
};
const TABLE_NEAR_X = .2, WALL = .008;

// Neue Objekte hier eintragen, Datei nach public/assets legen. Für MuJoCo zählt die vereinfachte Kollisionsform.
export const CATALOG = [
  {id: 'holder_40', name: 'Sample Holder, 40 mm tief', note: '600 mm Durchmesser, 46 Aufnahmen, 45 mm hoch', file: 'assets/holder-40mm.glb', image: 'assets/holder-40mm.png', collision: {radius: .3, height: .045}, at: [.86, 0]},
  {id: 'holder_20', name: 'Sample Holder, 20 mm tief', note: 'Erste flachere Fassung, 25 mm hoch', file: 'assets/holder-flach.glb', image: 'assets/holder-flach.png', collision: {radius: .3, height: .025}, at: [.86, 0]},
];

// Auswahl aus NVIDIA SimReady Assets, CC BY 4.0, gewandelt mit tools/convert_simready.py. Masse aus den Modellen.
const nvidia = (id, name, note, size, at, floor) => ({id, name, note, source: 'nvidia', keepMaterial: true, floor, file: `assets/nvidia/${id}.glb`, image: `assets/nvidia/${id}.jpg`,
  collision: {radius: Math.max(size[0], size[1]) / 2, height: size[2]}, at});
CATALOG.push(
  nvidia('container_vial_glass_a01', 'Glasfläschchen', '3,3 cm Durchmesser, 8,3 cm hoch', [.033, .033, .083], [.62, .28]),
  nvidia('bottle_laboratory_b01', 'Kleine Laborflasche', '1 cm Durchmesser, 5 cm hoch', [.01, .01, .05], [.56, .32]),
  nvidia('medicine_b01', 'Medikamentenflasche', '8 cm Durchmesser, 15 cm hoch', [.08, .08, .15], [.7, .32]),
  nvidia('container_system_sterilising_a02', 'Sterilisationsbehälter', '33 × 30 × 16 cm', [.328, .301, .16], [.86, .26]),
  nvidia('trolley_instrument_b01', 'Instrumentenwagen', 'Steht auf dem Boden, 106 × 58 × 89 cm', [1.056, .578, .889], [.7, 1.05], true),
);

// Es gibt genau eine Zielkiste. Eine Wahl hier ersetzt die vorhandene.
export const BOXES = [
  {id: 'box_std', name: 'Blaue Box', note: 'Standard, innen 15 × 11 × 6 cm', inner_x: .15, inner_y: .11, height: .06},
  {id: 'box_large', name: 'Grosse Kiste', note: 'Innen 30 × 22 × 12 cm', inner_x: .3, inner_y: .22, height: .12},
  {id: 'box_flat', name: 'Flache Schale', note: 'Innen 20 × 14 × 3 cm', inner_x: .2, inner_y: .14, height: .03},
];
function boxFrom(preset, old) {
  const {inner_x, inner_y, height} = preset;
  return {x: Math.max(old?.x ?? .32, TABLE_NEAR_X + inner_x / 2 + .02), y: old?.y ?? -.2, inner_x, inner_y, height};
}

export const sameScene = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Gleiche Geometrie wie write_scene in simulate_config.py.
export function geomsFor(geoms, cfg) {
  const {table: t} = cfg;
  const b = cfg.box || DEFAULT_SCENE.box;    // Ohne Kiste blendet die Szene diese Geometrie aus.
  const cx = TABLE_NEAR_X + t.depth / 2;
  return geoms.map(g => {
    const n = g.name;
    if (n === 'table_top') return {...g, pos: [cx, 0, t.height - .025], size: [t.depth / 2, t.width / 2, .025]};
    const leg = n.match(/^table_leg_(-?1)_(-?1)$/);
    if (leg) return {...g, pos: [cx + leg[1] * (t.depth / 2 - .05), leg[2] * (t.width / 2 - .05), (t.height - .05) / 2], size: [.025, .025, (t.height - .05) / 2]};
    if (n === 'box_floor') return {...g, size: [b.inner_x / 2 + WALL, b.inner_y / 2 + WALL, WALL / 4]};
    const wall = n.match(/^box_wall_([01])_([pn])$/);
    if (wall) {
      const axis = Number(wall[1]), sign = wall[2] === 'p' ? 1 : -1, inner = [b.inner_x, b.inner_y];
      const pos = [0, 0, b.height / 2], size = [b.inner_x / 2 + WALL, b.inner_y / 2 + WALL, b.height / 2];
      pos[axis] = sign * (inner[axis] + WALL) / 2;
      size[axis] = WALL / 2;
      return {...g, pos, size};
    }
    return g;
  });
}

const Ico = ({name, size = 15}) => { const C = Icons[name]; return C ? <C size={size} strokeWidth={1.7} aria-hidden="true"/> : null; };

function Cm({label, value, min, max, onChange, id}) {
  return <div className="sl"><label htmlFor={id}>{label}</label><output>{(value * 100).toFixed(1)} cm</output>
    <input id={id} type="range" min={min} max={max} step={.005} value={value} onChange={e => onChange(Number(e.target.value))}/></div>;
}

// Springt zu dem Abschnitt, den der Knopf in der 3D-Szene geöffnet hat.
function useFocus(focus) {
  useEffect(() => {
    if (!focus) return;
    const key = focus.kind === 'asset' ? `asset-${focus.index}` : focus.kind;
    const el = document.querySelector(`[data-target="${key}"]`);
    if (!el) return;
    el.scrollIntoView({block: 'center', behavior: 'smooth'});
    el.classList.add('flash');
    const id = setTimeout(() => el.classList.remove('flash'), 1400);
    return () => { clearTimeout(id); el.classList.remove('flash'); };
  }, [focus]);
}

function Simulate({scene, onResult}) {
  const [job, setJob] = useState({state: 'idle'});
  const [summary, setSummary] = useState(null);
  useEffect(() => {
    if (job.state !== 'running') return;
    const id = setInterval(async () => {
      try {
        const j = await (await fetch('api/simulate')).json();
        setJob(j);
        if (j.state === 'done') {
          const d = await (await fetch('data/custom.json', {cache: 'no-store'})).json();
          setSummary(d.summary);
          onResult(d);
        }
      } catch { setJob({state: 'failed', error: 'Keine Antwort vom lokalen Server.'}); }
    }, 1500);
    return () => clearInterval(id);
  }, [job.state, onResult]);
  const start = async () => {
    setSummary(null);
    try {
      const r = await fetch('api/simulate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(scene)});
      if (!r.ok) throw new Error(await r.text());
      setJob({state: 'running', seconds: 0});
    } catch (e) { setJob({state: 'failed', error: String(e.message || e)}); }
  };
  return <section className="sgroup">
    <h3><Ico name="Cpu"/>In MuJoCo berechnen</h3>
    <p className="hint">40 Startlagen mit Selbstkollisions- und Tischprüfung. Danach steht der Lauf „Eigene Szene“ unten zur Wahl.</p>
    {!scene.box && <p className="pstat warn"><span className="tag warn">Keine Zielkiste</span>Ohne Kiste hat der Griff kein Ziel. Unter „Assets“ eine hinzufügen.</p>}
    <button className="simbtn" onClick={start} disabled={job.state === 'running' || !scene.box}><Ico name={job.state === 'running' ? 'Loader' : 'Play'}/>{job.state === 'running' ? `Rechnet, ${job.seconds || 0} s` : 'Berechnen'}</button>
    {job.state === 'failed' && <p className="pstat bad">{job.error}</p>}
    {summary && <dl className="simres">
      <div><dt>Sanft abgelegt</dt><dd>{summary.gentle} von {summary.n}</dd></div>
      <div><dt>Verweigert</dt><dd>{summary.refused}</dd></div>
      <div><dt>Kit nicht am Boxboden</dt><dd>{summary.not_seated}</dd></div>
      <div><dt>Arm im Körper</dt><dd>{summary.self_hit}</dd></div>
      <div><dt>Kontakt mit Tisch oder Box</dt><dd>{summary.table_contact}</dd></div>
      <div><dt>Taille genutzt</dt><dd>{summary.waist_used}</dd></div>
    </dl>}
  </section>;
}

export function ScenePanel({scene, setScene, stale, onResult, focus}) {
  useFocus(focus);
  const t = v => setScene(s => ({...s, table: {...s.table, ...v}}));
  const b = v => setScene(s => ({...s, box: {...s.box, ...v}}));
  return <div className="settings">
    <p className="eyebrow">Szene</p>
    <h2>Tisch und Box</h2>
    <p className="lead">Das Bild passt sich sofort an. Ob der Griff dann noch klappt, zeigt erst die Rechnung in MuJoCo.</p>
    {stale && <p className="pstat warn"><span className="tag warn">Nur Vorschau</span>Der laufende Film stammt von anderen Massen. Der Arm kann deshalb durch Teile fahren.</p>}
    <section className="sgroup" data-target="table"><h3><Ico name="Table2"/>Tisch</h3>
      <Cm id="t-w" label="Breite" value={scene.table.width} min={.4} max={1.8} onChange={v => t({width: v})}/>
      <Cm id="t-d" label="Tiefe" value={scene.table.depth} min={.4} max={1.6} onChange={v => t({depth: v})}/>
      <Cm id="t-h" label="Höhe" value={scene.table.height} min={.55} max={1.05} onChange={v => t({height: v})}/>
    </section>
    {scene.box ? <>
    <section className="sgroup" data-target="box"><h3 className="withaction"><span><Ico name="Package"/>Kiste, Innenmass</span><button onClick={() => setScene(s => ({...s, box: null}))} aria-label="Kiste löschen" title="Kiste löschen"><Ico name="Trash2"/></button></h3>
      <Cm id="b-x" label="Tiefe" value={(scene.box || {}).inner_x} min={.09} max={.5} onChange={v => b({inner_x: v})}/>
      <Cm id="b-y" label="Breite" value={(scene.box || {}).inner_y} min={.05} max={.5} onChange={v => b({inner_y: v})}/>
      <Cm id="b-h" label="Höhe" value={(scene.box || {}).height} min={.02} max={.2} onChange={v => b({height: v})}/>
      <Cm id="b-px" label="Abstand vor dem Roboter" value={(scene.box || {}).x} min={.22} max={.6} onChange={v => b({x: v})}/>
      <Cm id="b-py" label="Seitlich, rechts negativ" value={(scene.box || {}).y} min={-.45} max={.45} onChange={v => b({y: v})}/>
    </section>
    </> : <p className="hint" data-target="box">Keine Kiste in der Szene. Unter „Assets“ eine hinzufügen.</p>}
    <div className="sactions"><button onClick={() => setScene(s => ({...DEFAULT_SCENE, assets: s.assets}))}><Ico name="RotateCcw"/>Standardmasse</button></div>
    <Simulate scene={scene} onResult={onResult}/>
  </div>;
}

export function AssetPanel({scene, setScene, focus}) {
  useFocus(focus);
  const add = c => setScene(s => ({...s, assets: [...s.assets, {id: c.id, x: c.at[0], y: c.at[1], collision: c.collision, ...(c.floor ? {floor: true} : {})}]}));
  const change = (i, v) => setScene(s => ({...s, assets: s.assets.map((a, k) => k === i ? {...a, ...v} : a)}));
  const remove = i => setScene(s => ({...s, assets: s.assets.filter((_, k) => k !== i)}));
  return <div className="settings">
    <p className="eyebrow">Asset Explorer</p>
    <h2>Objekte auf den Tisch</h2>
    <p className="lead">Für MuJoCo zählt eine vereinfachte, feste Kollisionsform. Berechnet wird unter „Szene“.</p>
    <h3>Kiste</h3>
    <div className="assets">
      {BOXES.map(c => <article key={c.id} className="asset">
        <span className="noimg boxicon"><Ico name="Package" size={22}/></span>
        <div><strong>{c.name}</strong><span>{c.note}</span></div>
        <button onClick={() => setScene(s => ({...s, box: boxFrom(c, s.box)}))} aria-label={`${c.name} ${scene.box ? 'einsetzen' : 'hinzufügen'}`} title={scene.box ? 'Ersetzt die aktuelle Kiste' : 'Hinzufügen'}><Ico name={scene.box ? 'Replace' : 'Plus'}/></button>
      </article>)}
    </div>
    <h3>Objekte</h3>
    <div className="assets">
      {CATALOG.filter(c => !c.source).map(c => <article key={c.id} className="asset">
        <img src={c.image} alt="" loading="lazy"/>
        <div><strong>{c.name}</strong><span>{c.note}</span></div>
        <button onClick={() => add(c)} aria-label={`${c.name} hinzufügen`}><Ico name="Plus"/></button>
      </article>)}
    </div>
    <h3>Labor und Pharma, NVIDIA SimReady</h3>
    <div className="assets">
      {CATALOG.filter(c => c.source === 'nvidia').map(c => <article key={c.id} className="asset">
        <img src={c.image} alt="" loading="lazy"/>
        <div><strong>{c.name}</strong><span>{c.note}</span></div>
        <button onClick={() => add(c)} aria-label={`${c.name} hinzufügen`}><Ico name="Plus"/></button>
      </article>)}
    </div>
    <p className="credit">Modelle: <a href="https://huggingface.co/datasets/nvidia/simready-assets" target="_blank" rel="noopener noreferrer">NVIDIA SimReady Assets</a>, <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>. Für die Anzeige gewandelt und verkleinert. In MuJoCo zählen sie als Zylinder.</p>
    <h3>Geplant</h3>
    <div className="assets">
      <article className="asset off"><span className="noimg"><Ico name="UserRound" size={22}/></span><div><strong><a href="https://3dclone.me/" target="_blank" rel="noopener noreferrer">3DClone.me</a> Avatare</strong><span>Geplant, noch nicht angebunden</span></div></article>
    </div>
    {scene.assets.length > 0 && <section className="sgroup"><h3><Ico name="Layers"/>In der Szene</h3>
      {scene.assets.map((a, i) => <div className="placed" key={i} data-target={`asset-${i}`}>
        <p><strong>{CATALOG.find(c => c.id === a.id)?.name || a.id}</strong><button onClick={() => remove(i)} aria-label="Entfernen"><Ico name="Trash2"/></button></p>
        <Cm id={`a-x-${i}`} label="Abstand vor dem Roboter" value={a.x} min={0} max={1.6} onChange={v => change(i, {x: v})}/>
        <Cm id={`a-y-${i}`} label="Seitlich, rechts negativ" value={a.y} min={-1.4} max={1.4} onChange={v => change(i, {y: v})}/>
      </div>)}
    </section>}
  </div>;
}
