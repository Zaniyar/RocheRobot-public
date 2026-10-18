# Öffentliche Fassung · 18.10.2026

## Umfang und Herkunft

Diese Fassung wurde aus einer ausdrücklichen Dateiauswahl erzeugt, mit neuer Git-Historie. Enthalten: browserlokale G1-Policy-Demo, zugehörige Quellen und Drittkomponenten mit Lizenzhinweisen, ausgewählter Simulations-/Prüfcode sowie neu verfasste öffentliche Dokumentation.

Nicht übernommen: Originalkommunikation, Chat-/Mail-Auszüge und daraus abgeleitete Personenprofile, ursprüngliche Projekt-/Übergabeprotokolle, interne Präsentationen, private CAD-Dateien, historische Fassungen, Laufzeitberichte, persönliche Server-/SSH-Konfiguration oder Anmeldedaten. Die alte History bleibt im privaten Entwicklungsarchiv.

Einige Simulationsskripte verwenden generische Beispielpfade und eigene Objektdateien als Voraussetzung. Diese Referenzen sind keine sofort startfähige Installation für andere Geräte. Der öffentliche Einstieg verweist für Quest auf das separat konfigurierte Teleop-Paket.

## Prüfung

- Browser-Demo mit festgelegten npm-Versionen erfolgreich neu gebaut; Lockfile enthalten.
- Python-Referenzdateien syntaktisch geprüft, ohne Isaac zu starten.
- Desktop-Chrome: Übersicht und Policy-Demo geladen; integrierter 12-s-Test mit 600 Policy-Schritten bestanden. Minimale Basishöhe 0.6184 m, Kriterium > 0.45 m. Das ist ein einzelner Funktionslauf, kein umfassender Stabilitätsbenchmark.
- Dateiauswahl gegen bekannte private Kontakte, Telefonnummern, Backend-Adressen und Laufzeitgeheimnisse geprüft; keine Treffer.
- Öffentliche Oberfläche enthält neu verfasste technische Texte statt der privaten Teamplanung.
- Secret-Scan der tatsächlichen Veröffentlichungsdateien und neue Git-Historie vor Push geprüft.

## Grenzen

Ein Muster-/Wertevergleich ist keine absolute Sicherheitsgarantie. Die Veröffentlichung des Codes gewährt keinen Zugriff auf eine bestehende Simulation. Eigene Instanzen benötigen eigene Zugänge und Tests. Robotik-/Cloud-Laufzeit, Training und reale Hardware wurden durch diese Exportprüfung nicht erneut validiert.

Die Browser-Demo verwendet öffentlich bezogene Drittmodelle. Die Datei `Projectboard/dist/policy/NOTICE.txt` enthält deren Herkunft und den noch offenen Hinweis zu den NVIDIA-Modellbedingungen; die BSD-Lizenz des Isaac-Lab-Codes ist nicht automatisch eine Lizenz für alle Modellgewichte.
