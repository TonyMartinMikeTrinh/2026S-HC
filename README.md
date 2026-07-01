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

## Übungsblatt 2 — SIMT & Speicherzugriff in OpenCL

- **OpenCL-Lösung:** [`uebung2/`](uebung2/) — Aufgabe 1 (SIMT-Ausführungsmodell &
  Warp-Divergenz) und Aufgabe 2 (Speicher: effektive Bandbreite über
  coalesced/strided/gather-Zugriffsmuster und Latency-Hiding über die Occupancy),
  umgesetzt mit OpenCL-C-Kernels und `pyopencl`-Host, gemessen auf einer Intel-GPU.
  Terminologie nach Kaeli et al., *Heterogeneous Computing with OpenCL* (2011).
  Siehe [`uebung2/README.md`](uebung2/README.md) zum Ausführen und
  [`uebung2/Ergebnisbericht.md`](uebung2/Ergebnisbericht.md) für den Ergebnisbericht.

Schnellstart: `cd uebung2 && pip install -r requirements.txt && python aufgabe1_simt_divergenz.py`
