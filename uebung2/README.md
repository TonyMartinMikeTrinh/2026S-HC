# Übungsblatt 2 — SIMT & Speicherzugriff in OpenCL

Lösung zu Übungsblatt 2 (Heterogeneous Computing, SS 2026), Aufgaben 1 und 2, in
**OpenCL** (OpenCL-C-Kernel + `pyopencl`-Host). Terminologie nach Kaeli, Mistry,
Schaa, Zhang: *Heterogeneous Computing with OpenCL* (2011).

- **Aufgabe 1 — SIMT-Ausführungsmodell & Warp-Divergenz:** compute-bound
  ALU-Kernel; Durchsatz-Skalierung über `n` (wann läuft die GPU „warm") und
  systematischer Warp-Divergenz-Sweep (bis ~16× Einbruch).
- **Aufgabe 2 — Speicher: Latenz & Bandbreite:** Streaming-Kernel `b=a·c`;
  effektive Bandbreite für coalesced / strided / gather (bis ~20× Unterschied) und
  Latency-Hiding über die Occupancy (residente Wavefronts).

👉 **Ergebnisse, Diagramme und Diskussion: [`Ergebnisbericht.md`](Ergebnisbericht.md).**

## Ausführen

Voraussetzung: OpenCL-fähige GPU mit installiertem ICD (der Loader `OpenCL.dll`
liegt unter Windows in `System32`).

```powershell
cd "uebung2"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python aufgabe1_simt_divergenz.py       # Aufgabe 1
python aufgabe2_speicher_bandbreite.py  # Aufgabe 2
python plots.py                         # Diagramme aus results/*.csv erzeugen
```

CSV-Rohdaten und PNG-Diagramme werden in `results/` abgelegt.

## Aufbau

| Datei | Inhalt |
|-------|--------|
| `kernels/aufgabe1.cl` | Kernel: `alu_mix`, `divergence_varlen`, `divergence_skew` |
| `kernels/aufgabe2.cl` | Kernel: `stream_coalesced/_strided/_gather/_gridstride` |
| `aufgabe1_simt_divergenz.py` | Host für Aufgabe 1 |
| `aufgabe2_speicher_bandbreite.py` | Host für Aufgabe 2 |
| `common.py` | OpenCL-Setup, Profiling-Timing, Device-Query, CSV |
| `plots.py` | Diagramme aus den CSV-Ergebnissen |
| `Ergebnisbericht.md` | Ergebnisbericht mit Messungen und Literaturbezug |
