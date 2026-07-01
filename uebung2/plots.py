"""Erzeugt die Diagramme fuer den Ergebnisbericht aus den CSV-Dateien in
results/.  Aufruf nach den beiden Benchmarks:  python plots.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent / "results"


def read(name):
    with (RESULTS / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plot_scaling():
    rows = read("a1_scaling.csv")
    n = [int(r["n"]) for r in rows]
    g = [float(r["gflops"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.semilogx(n, g, "o-", base=2)
    ax.set_xlabel("Problemgroesse n (work-items, log2)")
    ax.set_ylabel("Durchsatz [GFLOP/s]")
    ax.set_title("Aufgabe 1a: Durchsatz-Skalierung des ALU-Kernels (Intel UHD Graphics)")
    ax.grid(True, which="both", ls=":")
    ax.axhline(max(g), color="gray", ls="--", lw=0.8, label=f"Peak ~ {max(g):.0f} GFLOP/s")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "a1_scaling.png", dpi=120)


def plot_divergence():
    vl = read("a1_divergence_varlen.csv")
    sk = read("a1_divergence_skew.csv")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot([int(r["D"]) for r in vl], [float(r["slowdown"]) for r in vl],
            "o-", label="variable Schleifenlaenge (mehr Arbeit)")
    # Divergenzgrad der skew-Variante = S/active (konstante Nutzarbeit)
    S = int(sk[0]["active_lanes"])
    ax.plot([S / int(r["active_lanes"]) for r in sk], [float(r["slowdown"]) for r in sk],
            "s-", label="konstante Nutzarbeit (reine Serialisierung)")
    ax.set_xlabel("Divergenzgrad (distinkte Pfade je Warp)")
    ax.set_ylabel("Slowdown [x]")
    ax.set_title("Aufgabe 1b: Performanz-Einbruch durch Warp-Divergenz")
    ax.grid(True, ls=":")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "a1_divergence.png", dpi=120)


def plot_patterns():
    rows = read("a2_patterns.csv")
    labels = [r["muster"] for r in rows]
    bw = [float(r["gbps"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#2a7" if "coalesced" in l else ("#e63" if "gather" in l else "#38c") for l in labels]
    ax.bar(range(len(bw)), bw, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("effektive Bandbreite [GB/s]")
    ax.set_title("Aufgabe 2a: Zugriffsmuster vs. effektive Bandbreite")
    ax.grid(True, axis="y", ls=":")
    fig.tight_layout()
    fig.savefig(RESULTS / "a2_patterns.png", dpi=120)


def plot_occupancy():
    rows = read("a2_occupancy.csv")
    w = [int(r["resident_warps"]) for r in rows]
    bw = [float(r["gbps"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.semilogx(w, bw, "o-", base=2)
    ax.set_xlabel("gleichzeitig residente Wavefronts (log2)")
    ax.set_ylabel("effektive Bandbreite [GB/s]")
    ax.set_title("Aufgabe 2b: Latenz verstecken ueber Occupancy")
    ax.grid(True, which="both", ls=":")
    fig.tight_layout()
    fig.savefig(RESULTS / "a2_occupancy.png", dpi=120)


def main():
    plot_scaling()
    plot_divergence()
    plot_patterns()
    plot_occupancy()
    print("Diagramme nach results/ geschrieben:",
          ", ".join(p.name for p in sorted(RESULTS.glob("*.png"))))


if __name__ == "__main__":
    main()
