# Ergebnisbericht — Aufgabe 1b: Smart-Home-Demonstrator

Heterogeneous Computing, Sommersemester 2026 · Übungsblatt 1, Aufgabe 1b (Software-Projekt)

## 1. Kontext

Aufgabe 1b besteht aus zwei Teilen. Der **Recherche- und Anforderungsteil** ist im
Bericht [`../HC_1.pdf`](../HC_1.pdf) dokumentiert: dort werden bestehende
Smart-Home-Architekturen, Plattformen, Kommunikationsmodelle und Protokolle
(Matter, Thread, Zigbee, Z-Wave, MQTT), Cloud-/Edge-Ansätze und Interoperabilität
untersucht und daraus **23 Anforderungen (A-01…A-23)** entlang der
Qualitätsmerkmale Verteilung, Skalierbarkeit, Fehlertoleranz, Robustheit, lose
Kopplung, Heterogenität und Erweiterbarkeit abgeleitet — ergänzt um die beiden
Schwerpunkte *persistente Geräteregistrierung* und *On-Device-/agentische KI*.

Dieser Bericht dokumentiert den **prototypischen Demonstrator**, der die
wesentlichen Kernelemente dieser Architektur umsetzt. Er besteht aus mehreren
eigenständigen, über MQTT kommunizierenden Komponenten; physische Sensoren und
Aktoren sind als realistisch verhaltende Software-Mockups simuliert und
interagieren über definierte Schnittstellen mit der Infrastruktur.

## 2. Architekturüberblick

Der Demonstrator setzt das Referenzbild aus HC_1.pdf, Kapitel 5, konkret um:

```
                      ┌─────────────────────────────────────────────┐
                      │             MQTT-Broker (amqtt)              │  Pub/Sub-Backbone
                      │               127.0.0.1:1883                 │  (lose Kopplung)
                      └────▲─────────▲──────────▲──────────▲─────────┘
   retained: descriptor /  │         │          │          │
   state / availability /  │         │          │          │
   announce                │         │          │          │
   ┌─────────────────┐ ┌───┴────┐ ┌──┴───────┐ ┌┴────────┐ ┌┴─────────────┐
   │ Geräte (sim.)   │ │Registry│ │Controller│ │ Agent   │ │  Dashboard   │
   │ Licht·Thermostat│ │ SQLite │ │ Regel-   │ │ Ollama  │ │ FastAPI + WS │
   │ Bewegung·Schloss│ │ Source │ │ Engine + │ │ ·Regeln │ │ Live-Browser │
   │ Steckdose·Zigbee│ │of Truth│ │ Failover │ │ +Guard  │ │              │
   └─────────────────┘ └────────┘ └──────────┘ └─────────┘ └──────────────┘
```

Jede Komponente ist ein **eigenständiger Betriebssystem-Prozess** ohne zentralen
Single Point of Control. Die Kommunikation erfolgt ausschließlich
ereignisgesteuert über den Broker und ein gemeinsames, versioniertes
**semantisches Datenmodell** (Matter-Cluster-inspiriert: `type` +
`capabilities` + flache `attrs`-Map).

**Kernkomponenten:**

- **Geräte-Simulatoren** (`devices/`): Licht, Thermostat (thermisches Modell),
  Bewegungsmelder (PIR + Lux mit Tag/Nacht-Zyklus), Türschloss, Mess-Steckdose.
  Jedes Gerät hat eine persistente Identität, meldet sich beim Verbinden an
  (retained), reagiert idempotent auf Befehle und nutzt MQTT Last-Will für
  Online/Offline-Status.
- **Zigbee-Bridge** (`devices/zigbee_bridge.py`): kapselt ein „Legacy"-Gerät mit
  Cluster-/Attribut-Schnittstelle (Level 0–254) und normalisiert es auf das
  gemeinsame Modell — Protokoll-Abstraktion für heterogene Geräte.
- **Registry** (`services/registry.py`): persistente Source of Truth (SQLite);
  erkennt zurückkehrende Geräte am Credential-Fingerprint und bindet sie **ohne
  Re-Pairing** neu ein.
- **Controller** (`services/controller.py`): local-first Regel-Engine mit
  automatisch entdeckten Regel-Plugins (`rules/`); Redundanz über
  Leader-Lease-Failover.
