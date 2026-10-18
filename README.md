# RocheRobot — öffentlicher Technikstand

## Robotics meets XR — réalité suisse GmbH

**Robotik erlebbar machen. Mit AR, VR und Simulation.**

Roboter aus der Simulation räumlich erleben, intuitiv steuern und neue Anwendungen gemeinsam ausprobieren. Ein Projekt von **réalité suisse GmbH**.

**Ideen für Robotik und XR? → [swissmade.xyz](https://swissmade.xyz)**

---

Öffentliche, gezielt zusammengestellte Fassung der Robotik-Implementierung. Enthalten sind die browserlokale G1-Laufdemo, Quellcode für die Simulation und technische Integrationshinweise. **Keine privaten Chats/E-Mails, Teilnehmerprofile, internen Projektunterlagen, Zugangsdaten oder Verbindungen zu einer persönlichen Simulation.** Die Git-Historie beginnt mit dieser bereinigten Fassung.

## Zwei verschiedene Anwendungen

| Anwendung | Physik / Inferenz | Einstieg |
|---|---|---|
| G1 im Browser bewegen und per Klick schubsen | MuJoCo-WASM + ONNX Runtime Web, vollständig im Browser | `Projectboard/dist/index.html` über lokalen HTTP-Server |
| Quest-VR-Teleoperation mit Armen und optional Laufen | Eigene Isaac-Sim-Instanz, IK-Brücke, optionale Beinpolicy | [Separates Teleop-Repository](https://github.com/Zaniyar/quest-isaac-teleop) |

Die Browser-Laufdemo verwendet 123 Beobachtungen und 37 Aktionen. Die Quest-Dex1-Laufanbindung verwendet 910 Eingänge und zwölf Beinaktionen. **Diese Modelle und Roboterkonfigurationen sind nicht austauschbar.** Keine der beiden Anwendungen ist bereits ein autonomes VLA für Objekttransport.

## Webapp lokal starten

Im Repository-Hauptordner, mit Python 3:

```sh
python -m http.server 8080 --bind 127.0.0.1 --directory Projectboard/dist
```

Dann `http://127.0.0.1:8080` öffnen. Für eine statische Website den Inhalt von `Projectboard/dist/` unter einer gemeinsamen Origin ausliefern. Kein SSH, keine Cloud-GPU und kein Isaac-Backend sind für die Browser-Demo nötig. Bei geringer Browserleistung kann die Simulation langsamer laufen.

Die öffentliche Webapp enthält eine eigene technische Übersicht. Die private Teamplanung und ihre aus Originalkommunikation abgeleiteten Texte werden nicht mitgeliefert.

## Browser-Code ändern

```sh
cd Projectboard/three
npm ci --ignore-scripts
npm run build
```

Quellen: `policy-browser.js` und `policy-worker.js`. Der Build übernimmt lokale WASM-Dateien. Robotermodell, Meshes, Konfiguration und Quellen-/Lizenzhinweise liegen unter `Projectboard/dist/policy/`. Die Modelldistribution hat eigene Nutzungsbedingungen; `NOTICE.txt` lesen. Kein Training erforderlich.

Für eine bestehende React-Three-Fiber-App: [R3F-INTEGRATION-PROMPT.txt](Projectboard/R3F-INTEGRATION-PROMPT.txt). Vorhandenen Canvas nutzen; MuJoCo läuft im Worker. Klick-Schubsen ist eine physikalische Kraft am getroffenen Körperteil entlang des Kamera-Maus-Strahls. Pause, Reset, Richtungssteuerung und Worker-Cleanup erhalten.

## Isaac-Simulation / Quest

Der Ordner `Simulation/` enthält Referenzcode, einschließlich einer Szene mit wechselbarer Basisfixierung und gleichzeitiger Armteleoperation. Er ist **kein universeller Installer**. Standardpfade wie `D:/RobotRuntime` und `/opt/robot` sind generische Platzhalter für die eigene Installation. Für die Quest-Szenen kann `ROBOT_RUNTIME` gesetzt werden. Die Szenen erwarten einen eigenen Unitree-Checkout und ein eigenes Objekt unter `ObjectAssets/example_object.usd`; kein Firmen-CAD wird mitgeliefert.

Die passenden SDKs, Robotermodelle und Policy-Gewichte separat beziehen. G1-Dex1-Szene, Joint-Mapping, Physiktakt und Verankerung prüfen, bevor der Laufmodus freigegeben wird. Die Referenzadapter verwenden interne Loopback-Ports 18768/18769, passend zum separaten Teleop-Paket. Ursprüngliche LAN-/SSH-/Server-Starter werden nicht veröffentlicht.

Setup, Koordinaten, Steuerprotokoll, eigenes HTTPS/WSS und Codex-Auftrag: [quest-isaac-teleop](https://github.com/Zaniyar/quest-isaac-teleop).

## Entwicklungsstand

1. **Vorhanden:** browserlokaler Physik-/Policy-Regelkreis, G1-Steuerung, Pause/Reset und Klick-Schubsen.
2. **Vorhanden als Integrationscode:** räumliche Quest-Teleoperation, Arm-IK, wechselbare Fixierung und Laufanbindung für eine eigene Isaac-Szene.
3. **Nächster fachlicher Schritt:** eine erreichbare Objekt-zu-Behälter-Aufgabe mit klaren Erfolgskriterien festlegen, erfolgreiche Demonstrationen aufzeichnen und anschließend einfache Greifskills, ACT und passende VLA-Kandidaten unter denselben Bedingungen vergleichen.
4. **Nicht behauptet:** erfolgreicher autonomer Objekttransport, abgeschlossenes Fine-Tuning, geprüfte reale Hardware oder eine fertige Cloud-Installation für Dritte.

Eine mögliche Auswertung misst vollständige Aufgabe, Startlage, Loslassen im Ziel, Stabilität, Zeit und menschliche Eingriffe. Eine laufende Gehpolicy ist dafür erst ein technischer Baustein.

## Öffentlichkeit und Prüfgrenzen

Nur ausdrücklich ausgewählte Technikdateien wurden übernommen; keine alte Git-Historie. Die Veröffentlichung verwendet keine persönlichen Backend-Adressen. Der vorhandene private Entwicklungsstand bleibt separat erhalten.

Quellcode-/Asset-Prüfung, Syntaxcheck und lokaler Browser-Test sind dokumentiert in [PUBLICATION.md](PUBLICATION.md). Tests einer ursprünglichen Entwicklungsinstallation sind kein Nachweis für eine andere Isaac-/Cloud-Umgebung. Lizenztexte der mitgelieferten Drittkomponenten bleiben erhalten; für den eigenen Integrationscode ist noch keine allgemeine Open-Source-Lizenz festgelegt. Das Logo ist kein frei verwendbares Markenzeichen.
