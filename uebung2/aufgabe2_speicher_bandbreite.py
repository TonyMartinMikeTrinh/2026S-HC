"""Aufgabe 2 - Speicherzugriff: Latenz verstecken und Bandbreite.

Zeigt (a) den Einfluss des Zugriffsmusters (coalesced / strided / gather)
auf die effektive Bandbreite und (b) das Verstecken der Speicherlatenz
ueber die Occupancy (Anzahl gleichzeitig residenter Wavefronts/Warps,
gesteuert ueber die work-group size).

Terminologie: Kaeli, Mistry, Schaa, Zhang, "Heterogeneous Computing with
OpenCL" (2011), Kap. 4/5.

Aufruf:  python aufgabe2_speicher_bandbreite.py
"""

from __future__ import annotations

import numpy as np
import pyopencl as cl

import common

BYTES_PER_ELEM = 8  # 1 float lesen (a) + 1 float schreiben (b)


def gbps(n, t):
    return n * BYTES_PER_ELEM / t / 1e9


def run_patterns(ctx, queue, dev, prg, n=1 << 24, local=256):
    """Drei Zugriffsmuster auf den Device-Speicher vergleichen.  Die
    coalesced-Bandbreite (bestes Muster) dient als 100-%-Referenz; die
    theoretische DRAM-Peak-Bandbreite exponiert die OpenCL-API - anders als
    CUDAs deviceQuery - nicht."""
    print("\n=== Aufgabe 2a: Zugriffsmuster vs. effektive Bandbreite ===")
    print(f"    n = {n:,} Elemente ({n*4/1e6:.1f} MB je Buffer), local work size = {local}")
    mf = cl.mem_flags
    host_a = np.random.rand(n).astype(np.float32)
    a = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=host_a)
    b = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    perm = np.random.permutation(n).astype(np.int32)
    perm_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=perm)

    rows = []
    # (1) coalesced = Referenz (100 %)
    k_co = prg.stream_coalesced
    t = common.time_kernel(lambda: k_co(queue, (n,), (local,), a, b, np.float32(2.0)))
    peak = gbps(n, t)
    rows.append(("coalesced (Stride 1)", 1, f"{peak:.2f}", "100.0"))
    # Korrektheit stichprobenartig verifizieren (der Kernel rechnet wirklich).
    out = np.empty(n, np.float32); cl.enqueue_copy(queue, out, b); queue.finish()
    assert np.allclose(out[:1000], host_a[:1000] * 2.0), "coalesced-Kernel falsch"

    # (2) strided, Stride k
    k_st = prg.stream_strided
    for stride in (2, 4, 8, 16, 32, 64, 128):
        t = common.time_kernel(
            lambda s=stride: k_st(queue, (n,), (local,), a, b, np.float32(2.0), np.int32(s), np.int32(n)))
        rows.append((f"strided (Stride {stride})", stride, f"{gbps(n,t):.2f}", f"{gbps(n,t)/peak*100:.1f}"))
    # (3) gather
    k_ga = prg.stream_gather
    t = common.time_kernel(lambda: k_ga(queue, (n,), (local,), a, b, perm_buf, np.float32(2.0)))
    rows.append(("random / gather", 0, f"{gbps(n,t):.2f}", f"{gbps(n,t)/peak*100:.1f}"))

    print(f"    Referenz (beste coalesced-Bandbreite): {peak:.1f} GB/s")
    for label, _s, bw, pct in rows:
        print(f"    {label:<24} {bw:>8} GB/s   ({pct:>5} % der Referenz)")
    common.write_csv("a2_patterns.csv", ["muster", "stride", "gbps", "pct_of_peak"], rows)
    return peak, rows


def run_occupancy(ctx, queue, dev, prg, n=1 << 24):
    """Latenz-Hiding ueber die Occupancy: die Zahl der gleichzeitig residenten
    Wavefronts wird ueber die global work size gesteuert (Grid-Stride-Kernel,
    konstantes Datenvolumen n).  Zu wenige Wavefronts -> Speicherlatenz kann
    nicht versteckt werden -> Bandbreite bricht ein."""
    print("\n=== Aufgabe 2b: Latenz verstecken ueber Occupancy (residente Wavefronts) ===")
    mf = cl.mem_flags
    a = cl.Buffer(ctx, mf.READ_ONLY, size=n * 4)
    b = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    k_gs = prg.stream_gridstride

    S = common.sub_group_size(k_gs, dev)              # SIMD-Breite = 1 Wavefront
    # Grobe Architektur-Schaetzung der max. gleichzeitig residenten Wavefronts:
    # (OpenCL exponiert das nicht) Intel-EU: ~7 Hardware-Threads je EU/CU.
    threads_per_cu = 7
    max_resident_warps = dev.max_compute_units * threads_per_cu
    print(f"    Sub-Group (Wavefront) = {S} work-items; "
          f"geschaetzte max. residente Wavefronts ~ {dev.max_compute_units} CU x {threads_per_cu} = {max_resident_warps}")

    rows = []
    peak = 0.0
    # global work size = S * num_warps  (jede work-group = 1 Wavefront -> num_warps resident)
    for num_warps in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024):
        g = S * num_warps
        t = common.time_kernel(lambda gg=g: k_gs(queue, (gg,), (S,), a, b, np.float32(2.0), np.int32(n)))
        bw = gbps(n, t)
        peak = max(peak, bw)
        occ = min(num_warps, max_resident_warps) / max_resident_warps
        rows.append((num_warps, f"{occ*100:.1f}", f"{bw:.2f}"))
    for num_warps, occ, bw in rows:
        pct = float(bw) / peak * 100
        print(f"    Wavefronts={num_warps:>5}  Occupancy~{occ:>5} %   {bw:>8} GB/s   ({pct:5.1f} % vom Besten)")
    common.write_csv("a2_occupancy.csv", ["resident_warps", "occupancy_pct", "gbps"], rows)
    return rows


def main():
    ctx, queue, dev = common.get_gpu_context()
    info = common.device_report(dev)
    print("Device:", info["name"], "|", info["vendor"], "|", info["opencl_version"])
    print(f"  {info['compute_units']} compute units @ {info['max_clock_mhz']} MHz, "
          f"max WG {info['max_work_group_size']}, global mem {info['global_mem_mb']:.0f} MB, "
          f"cacheline {info['global_cacheline_b']} B")
    prg = common.build(ctx, "aufgabe2.cl")

    run_patterns(ctx, queue, dev, prg)
    run_occupancy(ctx, queue, dev, prg)
    print("\nCSV-Ergebnisse in uebung2/results/ geschrieben.")


if __name__ == "__main__":
    main()
