# Method Lab

Dashboard zur Aufgabe „Kit greifen, aufrecht tragen, in die Box stellen“. Links Methoden, rechts Themen, in der Mitte React Three Fiber. Der Browser rechnet keine Physik, er spielt aufgezeichnete MuJoCo-Läufe ab. Methoden ohne eigene Ausführung sind in der Oberfläche so gekennzeichnet.

```powershell
powershell -ExecutionPolicy Bypass -File .\Start-Demo.ps1
```

Danach http://127.0.0.1:8774/. Abhängigkeiten: `npm ci` in diesem Ordner; auf dem Projekt-PC liegen sie ausserhalb von Syncthing unter `D:/RocheRuntime/MethodLabModules` (anders: `ROCHE_METHODLAB_MODULES`). Daten erzeugt `Simulation/sim2real-lab/export_dashboard.py` nach `public/data`.

Inhalte stehen in `src/content.js`, Zahlen kommen aus `data.json`. Geprüft in Chrome auf dem RTX-5090-PC: alle Datenquellen geladen, keine Konsolenfehler, ein Bild samt Effekten rund 4 ms bei 3840×1823 per manuell ausgelöstem Rendern. In einem verdeckten Fenster drosselt Chrome auf etwa 1 Bild/s. Die flüssige Wiedergabe im Vordergrund und die schmale Ansicht sind noch nicht geprüft. Path-Tracing: three-gpu-pathtracer, Bewegungsprofile: `Simulation/sim2real-lab/dof_profiles.json`.

Materialien: `assets-src/` enthält das Laborpanorama und Boden-, Tisch-, Metall- und Plastiktextur, erzeugt mit ChatGPT am 2.11.2026. Der frühere lokal berechnete Boden bleibt als `tex_floor_lokal-platzhalter.png` erhalten. `build_textures.py` erzeugt daraus `public/textures`. Normal- und Rauheitskarten sind aus der Helligkeit abgeleitet, die Lichtstärke des Panoramas ist geschätzt, kein gemessenes HDR.

## Ohne schnelle GPU: MuJoCo auf dem ZHAW-Cluster rechnen

Das Dashboard läuft weiter in deinem Browser, die Rechnung auf dem Cluster. Eine SSH-Verbindung (Tunnel) verbindet beides.

| Was | Wo es läuft | Was es braucht |
| --- | --- | --- |
| 3D-Ansicht im Dashboard | dein Laptop, auch mit Tunnel | Grafik des Laptops. Ruckelt es, im Panel „Render“ Effekte und Path-Tracing ausschalten. Der Cluster hilft hier nicht. |
| „In MuJoCo berechnen“ (Panel „Szene“), Datensammlung ohne Bilder | Cluster | nur CPU. MuJoCo rechnet Physik nicht auf der GPU. |
| Datensammlung mit Kamerabildern | Cluster | GPU empfohlen |

Stand: Alle Befehle auf dem Server sind am 3.11.2026 in einem frischen Klon unter Linux (WSL) durchgelaufen, auch der Rechenknopf über die Server-Schnittstelle (40 Startlagen in 32 s auf 16 Kernen). **Auf dem Cluster selbst und durch den Tunnel ist es noch nicht getestet**, weil von unserem Testrechner kein Clusterzugang bestand. Die Cluster-Befehle stammen aus der [offiziellen Anleitung](https://github.zhaw.ch/pages/SoE-compute-cluster/cluster_doc_page/pages/getting_started.html).

### Einmalig einrichten

1. Zugang beantragen: Mail an hpc.engineering@zhaw.ch. Ausserhalb der ZHAW vermutlich VPN nötig (von aussen liess sich `dallas.zhaw.ch` nicht auflösen).
2. Anmelden und eine Arbeits-Shell holen. Auf dem Login-Rechner selbst darf nicht gerechnet werden. `givemeashell` reserviert 4 CPU-Kerne.

   ```bash
   ssh <zhaw-user>@dallas.zhaw.ch
   showmyaccounts
   showcustomports
   givemeashell
   hostname
   ```

   `showcustomports` nennt deine vier Ports, im Folgenden `<port>`. `hostname` nennt den Arbeitsrechner, im Folgenden `<worker>`.
3. Python laden (`module av` zeigt die Versionen, nötig ist 3.10 oder neuer), Projekt holen und einrichten. Die Anleitung des Clusters nennt nur Python- und CUDA-Module, deshalb kommt Node als Archiv in den eigenen Ordner:

   ```bash
   module load python/<version>
   git clone https://github.com/Zaniyar/RocheRobot-public.git
   cd RocheRobot-public/Simulation/mujoco-scene
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cd ../sim2real-lab
   ../mujoco-scene/.venv/bin/python export_dashboard.py
   cd ../../Projectboard/method-lab
   curl -L https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz | tar xJ -C ~
   export PATH=~/node-v22.11.0-linux-x64/bin:$PATH
   npm ci
   node build.mjs
   ```


### Jedes Mal starten

Auf dem Cluster, in der Arbeits-Shell (`givemeashell`, dann `module load` und `export PATH` wie oben):

```bash
cd ~/RocheRobot-public/Projectboard/method-lab
node serve.mjs <port>
```

Auf dem Laptop, in einem zweiten Terminal. Es bleibt ohne Ausgabe offen, solange der Tunnel steht:

```bash
ssh -N -L <port>:127.0.0.1:<port> <zhaw-user>@<worker>.zhaw.ch
```

Dann im Browser `http://127.0.0.1:<port>/` öffnen. „In MuJoCo berechnen“ (Panel „Szene“) läuft nun auf dem Cluster.

Stolperstellen:

- Genau `127.0.0.1` und auf beiden Seiten denselben Port verwenden. Bei `localhost` oder einem anderen Port weist der Server den Rechenknopf mit Fehler 403 ab; das ist sein Schutz gegen fremde Webseiten.
- Der Server antwortet nur auf dem Arbeitsrechner selbst. Den Tunnel also direkt zu `<worker>` öffnen, nicht zu `dallas`. Das klappt nur, solange dort dein Job läuft.
- Endet der Job, sind Server und Tunnel weg. Dann neu `givemeashell` starten; der Arbeitsrechner kann ein anderer sein.

### Daten sammeln

Ohne Bilder genügt die Arbeits-Shell oben (2 Episoden in rund 8 s):

```bash
cd ~/RocheRobot-public/Simulation/sim2real-lab
../mujoco-scene/.venv/bin/python collect_gentle.py --profile right_arm --episodes 50 --out data/run01
```

Mit Bildern einen GPU-Job holen und MuJoCo ohne Bildschirm rendern lassen. Grössere Läufe gehören als Batch-Job (`sbatch`) auf den Cluster:

```bash
srun --gres=gpu:1 --partition=<partition> --account=<slurm-account> --time=200 --pty bash
MUJOCO_GL=egl ../mujoco-scene/.venv/bin/python collect_gentle.py --profile right_arm --episodes 50 --out data/run01 --images
```

Rund 44 MB pro Episode. Im WSL-Test dauerte eine Episode rund 6,5 Minuten, einschliesslich zweier verworfener Startlagen; EGL meldete dort beim Beenden einen Fehler. Wie schnell es auf den Cluster-GPUs geht, ist nicht gemessen. Balance-Profile brauchen zusätzlich `onnxruntime` und die Laufpolicy von Unitree (`ROCHE_WALK_POLICY`), die nicht im Repository liegt.

Ergebnisse auf den Laptop holen:

```bash
scp -r <zhaw-user>@dallas.zhaw.ch:RocheRobot-public/Simulation/sim2real-lab/data/run01 .
```
