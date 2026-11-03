# Sim-to-Real-Messungen für den Griff

Misst in `Simulation/mujoco-scene`, wie sanft der Griff ist und welche Fehler er verträgt. Die Szene bleibt unverändert. Kein Training, keine Kamera, keine Hardware.

- `gentle_expert.py`: sanfter Griff. Vorab berechnete Gelenktrajektorie, konstante Handorientierung, Min-Jerk.
- `measure.py`: Vergleich mit dem alten Skript und Störungsreihen. Der Planer sieht die Störung nicht. Ergebnis: `results.json`.
- `collect_gentle.py` und `dof_profiles.json`: Datensammlung nach Bewegungsprofil; nicht ausführbare Profile werden abgelehnt.
- `export_dashboard.py` und `runs.json`: Szene, aufgezeichnete Läufe und Messwerte für `Projectboard/method-lab`.

## Wiederholen

```powershell
..\mujoco-scene\.venv\Scripts\python.exe measure.py --episodes 40 --compare 200 --seed0 7000 --workers 14
..\mujoco-scene\.venv\Scripts\python.exe export_dashboard.py
```

Rechenzeit der Reihe vom 2.11.2026: rund 17 Minuten. Die erste Reihe ohne Selbstkollision liegt als `history/results-2026-11-02-ohne-selbstkollision_unkorrekt.json` vor. Vergleich auf Seeds 7000–7199, Störungen auf planbaren Seeds ab 12000. Entwickelt wurde auf den Seeds 2000–2027 und 3000–3119.

## Erfolgskriterien

- `placed`: Kit in der Box, am Ende unter 10° Neigung und keine Selbstkollision. `kit_in_box()` aus `roche_env.py` allein zählt auch ein liegendes Kit.
- `gentle`: zusätzlich während des Tragens immer unter 5°. Die 5° sind eine Arbeitsannahme, kein Roche-Wert.

## Grenzen

Becken in der Szene fixiert; Schwanken ist als kinematisch bewegte Basis nachgestellt, die Amplitude am echten G1 ist unbekannt. Regler, Reibung und Griffkraft sind unkalibriert. Der Griff ist im Modell so stark, dass Reibung, Masse und Schwerpunkt fast nichts ändern; das ist keine Entwarnung. Konstante Latenz schadet beim Abspielen ohne Rückkopplung nicht; für Teleoperation und Policies gilt das nicht. Über etwa 200 mm/s begrenzt die Gelenkrate, schnellere Bahnen wurden also nicht wirklich getestet. Schwappen ist ein nachgerechneter Schwinger mit angenommener Geometrie (3,5 Hz), nur zum Vergleichen. Die Szene selbst kennt keine Selbstkollision: `selfcheck.py` prüft Arm gegen Rumpf, Kopf, Becken, Beine und anderen Arm auf konvexen Hüllen der sichtbaren Meshes, `exact_mesh_check.py` gegen die exakten Netze als Stichprobe. Das Kit in der Hand wird nicht gegen den Körper geprüft. Es wurde jeweils nur eine Grösse gestört.

## Bewegungsprofile mit Taille und Balance (3.11.2026)

`build_variants.py` erzeugt `scenes/waist.xml` und `scenes/floating.xml`, `mujoco-scene/scene.xml` bleibt unverändert. Seeds 7000–7199, zusätzliche Fehlerbedingung: über 5 N Kontakt zwischen Roboter und Tisch oder Box (`world_contact`).

- `waist_lab.py`, Becken fest, Taille stellt sich vor dem Griff ein: 200 von 200 sanft abgelegt, 42 davon nur dank Taille. Kein Tischkontakt, keine Selbstkollision auf Hüllen. Exakte Netzprobe für diese Haltungen noch nicht gelaufen. Ob der eigene G1 alle Taillengelenke frei hat, ist unbestätigt.
- `balance_env.py`, `floating_lab.py`, Becken frei, Unitrees Wholebody-Dex1-Laufpolicy per onnxruntime (nicht im Repo, Pfad `ROCHE_WALK_POLICY`). Mit Handausgleich über die Armjacobi: 127 abgelegt, 100 sanft, 48 verweigert, 7 Tischkontakt, 4 Selbstkollision, 0 Stürze; Körper bewegt sich dabei rund 38 mm. Ohne Ausgleich: 4 abgelegt, 1 sanft. Das ist Sim-zu-Sim mit idealer Armvorsteuerung und kein Nachweis am Roboter. Der Arm startet schon in Heimhaltung, weil Anheben nahe am Tisch die Platte streift oder den Roboter wegtreibt.
- Gehen: frei im Raum funktioniert es ab etwa .3 m/s vorwärts und .5 m/s rückwärts und seitwärts, mit Drift; Drehen auf der Stelle kaum (10,9° statt 12 rad bei 1,2 rad/s über 10 s). Herantreten und Greifen scheitert: Mit angehobenem Arm stoppt der Roboter nicht und drückt mit den Hüften gegen den Tisch, auch mit früherem Stoppbefehl. `collect_gentle.py` lehnt dieses Profil deshalb ab.

Die Serie vor der Tischkontakt-Prüfung ist `_unkorrekt` (Roboter stützte sich mit rund 1400 N am Tisch ab): `history/results_floating-2026-11-03-tischkontakt_unkorrekt.json`.

## Eigene Szene aus dem Dashboard

`simulate_config.py` rechnet Tisch-, Box- und Objektmasse aus dem Panel „Szene“ in MuJoCo nach (Becken fest, Taille frei, 40 Startlagen). Der lokale Server `serve.mjs` startet das; Fremdseiten werden abgewiesen. Zusatzobjekte sind Zylinder als feste Hindernisse. Der Griff zählt nur, wenn das Kit auf dem Boxboden steht. Gegenproben: Holder über der Kit-Zone ergibt 0 von 14. Die Taille darf nach vorn neigen, solange der Tisch nicht berührt wird; für die 200 Standard-Startlagen reicht Drehen allein.

## Handkameras

Im Panel „Roboter“ schaltbar. Ohne Handkameras speichert `collect_gentle.py` nur die Kopfkamera (`wrist_cameras: false` im Profil oder `--no-wrist-cameras`) und blendet das Gehäuse auch im Kopfbild aus. Jede Episode vermerkt das in den Attributen `wrist_cameras` und `cameras`. Lage und Form der Kamera samt Halter (`wrist_camera` in `build_scene.py`) sind Annahmen und am echten Roboter nachzumessen.
