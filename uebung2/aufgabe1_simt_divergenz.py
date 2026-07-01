"""Aufgabe 1 - SIMT-Ausfuehrungsmodell und Warp-Divergenz.

Zeigt (a) die Durchsatz-Skalierung eines compute-bound Kernels ueber die
Problemgroesse n (wann das Device "warmlaeuft") und (b) den Performanz-
Einbruch durch Warp-/Wavefront-Divergenz.

Terminologie: Kaeli, Mistry, Schaa, Zhang, "Heterogeneous Computing with
OpenCL" (2011), Kap. 3-5.

Aufruf:  python aufgabe1_simt_divergenz.py
"""

from __future__ import annotations

import numpy as np
import pyopencl as cl

import common

NEWTON_FLOPS = 5  # FLOP pro Newton-Iteration, siehe kernels/aufgabe1.cl


def run_scaling(ctx, queue, dev, prg, iters=512, local=256):
    """Durchsatz ueber n: von wenigen work-items bis in die Millionen.
    Bei kleinem n ist das Device unterbelegt; ab einer Schwelle saettigt es."""
    print("\n=== Aufgabe 1a: Durchsatz-Skalierung ueber n (alu_mix) ===")
    print(f"    iters/work-item = {iters}, local work size = {local}")
    ns = [1 << e for e in range(10, 25)]  # 1.024 .. 16.777.216 work-items
    kern = prg.alu_mix
    rows = []
    peak = 0.0
    for n in ns:
        out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)
        run = lambda: kern(queue, (n,), (local,), out, np.int32(iters))
        t = common.time_kernel(run)
        flops = n * iters * NEWTON_FLOPS
        gflops = flops / t / 1e9
        gitems = n / t / 1e9
        peak = max(peak, gflops)
        rows.append((n, f"{t*1e3:.3f}", f"{gflops:.2f}", f"{gitems:.3f}"))
        print(f"    n={n:>10,}  t={t*1e3:8.3f} ms   {gflops:8.2f} GFLOP/s   {gitems:6.3f} G-items/s")
    common.write_csv("a1_scaling.csv", ["n", "time_ms", "gflops", "gitems_per_s"], rows)

    # Schwelle bestimmen, ab der >=95 % des Peak-Durchsatzes erreicht sind.
    warm_n = next((n for (n, _t, g, _i) in rows if float(g) >= 0.95 * peak), ns[-1])
    print(f"    -> Peak ~ {peak:.1f} GFLOP/s; Device 'warmgelaufen' ab n ~ {warm_n:,} work-items")
    return peak, warm_n


def run_divergence_varlen(ctx, queue, dev, prg, n=1 << 22, base=64, local=256):
    """Divergenz ueber datenabhaengige Schleifenlaenge (threadIdx % D)."""
    S = common.sub_group_size(prg.divergence_varlen, dev)
    print(f"\n=== Aufgabe 1b-A: Divergenz ueber variable Schleifenlaenge ===")
    print(f"    Sub-Group (Warp/Wavefront) = {S} work-items, n = {n:,}, base = {base}")
    out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)
    kern = prg.divergence_varlen
    Ds = [d for d in (1, 2, 4, 8, 16, 32) if d <= S] + ([S] if S not in (1, 2, 4, 8, 16, 32) else [])
    rows = []
    t1 = None
    for D in Ds:
        run = lambda D=D: kern(queue, (n,), (local,), out, np.int32(base), np.int32(D))
        t = common.time_kernel(run)
        if D == 1:
            t1 = t
        # Nutzarbeit vs. tatsaechlich vom Warp abgearbeitete (serialisierte) Arbeit:
        useful = sum(base * (1 + (l % D)) for l in range(S)) / S           # Mittel pro Lane
        executed = base * D                                                # laengste Lane = Warp-Laufzeit
        simt_eff = useful / executed                                       # Lane-Auslastung
        rows.append((D, f"{t*1e3:.3f}", f"{t/t1:.2f}", f"{simt_eff*100:.1f}"))
        print(f"    D={D:>3}  t={t*1e3:8.3f} ms   Slowdown x{t/t1:5.2f}   SIMT-Effizienz {simt_eff*100:5.1f} %")
    common.write_csv("a1_divergence_varlen.csv", ["D", "time_ms", "slowdown", "simt_eff_pct"], rows)
    return S, rows


def run_divergence_skew(ctx, queue, dev, prg, n=1 << 22, base=64, local=256):
    """Divergenz bei KONSTANTER Nutzarbeit -> reine Serialisierungs-Strafe."""
    S = common.sub_group_size(prg.divergence_skew, dev)
    print(f"\n=== Aufgabe 1b-B: Divergenz bei konstanter Nutzarbeit (Serialisierung) ===")
    print(f"    Sub-Group = {S} work-items, konstante Warp-Arbeit = {S*base} Iterationen")
    out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)
    kern = prg.divergence_skew
    actives = [a for a in (S, S // 2, S // 4, S // 8, S // 16, S // 32) if a >= 1]
    actives = sorted(set(actives), reverse=True)
    rows = []
    t_full = None
    for a in actives:
        run = lambda a=a: kern(queue, (n,), (local,), out, np.int32(base), np.int32(S), np.int32(a))
        t = common.time_kernel(run)
        if a == S:
            t_full = t
        eff = a / S
        rows.append((a, f"{eff*100:.1f}", f"{t*1e3:.3f}", f"{t/t_full:.2f}"))
        print(f"    aktive Lanes={a:>3}/{S}  SIMT-Auslastung {eff*100:5.1f} %   t={t*1e3:8.3f} ms   Slowdown x{t/t_full:5.2f}")
    common.write_csv("a1_divergence_skew.csv", ["active_lanes", "simt_util_pct", "time_ms", "slowdown"], rows)
    return S, rows


def main():
    ctx, queue, dev = common.get_gpu_context()
    info = common.device_report(dev)
    print("Device:", info["name"], "|", info["vendor"], "|", info["opencl_version"])
    print(f"  {info['compute_units']} compute units @ {info['max_clock_mhz']} MHz, "
          f"max WG {info['max_work_group_size']}, cacheline {info['global_cacheline_b']} B")
    prg = common.build(ctx, "aufgabe1.cl")

    run_scaling(ctx, queue, dev, prg)
    run_divergence_varlen(ctx, queue, dev, prg)
    run_divergence_skew(ctx, queue, dev, prg)
    print("\nCSV-Ergebnisse in uebung2/results/ geschrieben.")


if __name__ == "__main__":
    main()
