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

## Phase 2: what actually minimises gates

A word of gate-built RAM costs ~196 gates, so the 100-word output array was 71%
of the phase 1 machine. Replacing it with an output port and sweeping the
instruction set gives the real picture:

| design | ops | words | core | + code in RAM | + code in ROM | cycles |
|---|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 50 | 807 | 10629 | 1903 | 4147 |
| LDA STA JZ SUB | 4 | 29 | 704 | 6423 | 1941 | 2067 |
| + ADD JMP | 6 | 18 | 887 | 4464 | 1730 | 1185 |
| **+ LDC DJNZ** | **8** | **13** | 1078 | **3678** | **1526** | 843 |
| + AND OR XOR SHR | 12 | 13 | 1293 | 3893 | 1741 | 843 |
| 2-register machine | 9 | 9 | 1071 | 2891 | 1143 | 252 |
| hardwired FSM | 0 | 0 | 884 | 884 | 884 | 150 |

Three findings:

* **The curve turns up at 12 instructions.** An instruction pays for itself only
  if it removes at least one word of program per ~196 gates it adds. The four
  logic instructions in the 12-op variant are never executed, so they are pure
  cost.
* **Code in ROM beats every ISA decision.** A ROM word is 3-8 gates against ~196
  for RAM. Moving code to ROM cuts totals by 2.4-5.6x and shrinks SUBLEQ's
  penalty from 2.9x to 1.25x.
* **The benchmark is degenerate.** The cheapest machine that computes 100
  Fibonacci numbers has no instruction set at all. See `project.md` for the
  proposed replacement benchmark.

## Phase 3: the answer

Phase 2's benchmark was degenerate — one fixed program doesn't need a program.
Phase 3 replaces it with a five-benchmark suite the same machine must run
(Fibonacci, insertion sort, multiply, GCD, binary-to-decimal; 123 outputs),
written once in a virtual ISA and macro-expanded per target so every machine
provably runs the same algorithm.

| design | ops | words | core | all-RAM | ROM+RAM | best | cycles | gate-Mcy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 852 | 1043 | 166655 | n/a | 166655 | 47509 | 7918 |
| LDA STA JZ SUB JN | 5 | 309 | 958 | 61085 | n/a | 61085 | 14873 | 909 |
| + ADD JMP | 7 | 259 | 1182 | 51603 | n/a | 51603 | 11013 | 568 |
| **+ LDX LDAX STAX** | **10** | **247** | 1335 | 49501 | **10581** | **10581** | 10333 | **109** |
| + AND OR XOR SHR | 14 | 247 | 1543 | 49709 | 10789 | 10789 | 10333 | 112 |

**Ten instructions wins** — 5.2x better than seven on area x time, 72x better
than SUBLEQ, with the curve turning up at 14.

The index register is the reason, and not for the obvious reason. It costs 153
gates and saves only 12 words of program. What it actually does is remove the
need for self-modifying code, which lets the whole program move from RAM
(~196 gates/word) into ROM (~4 gates/word): 49501 gates down to 10581. **ROM
eligibility is an ISA property**, and on any workload with array indexing exactly
one instruction group buys it.

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
make sweep    # phase 2: build and measure all seven design points
make suite    # phase 3: run the five-program suite across the ISA ladder
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
