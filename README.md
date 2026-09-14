# SUBLEQ (OISC) vs. a 4-instruction accumulator machine

Is a one-instruction computer actually cheaper to build out of gates than a
small conventional one? This repository measures it instead of arguing about it:
two CPUs, the same Fibonacci program, the same memory system, counted in NAND
gates and timed on a real FPGA.

**Answer: no.** The 4-instruction accumulator machine is 1.44x smaller in the
core, 1.16x smaller as a whole computer, and 2.47x faster.

| | accumulator | SUBLEQ | ratio |
|---|---:|---:|---:|
| program size (words) | 136 | 157 | 1.15x |
| instructions executed | 1398 | 799 | 0.57x |
| **cycles** | **2698** | **4795** | **1.78x** |
| CPU core, NAND-equivalent | 806 | 1161 | 1.44x |
| flip-flops | 31 | 67 | 2.16x |
| iCE40 LUT4 | 109 | 108 | 0.99x |
| Fmax (routed, hx8k) | ~103 MHz | ~74 MHz | 0.72x |
| **wall-clock run time** | **26.2 us** | **64.6 us** | **2.47x** |
| whole computer (CPU + program store) | 27406 | 31841 | 1.16x |

The combinational logic is near-identical — both designs contain one 16-bit
subtractor and map to ~109 LUT4s. The cost of SUBLEQ is *sequential state*: it
must buffer A, B, C and M[A] across every instruction. And once the program store
is counted, the CPU core is only ~3% of the gate budget, so code density
dominates — which is exactly where 3 words per instruction hurts.

## Documents

* **[project.md](project.md)** — what is being compared and why, the fairness
  rules, full results with explanation, and an honest account of which way each
  remaining bias cuts.
* **[progress.md](progress.md)** — build log: tool selection and installation,
  design decisions, bugs found, three failed attempts at correct gate counting.

## Reproducing

```sh
apt-get install iverilog yosys nextpnr-ice40
make          # assemble both programs, simulate, verify output, count gates
make fmax     # place & route both designs, report Fmax across 4 seeds
```

`make` prints cycle counts, a verification pass against an independent Python
model of each ISA, and NAND-level gate counts for both cores and both program
stores.

## Layout

```
rtl/     acc_cpu.v      4-instruction accumulator CPU (LOAD/STORE/JZ/SUB)
         subleq_cpu.v   SUBLEQ CPU
         tb.v           RAM model + testbench: runs both, counts cycles, verifies
         top.v          CPU + RAM wrappers for FPGA place-and-route
         ramg.v         gate-level register-file RAM, for area accounting
sw/      asm.py         assemblers + reference emulators for both ISAs
synth/   gates_*.ys     NAND-only technology mapping (area)
         mixed_*.ys     richer generic gate set (area cross-check)
         ice40_*.ys     iCE40 mapping for nextpnr (speed)
         gates_ram.sh   area of an N-word program store
```
