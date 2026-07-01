/* Aufgabe 2 - Speicherzugriff: Latenz verstecken und Bandbreite
 *
 * Terminologie nach Kaeli, Mistry, Schaa, Zhang, "Heterogeneous Computing
 * with OpenCL" (2011), Kap. 4/5: coalesced global memory access,
 * memory objects (buffers), work-group / NDRange, latency hiding durch
 * viele gleichzeitig residente Wavefronts/Warps.
 *
 * Streaming-Kernel mit geringer arithmetischer Intensitaet: b[i] = a[i]*c.
 * Pro Element genau ein global load + ein global store (8 Byte), eine
 * Multiplikation -> der Kernel ist bandbreiten-, nicht rechenlimitiert.
 *
 * Der STORE ist in allen Varianten coalesced (b[gid]); nur das
 * LESE-Zugriffsmuster auf `a` wird variiert, um den Coalescing-Effekt
 * sauber zu isolieren.
 */

/* (1) Zusammenhaengend / coalesced, Stride 1:
 * Benachbarte work-items einer Wavefront lesen benachbarte Adressen; die
 * Hardware fasst sie zu wenigen 64-Byte-Speichertransaktionen zusammen
 * (coalescing) -> maximale effektive Bandbreite.                        */
__kernel void stream_coalesced(__global const float *a, __global float *b, const float c) {
    const int gid = get_global_id(0);
    b[gid] = a[gid] * c;
}

/* (2) Gestriped, Stride k:
 * work-item gid liest a[(gid*stride) % n].  Benachbarte work-items greifen
 * `stride` Elemente auseinander zu; eine 64-Byte-Cache-Line liefert dann
 * nur noch wenige nutzbare Elemente -> die effektive Bandbreite sinkt.   */
__kernel void stream_strided(__global const float *a, __global float *b,
                             const float c, const int stride, const int n) {
    const int gid = get_global_id(0);
    const int idx = (int)(((long)gid * stride) % n);
    b[gid] = a[idx] * c;
}

/* Grid-Stride-Variante fuer das Occupancy-Experiment:
 * Jedes work-item bearbeitet mehrere Elemente im Abstand der globalen
 * work size (weiterhin coalesced pro Schritt).  Ueber die global work size
 * laesst sich so die Zahl der gleichzeitig residenten Wavefronts/Warps
 * (= Occupancy) variieren, bei konstantem Datenvolumen n.  Zu wenige
 * Wavefronts koennen die Speicherlatenz nicht verstecken -> Bandbreite
 * bricht ein (Kaeli et al., Kap. 5: latency hiding via many wavefronts). */
__kernel void stream_gridstride(__global const float *a, __global float *b,
                                const float c, const int n) {
    const int gsize = get_global_size(0);
    for (int i = get_global_id(0); i < n; i += gsize)
        b[i] = a[i] * c;
}

/* (3) Zufaellig / Gather:
 * Der Leseindex kommt aus einer vorab erzeugten Zufallspermutation `perm`.
 * Kein raeumlicher Zusammenhang -> nahezu kein Coalescing, viele
 * Cache-Line-Misses, minimale effektive Bandbreite.                      */
__kernel void stream_gather(__global const float *a, __global float *b,
                            __global const int *perm, const float c) {
    const int gid = get_global_id(0);
    b[gid] = a[perm[gid]] * c;
}
