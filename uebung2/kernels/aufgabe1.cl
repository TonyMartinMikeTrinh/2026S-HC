/* Aufgabe 1 - SIMT-Ausfuehrungsmodell und Warp-Divergenz
 *
 * Terminologie nach Kaeli, Mistry, Schaa, Zhang, "Heterogeneous Computing
 * with OpenCL" (2011), Kap. 5 (AMD/NVIDIA-Hardware, SIMT/Wavefront) und
 * Kap. 3/4 (work-item, work-group, NDRange).
 *
 * Jedes work-item bearbeitet genau EIN Element und fuehrt eine rein
 * arithmetische Last mit vernachlaessigbarem Speicherbedarf aus
 * (ein einziger globaler Store am Ende).  So ist der Kernel compute-bound
 * und die SIMT-Ausfuehrung (nicht die Speicherbandbreite) limitiert.
 */

#pragma OPENCL EXTENSION cl_khr_subgroups : enable

/* Eine Newton-Iteration fuer sqrt(2): x <- x - (x*x - 2)/(2x).
 * Der Wert konvergiert und bleibt beschraenkt (keine Overflows), die
 * ALU-Arbeit ist aber real, da `iters` ein Laufzeit-Argument ist und der
 * Compiler die Schleife nicht wegfalten kann.
 * FLOP-Zaehlung pro Iteration (Division = 1 FLOP):
 *   x*x (1) - 2 (1) = 2 ; 0.5/x div (1) ; *(1) ; x-... (1) = 5 FLOP.  */
#define NEWTON_FLOPS 5
inline float newton_step(float x) {
    return x - (x * x - 2.0f) * (0.5f / x);
}

/* --- Durchsatz / Skalierung ueber n -----------------------------------
 * Reine, divergenzfreie ALU-Last: alle work-items einer Sub-Group (Warp)
 * laufen im Gleichschritt denselben Pfad.  Ueber die Problemgroesse n
 * (= global work size) wird das Device ausgelastet ("warmlaufen").      */
__kernel void alu_mix(__global float *out, const int iters) {
    const int gid = get_global_id(0);
    float x = 1.0f + (float)(gid & 255) * (1.0f / 256.0f);
    for (int i = 0; i < iters; i++)
        x = newton_step(x);
    out[gid] = x;
}

/* --- Divergenz-Variante A: datenabhaengige Schleifenlaenge -------------
 * Genau die im Aufgabenblatt vorgeschlagene "Verzweigung ueber
 * threadIdx % k": die Trip-Count haengt vom Lane-Index in der Sub-Group ab.
 *   D = 1  -> alle Lanes gleich lang  -> KEINE Divergenz
 *   D = S  -> Lane l laeuft (1 + l) mal so lang -> maximale Divergenz
 * Der Warp serialisiert die Pfade und laeuft bis zur laengsten Lane; die
 * kuerzeren Lanes sind derweil per Praedikation stillgelegt.            */
__kernel void divergence_varlen(__global float *out, const int base, const int D) {
    const int gid = get_global_id(0);
    const int lane = get_sub_group_local_id();      /* 0 .. S-1 im Warp */
    const int trip = base * (1 + (lane % D));       /* datenabhaengige Laenge */
    float x = 1.0f + (float)(gid & 255) * (1.0f / 256.0f);
    for (int i = 0; i < trip; i++)
        x = newton_step(x);
    out[gid] = x;
}

/* --- Divergenz-Variante B: gleiche Nutzarbeit, nur umverteilt ----------
 * Isoliert die reine Serialisierungs-Strafe.  Pro Warp wird IMMER dieselbe
 * Gesamtzahl an Iterationen (S*base) geleistet, aber nur auf `active`
 * Lanes konzentriert; die uebrigen Lanes divergieren in den Leerlauf.
 *   active = S -> jede Lane base Iterationen           -> konvergent
 *   active = 1 -> eine Lane S*base, Rest 0             -> volle Serialisierung
 * Da die Nutzarbeit konstant ist, zeigt der Anstieg der Wall-Clock-Zeit
 * ausschliesslich den Divergenz-Overhead (bis zu Faktor S).             */
__kernel void divergence_skew(__global float *out, const int base,
                              const int sub_group, const int active) {
    const int gid = get_global_id(0);
    const int lane = get_sub_group_local_id();
    const int stride = sub_group / active;          /* gleichmaessig verteilte aktive Lanes */
    const int is_active = (lane % stride == 0);
    const int trip = is_active ? (sub_group * base) / active : 0;
    float x = 1.0f + (float)(gid & 255) * (1.0f / 256.0f);
    for (int i = 0; i < trip; i++)
        x = newton_step(x);
    out[gid] = x;
}
