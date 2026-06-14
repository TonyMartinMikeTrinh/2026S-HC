# 2026S-HC
Abgaben zur Vorlesung "Heterogeneous Computing" im Sommer 2026.

## Aufgabe 1b — Software-Projekt: Smart-Home-Demonstrator

- **Recherche & Anforderungen:** [`HC_1.pdf`](HC_1.pdf) — Smart-Home-Architekturen,
  Protokolle, Cloud/Edge, Interoperabilität und 23 abgeleitete Anforderungen (A-01…A-23).
- **Prototypischer Demonstrator:** [`demonstrator/`](demonstrator/) — eine local-first,
  ereignisgesteuerte Smart-Home-Infrastruktur aus mehreren über MQTT kommunizierenden
  Komponenten (Broker, simulierte Geräte, persistente Registry, Automations-Controller,
  On-Device-KI-Agent, Live-Dashboard) — inklusive eines **Architektur-Benchmarks**
  (Edge/Cloud/Hybrid), der Latenz, Korrektheit, Erfolgsrate und Ausfall-Robustheit
  je nach gewählter Architektur visualisiert (Dashboard-Tab oder
  `python run.py benchmark`). Siehe
  [`demonstrator/README.md`](demonstrator/README.md) zum Ausführen und
  [`demonstrator/Ergebnisbericht.md`](demonstrator/Ergebnisbericht.md) für den Ergebnisbericht.

Schnellstart: `cd demonstrator && pip install -e . && python run.py up` → http://127.0.0.1:8000
