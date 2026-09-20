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

| design | ops | words | core | all-RAM | ROM=code | ROM=code+RO | cycles | gate-Mcy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 841 | 1241 | 164783 | n/a | n/a | 47509 | 7829 |
| LDA STA JZ SUB JN | 5 | 298 | 1134 | 59125 | n/a | n/a | 14873 | 879 |
| + ADD JMP | 7 | 247 | 1311 | 49477 | n/a | n/a | 11013 | 545 |
| **+ LDX LDAX STAX** | **10** | **235** | 1509 | 47295 | 9344 | **7078** | 10333 | 73.1 |
| + LDI ADDI | 12 | 227 | 1691 | 45927 | 8019 | 7325 | 9814 | **71.9** |
| + AND OR XOR SHR | 14 | 235 | 1711 | 47497 | 9546 | 7280 | 10333 | 75.2 |

**Ten instructions wins** — 4.8x better than seven on area x time, 67x better
than SUBLEQ, with the curve turning up at 14.

The index register is the reason, and not for the obvious reason. It costs 148
gates and saves only 12 words of program. What it actually does is remove the
need for self-modifying code, which lets the whole program move from RAM
(~196 gates/word) into ROM (~4 gates/word). **ROM eligibility is an ISA
property**, and on any workload with array indexing exactly one instruction group
buys it.

## Phase 4: survey, and what's left

A literature survey (Subleq-theta, Lipsi, SERV, Ultrasmall, Jones's Ultimate
RISC) found no ISA shape that beats an accumulator machine on this cost model.
Three further levers were tested, and the winner dropped from 11,420 to **7,078
gates**:

* **Read-only data out of writable RAM** — 12 constants were sitting in RAM at
  ~196 gates each. A memory-map change, not an ISA change: **2,266 gates**.
* **Variable pooling** — the benchmarks run in sequence, so 18 scalars pool to
  seven: **2,076 gates**. A compiler decision worth more than every remaining
  ISA decision combined.
* **Immediates** — a *net 247-gate loss*, because once constants live in ROM
  there is nothing left for an immediate field to save. They do save cycles.

Also measured and rejected: narrower data words. Storing 368 bits costs 12.5
gates/bit at 16-bit words and 14.4 at 1-bit words — cost is set by bits, not
words, so going 8-bit like Lipsi cannot help when memory is built from gates.

Over half the remaining 7,078 gates is the benchmark's own working set.

## Phases 5-6: the MOVE machine, and a correction

Built Jones's Ultimate RISC — one instruction, `MOVE src,dst`, with a
memory-mapped accumulator, ALU, PC and index register. It came within 3.5% of the
10-instruction machine, which looked like a striking result for an OISC.

It isn't. The MOVE machine's destination address field selects between ten
behaviours, which is what an opcode field does; its ports map 1:1 onto the
accumulator machine's ten instructions. It is the same architecture with the
opcode relocated into an address — which is why its core measured *larger*, not
smaller. **Instruction count was the wrong axis**; the tables now count distinct
primitive operations.

The fair test is to give SUBLEQ the same amenity: two addresses wired to hardware
(`ADR`, an index register; `IND`, which reads and writes `mem[ADR]`). Still one
instruction.

| design | ops | gates | cycles | gate-Mcy |
|---|---:|---:|---:|---:|
| SUBLEQ | 1 | 164783 | 47509 | 7829 |
| **SUBLEQ + ADR/IND** | 3 | **8848** | 44953 | 398 |
| LDA STA JZ SUB JN | 5 | 59125 | 14873 | 879 |
| + ADD JMP | 7 | 49477 | 11013 | 545 |
| **+ LDX LDAX STAX** | 10 | **7078** | 10333 | 73.1 |
| + LDI ADDI | 12 | 7325 | 9814 | **71.9** |
| MOVE, 9 ports | 9 | 7329 | 10743 | 78.7 |
| + AND OR XOR SHR | 14 | 7280 | 10333 | 75.2 |

**Two ports take SUBLEQ from 164,783 gates to 8,848** — 18.6x smaller, from 67x
worse than the best design to 1.25x worse. SUBLEQ remains 4.35x slower in cycles,
which is genuine: three words per instruction, no native compare and no native
add are properties of the instruction that no port can fix.

## The actual finding

Sorted by gate count the field splits in two, and the boundary is not the
instruction count:

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

Everything in the cheap cluster is within 25% of everything else in it. The
dominant variable in this whole study is one binary property: **can the machine
compute an address without writing into its own program?** If yes the program is
read-only and lives in ROM at ~4 gates/word; if no it lives in RAM at ~196.
Instruction count, encoding, and where the opcode lives are sub-25% effects on
top of that.

SUBLEQ's famous inefficiency was never really about having one instruction. It
was about having no way to touch an array.

## Documents

* **[ARTICLE.md](ARTICLE.md)** — short write-up of the whole investigation and
  what it found ([русский перевод](ARTICLE.ru.md)). A prompt for getting it
  critically reviewed is in [review-prompt.md](review-prompt.md).
* **[DESIGN.md](DESIGN.md)** — reference description of the winning design: the
  ten instructions and their encoding, the microarchitecture, the memory map,
  the full gate budget, and why the index register is worth roughly 200x what it
  costs.
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
make phase4   # phase 4: three-way memory split, immediates, corrected counting
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