- **Agent** (`services/agent.py`): On-Device-Orchestrierung. Übersetzt
  natürlichsprachige Anfragen über ein lokales LLM (Ollama, Tool-Calling) oder
  einen deterministischen Regel-Fallback in Gerätebefehle — mit Guardrails und
  Audit-Trail.
- **Dashboard** (`dashboard/`): FastAPI + WebSocket; zeigt Gerätezustände,
  Registry-Inventar und Event-Log live und nimmt Sprachbefehle entgegen.

## 3. Umsetzung der Anforderungen (A-01…A-23)

Legende: ✅ vollständig umgesetzt · ◐ teilweise/konzeptionell (im Rahmen einer
Simulation; in Abschnitt 5 begründet).

| ID | Anforderung (Kurz) | Umsetzung im Demonstrator | Status |
|----|--------------------|---------------------------|:--:|
| A-01 | Dezentral, kein Single Point of Control | Jede Komponente eigener Prozess; nur über Broker gekoppelt | ✅ |
| A-02 | Verteilte/replizierte Zustandshaltung | Retained State auf dem Bus + persistente SQLite-Registry; echte Multi-Node-Replikation skizziert | ◐ |
| A-03 | Horizontale Skalierung über Pub/Sub | Gesamte Kommunikation über MQTT-Topics; Geräte additiv ohne Eingriff | ✅ |
| A-04 | Föderierte Topologie, Discovery, Adressierung | Service Discovery über retained `announce`/`descriptor`; eindeutige `device_id`-Adressierung | ✅ |
| A-05 | Selbstheilende Topologie, Redundanz | Redundante Controller mit Leader-Lease + automatischem Failover; Auto-Reconnect | ✅ |
| A-06 | Voller Lokalbetrieb bei Cloud-Ausfall | Komplett local-first, keine Cloud-Abhängigkeit; graceful degradation | ✅ |
| A-07 | Auto-Reconnect ohne Re-Pairing | paho Auto-Reconnect + persistente Identität + transparenter Re-Bind | ✅ |
| A-08 | Idempotenz, verlustfreie Wiederherstellung | Idempotentes `apply_command` + `command_id`-Dedupe; Restore aus retained State/SQLite | ✅ |
| A-09 | Deterministische Konfliktauflösung, Watchdogs | Leader verhindert Doppelausführung (kleinste id gewinnt); `last_seen`/Availability-Watchdog | ◐ |
| A-10 | Ereignisgesteuerte Kommunikation über Broker | Asynchrones Publish/Subscribe als einziger Kopplungsmechanismus | ✅ |
| A-11 | Standardisierte, versionierte Schnittstellen | Gemeinsames pydantic-Datenmodell mit `schema_version` als Vertrag | ✅ |
| A-12 | Protokoll-Abstraktion über Adapter/Bridges | Zigbee-Bridge normalisiert Cluster-Format auf das gemeinsame Modell | ✅ |
| A-13 | Einheitliches semantisches Geräte-/Dienstmodell | Einheitliches Modell + simulierte Digital Twins; Registry-Inventar | ✅ |
| A-14 | Modulare Plugin-Architektur, offene APIs | Auto-Discovery von Regel-Plugins und Geräteklassen — neue Funktion ohne Kernänderung | ✅ |
| A-15 | Sichere OTA-Updates, versionierte Schnittstellen | Versionierte Schnittstellen ✅; OTA-Mechanismus konzeptionell | ◐ |
| A-16 | Dauerhafte, lokale Identitäts-/Credential-Speicherung | `identity.py` persistiert `device_id` + Secret lokal (Factory-Reset = State löschen) | ✅ |
| A-17 | Repliziertes Register, Re-Auth ohne Re-Pairing | SQLite-Registry als Source of Truth; Re-Bind über Fingerprint, kein Neuanlernen | ✅ |
| A-18 | Robustes Session-Management mit Selbstreparatur | Stale/Offline-Sitzung wird erkannt und geheilt statt Reset zu erzwingen | ✅ |
| A-19 | Lokale Inferenz-Laufzeit, standardisierte Schnittstelle | Ollama-Backend (lokales LLM `llama3.1`, real betrieben & verifiziert) hinter `LLMBackend`-Abstraktion; tolerante Tool-Call-Extraktion (nativ **und** Text-Fallback) | ✅ |
| A-20 | Geregelter Modell-Lebenszyklus, OTA-Modellupdates | Modell konfigurierbar/austauschbar; echtes Modell-OTA konzeptionell | ◐ |
| A-21 | Orchestrierung agentischer KI, Kontext, Guardrails | Agent mit gemeinsamem Weltkontext, Tool-Whitelist, Guardrails, Audit | ✅ |
| A-22 | Zero-Trust, E2E-Verschlüsselung, attestiertes Onboarding | Fingerprint-Identitätsprüfung + Mismatch-Ablehnung + Aktions-Whitelist; TLS/Attestierung konzeptionell | ◐ |
| A-23 | Lokale Verarbeitung, Datenminimierung, Audit | Alles lokal, On-Device-LLM; durchgängiger Audit-/Event-Trail | ✅ |

