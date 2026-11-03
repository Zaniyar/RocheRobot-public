import {useState} from 'react';
import * as Icons from 'lucide-react';
import {LAB_DAY, QUESTIONS, SWEEP_META, VERDICT, WEEK} from './content.js';

const Ico = ({name, size = 18}) => { const C = Icons[name]; return C ? <C size={size} strokeWidth={1.6} aria-hidden="true"/> : null; };
const pct = (a, b) => `${Math.round(a / b * 100)} %`;

export const TOPICS = [
  {id: 'verdict', short: 'Antwort', icon: 'Scale'},
  {id: 'measure', short: 'Messwerte', icon: 'Activity'},
  {id: 'budget', short: 'Toleranz', icon: 'Crosshair'},
  {id: 'work', short: 'Reichweite', icon: 'Map'},
  {id: 'week', short: 'Woche', icon: 'CalendarDays'},
  {id: 'ask', short: 'Fragen', icon: 'MessagesSquare'},
  {id: 'scene', short: 'Szene', icon: 'Table2'},
  {id: 'assets', short: 'Assets', icon: 'Shapes'},
  {id: 'robot', short: 'Roboter', icon: 'Bot'},
  {id: 'render', short: 'Render', icon: 'SlidersHorizontal'},
];

function compare(data) {
  const c = data.results.sweeps.compare;
  return {old: c.find(x => x.value === 'scripted'), neu: c.find(x => x.value === 'gentle')};
}

function Verdict({data}) {
  const {old, neu} = compare(data);
  return <>
    <p className="eyebrow">Die ehrliche Antwort</p>
    <h2>Ja, viel. Aber nicht alles.</h2>
    <p className="lead">Ohne Roboter können wir keinen Griff beweisen. Wir können aber Bahn, Software und Fehlerbudget so vorbereiten, dass der Labortag für die offenen Fragen genutzt wird und nicht für Grundlagen.</p>
    <div className="beforeafter">
      <div><span>Altes Skript</span><b>{old.tilt_median.toFixed(1)}°</b><em>mittlere Spitzenneigung</em></div>
      <Ico name="ArrowRight"/>
      <div className="now"><span>Nach Sim-Tuning</span><b>{neu.tilt_median.toFixed(1)}°</b><em>gleiche Szene, {neu.n} Startlagen</em></div>
    </div>
    {VERDICT.map(v => <section key={v.title} className={`vgroup ${v.tone}`}>
      <h3><Ico name={v.icon} size={16}/>{v.title}</h3>
      <dl>{v.items.map(([a, b]) => <div key={a}><dt>{a}</dt><dd>{b}</dd></div>)}</dl>
    </section>)}
    <p className="foot">Empfehlung: Plan A ist der geplante Griff, Plan B ist ACT auf echten Demonstrationen im Labor. Kein Sim-Ergebnis sagt die reale Erfolgsquote voraus.</p>
  </>;
}

function Measure({data}) {
  const {old, neu} = compare(data);
  const rows = [
    ['Sauber abgelegt', pct(old.placed, old.n), pct(neu.placed, neu.n)],
    ['Zusätzlich immer unter 5°', pct(old.gentle, old.n), pct(neu.gentle, neu.n)],
    ['Arm im eigenen Körper', old.self_hit, neu.self_hit],
    ['Griff verweigert', old.plan_fail, neu.plan_fail],
    ['Liegt umgekippt in der Box', old.lying_in_box, neu.lying_in_box],
    ['Spitzenneigung, Median', `${old.tilt_median.toFixed(1)}°`, `${neu.tilt_median.toFixed(1)}°`],
    ['Spitzenneigung, 95 %', `${old.tilt_p95.toFixed(1)}°`, `${neu.tilt_p95.toFixed(1)}°`],
    ['Spitzenbeschleunigung', `${old.acc_median.toFixed(1)} m/s²`, `${neu.acc_median.toFixed(2)} m/s²`],
    ['Schwappen (Modell)', `${old.slosh_median.toFixed(0)}°`, `${neu.slosh_median.toFixed(1)}°`],
    ['Dauer, Median', `${old.duration_median.toFixed(0)} s`, `${neu.duration_median.toFixed(0)} s`],
  ];
  return <>
    <p className="eyebrow">Eigene Messung, {data.results.engine}</p>
    <h2>Vorher und nachher</h2>
    <p className="lead">Gleiche Szene, gleiche {old.n} Startlagen. Fehlschlag sind jetzt auch: über 10° Neigung nach dem Ablegen und jede Selbstkollision. Die frühere Zählung „38 von 40“ erkannte beides nicht.</p>
    <table className="cmp"><thead><tr><th>Grösse</th><th>Altes Skript</th><th>Sanft</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r[0]}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td></tr>)}</tbody></table>
    <h3>Was das sanfte Verfahren ändert</h3>
    <ul className="clean">
      <li>Hand behält nach dem Griff ihre Orientierung, nur Drehung um die Senkrechte.</li>
      <li>Min-Jerk statt abrupter Gelenkschritte, begrenzte Gelenkrate.</li>
      <li>Niedrigere Tragehöhe, tieferes Absetzen, langsames Öffnen.</li>
      <li>Ellbogen bleibt aussen, jede Bahn wird auf Selbstkollision geprüft.</li>
      <li>Der Planer verweigert Griffe, für die kein solcher Gesamtweg existiert.</li>
    </ul>
    <p className="foot">Grenzen: Becken fixiert, Regler und Reibung unkalibriert, kein Kamerabild. Selbstkollision wird auf konvexen Hüllen geprüft, stichprobenartig gegengeprüft auf den exakten Netzen. Das Kit ist ein starrer Körper, die Flüssigkeit wird nachgerechnet ({data.results.slosh_model.f_hz.toFixed(1)} Hz angenommen).</p>
  </>;
}

