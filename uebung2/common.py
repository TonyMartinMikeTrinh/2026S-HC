"""Gemeinsame OpenCL-Host-Infrastruktur fuer Uebungsblatt 2.

Terminologie durchgaengig nach Kaeli, Mistry, Schaa, Zhang:
"Heterogeneous Computing with OpenCL" (Morgan Kaufmann, 2011).

Die vier Schritte des OpenCL-Host-Programms (Kap. 2/3 "The four steps"):
    1. Platform / Device auswaehlen  -> get_gpu_context()
    2. Context + Command-Queue erzeugen
    3. Program aus Kernel-Quellen bauen (online compilation, Kap. 6)
    4. Kernel als NDRange (global/local work size) auf die Queue schieben

Gemessen wird ueber Command-Queue-Profiling (clGetEventProfilingInfo,
Kap. 2 "Profiling"): das liefert die reine Device-Ausfuehrungszeit des
Kernels und blendet Host-Overhead aus.
"""

from __future__ import annotations

import statistics
import warnings
from pathlib import Path

import numpy as np
import pyopencl as cl

# Der Benchmark holt denselben Kernel bewusst in mehreren Funktionen; die
# damit verbundene Effizienz-Warnung ist hier irrelevant (Messschleifen
# nutzen jeweils eine gebundene Kernel-Instanz).
warnings.filterwarnings("ignore", category=cl.RepeatedKernelRetrieval)

KERNEL_DIR = Path(__file__).resolve().parent / "kernels"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def get_gpu_context() -> tuple[cl.Context, cl.CommandQueue, cl.Device]:
    """Schritt 1+2: erstes GPU-Device suchen, Context und Command-Queue
    (mit aktiviertem Profiling) erzeugen."""
    gpu = None
    for platform in cl.get_platforms():
        for dev in platform.get_devices():
            if dev.type & cl.device_type.GPU:
                gpu = dev
                break
        if gpu:
            break
    if gpu is None:  # Fallback: irgendein Device (z. B. CPU-ICD)
        gpu = cl.get_platforms()[0].get_devices()[0]

    ctx = cl.Context([gpu])
    queue = cl.CommandQueue(ctx, properties=cl.command_queue_properties.PROFILING_ENABLE)
    return ctx, queue, gpu


def build(ctx: cl.Context, filename: str, options: str = "") -> cl.Program:
    """Schritt 3: Program aus einer .cl-Quelle online kompilieren."""
    src = (KERNEL_DIR / filename).read_text(encoding="utf-8")
    return cl.Program(ctx, src).build(options=options)


def device_report(dev: cl.Device) -> dict:
    """Fuer den Ergebnisbericht relevante Device-Eigenschaften
    (das OpenCL-Pendant zu CUDAs deviceQuery)."""
    info = {
        "name": dev.name.strip(),
        "vendor": dev.vendor.strip(),
        "opencl_version": dev.version.strip(),
        "compute_units": dev.max_compute_units,
        "max_clock_mhz": dev.max_clock_frequency,
        "max_work_group_size": dev.max_work_group_size,
        "local_mem_kb": dev.local_mem_size / 1024,
        "global_mem_mb": dev.global_mem_size / (1024 * 1024),
        "global_cacheline_b": dev.global_mem_cacheline_size,
    }
    return info


def sub_group_size(kernel: cl.Kernel, dev: cl.Device) -> int:
    """SIMD-Breite / Groesse der Sub-Group, die der Online-Compiler fuer
    diesen Kernel gewaehlt hat.  Die Sub-Group ist das OpenCL-portable
    Pendant zur *Wavefront* (AMD) bzw. zum *Warp* (NVIDIA) aus Kaeli et al.
    (Kap. 5, SIMT/SIMD-Ausfuehrung)."""
    return kernel.get_work_group_info(
        cl.kernel_work_group_info.PREFERRED_WORK_GROUP_SIZE_MULTIPLE, dev
    )


def time_kernel(run, reps: int = 9, warmup: int = 2) -> float:
    """Fuehrt `run()` (gibt ein cl.Event zurueck) mehrfach aus und liefert
    den Median der reinen Device-Zeit in Sekunden (Command-Queue-Profiling).
    Warmup-Laeufe fangen JIT-Compile / erstes Warmlaufen des Device ab."""
    for _ in range(warmup):
        run().wait()
    samples = []
    for _ in range(reps):
        evt = run()
        evt.wait()
        samples.append((evt.profile.end - evt.profile.start) * 1e-9)
    return statistics.median(samples)


def ensure_results_dir() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def write_csv(name: str, header: list[str], rows: list) -> Path:
    path = ensure_results_dir() / name
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    return path