## 4. Was die Demo zeigt

`python run.py scenario` führt reproduzierbar durch die Kernpunkte:

1. **Discovery & persistente Registrierung** — Geräte melden sich an, die
   Registry persistiert sie (SQLite) als Source of Truth.
2. **Local-first-Automation** — Bewegung im dunklen Raum schaltet lokal das Licht
   ein (Regel-Engine, ohne Cloud).
3. **On-Device-Agent** — die Anfrage „good night" wird in Gerätebefehle
   übersetzt (Licht aus, Tür verriegeln).
4. **Persistente Re-Registrierung** — ein Gerät „startet neu" und wird **ohne
   Re-Pairing** wieder eingebunden; kein Duplikat im Inventar.
5. **Fehlertoleranz** — der Broker fällt aus; Komponenten verbinden sich
   automatisch wieder, die Registry lädt ihr Inventar aus SQLite — nichts geht
   verloren.

`python run.py up` startet zusätzlich das Live-Dashboard (http://127.0.0.1:8000)
mit zehn Geräten in vier Räumen für die interaktive Vorführung.

## 5. Annahmen und Grenzen

- **Simulation statt Hardware:** Geräte sind Software-Mockups mit plausiblem
  Verhalten (thermisches Modell, Tag/Nacht-Lux, Energieprofile). Funk-Mesh
  (Thread/Zigbee-Routing) und NPU-Inferenz pro Gerät sind physische Aspekte und
  werden nicht real, sondern über die Architektur (Bridge, LLM-Abstraktion)
  abgebildet.
- **Konzeptionelle Punkte (◐):** echte Multi-Broker-Föderation und
  Zustandsreplikation (A-02/A-04), OTA für Firmware/Modelle (A-15/A-20) sowie
  TLS/E2E-Verschlüsselung und Geräteattestierung (A-22) sind als Schnittstelle
  bzw. Mechanismus vorgesehen, aber im Demo bewusst vereinfacht (anonymer lokaler
  Broker, Fingerprint als Identitätsnachweis).
- **On-Device-LLM real betrieben, mit Fallback:** der Agent wurde mit einem
  lokalen `llama3.1` (8B, über Ollama) verifiziert und erzeugt darüber echte
  Tool-Calls und Gerätebefehle. Läuft kein Ollama-Server, schaltet er automatisch
  auf den deterministischen Regel-Backend um — der Demonstrator bleibt jederzeit
  lauffähig. Da kleine Modelle Tool-Calls teils als JSON-Text statt über das
  native `tool_calls`-Feld ausgeben, werden beide Formen tolerant geparst, damit
  die Aktionen zuverlässig aufgelöst werden.
- **Stromverbrauch** wird annahmegemäß (vgl. HC_1.pdf) nicht betrachtet.

## 6. Architektur-Benchmark (Edge/Cloud/Hybrid)

Ergänzend zur Live-Demo erlaubt ein **Benchmark-Werkzeug** den quantitativen
Vergleich verschiedener **Architekturvarianten** entlang der in HC_1.pdf
diskutierten Cloud-/Edge-Dimension — also abhängig davon, *wo die KI-Inferenz
läuft*:

- **Edge / On-Device:** lokales, beschränktes Modell — keine Netz-Latenz, keine
  Cloud-Abhängigkeit, keine Datenausleitung, aber geringere Sprachabdeckung.
- **Cloud:** großes Modell im Rechenzentrum — höchste Trefferquote, aber
  Netz-Latenz, Datenausleitung und Totalausfall bei fehlender Verbindung.
- **Hybrid:** Cloud bei Erreichbarkeit, transparenter Fallback auf das
  On-Device-Modell im Ausfall (graceful degradation).

Eine feste Suite natürlichsprachiger Anfragen wird durch jede Variante geschickt
und über die **gleichen Guardrails** wie der Live-Agent aufgelöst
([`services/guardrails.py`](src/smarthome/services/guardrails.py)). Gemessen
werden **Latenz, Aktions-Korrektheit, Erfolgsrate über das Testset** und
**Robustheit bei Cloud-Ausfall**. Ergebnis (reproduzierbar, Seed-gesteuert): die
Cloud-Variante erzielt die höchste Erfolgsrate, fällt im Ausfall aber auf 0 %
Verfügbarkeit; Edge bleibt bei 100 % Verfügbarkeit, ist aber schwächer; Hybrid
behält die Cloud-Qualität und degradiert im Ausfall auf das Edge-Niveau, ohne die
Verfügbarkeit zu verlieren. Das untermauert quantitativ den local-first-Ansatz und
die Anforderungen A-06/A-19/A-20.

Ergebnis bei der Standardwelt (10 Geräte, 4 Räume, Seed 42; reproduzierbar):

| Architektur | Erfolg (normal) | Erfolg (Ausfall) | Verfügbar (Ausfall) | Ø Latenz | Daten verlassen Haus |
|-------------|:--:|:--:|:--:|:--:|:--:|
| Edge / On-Device | 64,7 % | 64,7 % | 100 % | 73,3 ms | nein |
| Cloud | 94,1 % | 0 % | 0 % | 152,1 ms | ja |
| Hybrid (Cloud + Edge-Fallback) | 94,1 % | 64,7 % | 100 % | 152,1 ms | ja |

Lesart: Cloud ist am fähigsten, fällt im Ausfall aber komplett aus und leitet
Daten aus; Edge ist privat und immer verfügbar, aber schwächer; Hybrid vereint
hohe Trefferquote mit voller Verfügbarkeit (Degradation auf Edge-Niveau im
Ausfall). Die Latenz wächst mit der Gerätezahl (hier 10 Geräte).

Die simulierte **Hausgröße ist einstellbar** (Anzahl Räume und Geräte). Die
Erfolgsrate bleibt dabei bewusst unabhängig von der Größe — der Vergleich misst
Modell-*Fähigkeit*, nicht Hausgröße —, während die **Latenz mit der Gerätezahl
wächst**.

**Quergleich mit einem echten lokalen Modell:** Mit `llama3.1` (8B) als
Agent-Backend lässt sich die im Benchmark modellierte Edge-Schwäche real beobachten:
auf die Frage „is the front door locked?" antwortet das kleine Modell nicht, sondern
verriegelt die Tür fälschlich (Befehl statt Frage) — genau das Verhalten, das der
Benchmark der beschränkten On-Device-Klasse zuschreibt, während das fähigere
(simulierte) Cloud-Modell die Frage korrekt nur beantwortet. Das fähigere Modell
lässt sich auch in die „Cloud"-Rolle einsetzen (`SH_BENCH_CLOUD_MODEL`).

Aufruf: Dashboard-Tab *📊 Architecture benchmark* (http://127.0.0.1:8000/benchmark)
oder `python run.py benchmark` (HTML-Report + Konsolentabelle). Die Latenz ist ein
transparentes, simuliertes Modell; das voreingestellte „Cloud"-Modell ist ein
simuliertes, fähigeres Modell — konsistent mit dem Simulationscharakter des
Demonstrators (Abschnitt 5).

## 7. Technologie & Ausführung

Python 3.11; paho-mqtt, amqtt (Broker), pydantic v2, FastAPI/uvicorn, ollama
(lokales LLM `llama3.1`), typer, rich; getestet mit pytest (48 Tests). Aufbau,
Start und interaktive Demos sind in [`README.md`](README.md) beschrieben.