function Spark({rows, metric, meta}) {
  const [hover, setHover] = useState(null);
  const W = 300, H = 74, pad = 10;
  const x = i => pad + i / Math.max(1, rows.length - 1) * (W - pad * 2);
  const y = v => H - 16 - v * (H - 26);
  const val = r => r[metric] / r.n;
  return <div className="spark">
    <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)} role="img" aria-label={`${meta.title}: ${rows.map(r => `${r.value} ${meta.unit} ${Math.round(val(r) * 100)} Prozent`).join(', ')}`}>
      <line x1={pad} x2={W - pad} y1={y(1)} y2={y(1)} className="grid"/>
      <line x1={pad} x2={W - pad} y1={y(.9)} y2={y(.9)} className="grid dashed"/>
      <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} className="grid"/>
      <path d={rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)} ${y(val(r))}`).join('')} className="ln"/>
      {rows.map((r, i) => <g key={r.value} onMouseEnter={() => setHover(i)}>
        <rect x={x(i) - 18} y="0" width="36" height={H} fill="transparent"/>
        <circle cx={x(i)} cy={y(val(r))} r={hover === i ? 5.5 : 4} className={r.value === meta.nominal ? 'pt nominal' : 'pt'}/>
        <text x={x(i)} y={H - 2} textAnchor="middle" className="tk">{r.value}</text>
      </g>)}
    </svg>
    {hover !== null && <div className="tip">{rows[hover].value} {meta.unit}: {rows[hover][metric]} von {rows[hover].n}, Neigung {rows[hover].tilt_median?.toFixed(1) ?? '–'}°</div>}
  </div>;
}

function tolerance(rows, meta, metric) {
  const ok = r => r[metric] / r.n >= .9;
  const start = Math.max(0, rows.findIndex(r => r.value === meta.nominal));
  if (!ok(rows[start])) return 'schon nominal unter 90 %';
  let hi = start, lo = start;
  while (hi + 1 < rows.length && ok(rows[hi + 1])) hi++;
  while (lo > 0 && ok(rows[lo - 1])) lo--;
  if (meta.twoSided) return `${rows[lo].value} bis +${rows[hi].value} ${meta.unit}`;
  if (meta.higherBetter) return `ab ${rows[lo].value} ${meta.unit}`.trim();
  if (lo !== hi && lo !== start) return `${rows[lo].value} bis ${rows[hi].value} ${meta.unit}`;
  return `bis ${rows[hi].value} ${meta.unit}${hi === rows.length - 1 ? ' (Testgrenze)' : ''}`;
}

function Budget({data}) {
  const [metric, setMetric] = useState('placed');
  const sweeps = data.results.sweeps;
  const names = Object.keys(SWEEP_META);
  return <>
    <p className="eyebrow">Das wichtigste Ergebnis</p>
    <h2>Toleranzbudget fürs Labor</h2>
    <p className="lead">Geordnet nach Risiko. Jeweils eine Grösse gestört, der Planer weiss nichts davon. So wird sichtbar, was im Labor genau stimmen muss. Gestrichelt: 90 %. {sweeps[names[0]][0].n} planbare Startlagen pro Punkt, heller Punkt ist der Nominalwert.</p>
    <div className="seg wide" role="group" aria-label="Kennzahl">
      <button className={metric === 'placed' ? 'on' : ''} onClick={() => setMetric('placed')}>Abgelegt</button>
      <button className={metric === 'gentle' ? 'on' : ''} onClick={() => setMetric('gentle')}>Abgelegt und unter 5°</button>
    </div>
    <div className="sparks">
      {names.filter(k => !SWEEP_META[k].blind).map(k => <section key={k}>
        <h4>{SWEEP_META[k].title}<small>{SWEEP_META[k].unit}</small></h4>
        <Spark rows={sweeps[k]} metric={metric} meta={SWEEP_META[k]}/>
        <p className="tol"><b>{tolerance(sweeps[k], SWEEP_META[k], metric)}</b><span>{SWEEP_META[k].lab}</span></p>
      </section>)}
    </div>
    <h3>Hier sagt die Simulation wenig aus</h3>
    <div className="sparks">
      {names.filter(k => SWEEP_META[k].blind).map(k => <section key={k}>
        <h4>{SWEEP_META[k].title}<small>{SWEEP_META[k].unit}</small></h4>
        <Spark rows={sweeps[k]} metric={metric} meta={SWEEP_META[k]}/>
        <p className="blind">{SWEEP_META[k].blind}</p>
      </section>)}
    </div>
    <p className="foot">Simulationsgrenzen unter jeweils einer Störung. Im Labor treten mehrere gleichzeitig auf, die echten Grenzen sind also eher enger. Kleine Stichprobe, Richtwerte.</p>
  </>;
}

function Work({data}) {
  const pts = data.results.workspace;
  const X = v => 20 + (v - .28) / .09 * 240, Y = v => 160 - (v + .08) / .16 * 140;
  const ok = pts.filter(p => p.ok).length;
  return <>
    <p className="eyebrow">Arbeitsraum</p>
    <h2>Wo der rechte Arm aufrecht greift</h2>
    <p className="lead">{ok} von {pts.length} zufälligen Startlagen lassen einen aufrechten Gesamtweg zu. Die übrigen verweigert der Planer, bevor sich der Arm bewegt.</p>
    <svg className="map" viewBox="0 0 280 190" role="img" aria-label={`Kit-Startlagen, ${ok} planbar, ${pts.length - ok} verweigert`}>
      <rect x="20" y="20" width="240" height="140" className="plate"/>
      {pts.map((p, i) => {
        const dx = Math.cos(p.yaw) * 6, dy = Math.sin(p.yaw) * 6;
        return <line key={i} x1={X(p.x) - dx} x2={X(p.x) + dx} y1={Y(p.y) + dy} y2={Y(p.y) - dy} className={p.ok ? (p.placed ? 'k ok' : 'k miss') : 'k no'}/>;
      })}
      <text x="140" y="178" textAnchor="middle" className="tk">x 0,28 bis 0,37 m (vom Roboter weg)</text>
      <text x="12" y="90" textAnchor="middle" className="tk" transform="rotate(-90 12 90)">y −0,08 bis 0,08 m</text>
    </svg>
    <p className="lg-row"><span className="lg"><i className="m1"/>abgelegt</span><span className="lg"><i className="m2"/>geplant, misslungen</span><span className="lg"><i className="m3"/>verweigert</span></p>
    <p>Jeder Strich zeigt Lage und Drehung eines Kits. Verweigert wird vor allem, wenn das Kit links vor dem Körper liegt oder weit entfernt ist, und bei Griffwinkeln von −60° bis 0°. Der rechte Arm kommt dort nicht hin, ohne das Kit zu neigen oder den Oberarm in den Rumpf zu drücken.</p>
    <h3>Folge fürs Labor</h3>
    <ul className="clean"><li>Beim ersten Test das Kit im sicheren Bereich hinlegen.</li><li>Später linken Arm, Umgreifen oder Taille als zusätzliche Freiheit prüfen.</li></ul>
  </>;
}

function Week() {
  return <>
    <p className="eyebrow">Fahrplan, Vorschlag</p>
    <h2>Sieben Tage bis zum Labor</h2>
    <ol className="steps">{WEEK.map(([d, t, x]) => <li key={d}><span>{d}</span><div><b>{t}</b><p>{x}</p></div></li>)}</ol>
    <h3>Reihenfolge am Labortag</h3>
    <ol className="lab">{LAB_DAY.map(([t, x]) => <li key={t}><b>{t}</b> {x}</li>)}</ol>
    <p className="foot">Zugangsdauer, Hardware und Sicherheitsregeln im Labor sind noch nicht bestätigt, siehe Fragen.</p>
  </>;
}

function Ask() {
  return <>
    <p className="eyebrow">Vor dem Labor klären</p>
    <h2>Offene Fragen</h2>
    <p className="lead">Jede Antwort ersetzt eine Annahme aus unserer Simulation.</p>
    <ul className="qs">{QUESTIONS.map(([who, q]) => <li key={q}><span>{who}</span>{q}</li>)}</ul>
  </>;
}

export default function Topic({id, data}) {
  const C = {verdict: Verdict, measure: Measure, budget: Budget, work: Work, week: Week, ask: Ask}[id];
  if (!data.results && !['week', 'ask'].includes(id)) return <><p className="eyebrow">Vorschau</p><h2>Messreihe läuft noch</h2><p className="lead">Diese Tafel zeigt nur echte Messwerte und bleibt leer, bis die MuJoCo-Reihe fertig ist. Die Läufe in der Mitte sind bereits echt aufgezeichnet.</p></>;
  return <C data={data}/>;
}
