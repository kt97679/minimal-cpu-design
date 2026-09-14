# Project: OISC vs. a 4-instruction accumulator machine

## The question

If you had to build a whole computer out of primitive logic gates — CPU, program
store, everything — and you wanted to run a small program on it, are you better
off with:

* **Design A**, a minimal but conventional accumulator machine with four
  instructions: `LOAD` (memory to accumulator), `STORE` (accumulator to memory),
  `JZ` (jump if accumulator is zero), `SUB` (subtract memory from accumulator); or
* **Design B**, a
  [one-instruction set computer](https://en.wikipedia.org/wiki/One-instruction_set_computer),
  specifically **SUBLEQ**: `subleq A, B, C` means `M[B] -= M[A]; if (M[B] <= 0) goto C`.

Two things are being asked, and they are not the same question:

1. **Area.** Which design needs fewer gates for the complete machine?
2. **Performance.** Which design runs a given program faster in wall-clock time?

SUBLEQ is folklore-famous for being "the smallest possible CPU". The folklore is
about *instruction count*, not about *gate count*, and the two are not the same
thing. This project measures the difference instead of arguing about it.

## Benchmark

Compute the first 100 Fibonacci numbers and write them into a 100-word array in
memory.

F(100) is about 3.5e20, which does not fit in a machine word, so the machines
compute F0..F99 **modulo 2^16** — the natural wraparound of a 16-bit adder. Both
machines do exactly the same arithmetic, so the comparison is unaffected.

The reference algorithm, used verbatim on both machines:

```
(a, b) = (0, 1)                  # = (F0, F1)
repeat 50 times:
    out(a)                       # F(2k)
    out(b)                       # F(2k+1)
    a += b                       # a = F(2k+2)
    b += a                       # b = F(2k+3)
```

The loop is unrolled by two on purpose. The obvious `t = a+b; a = b; b = t`
formulation needs register-to-register copies, which SUBLEQ has to synthesise out
of three instructions each; the unrolled form needs none, on either machine. This
removes an accidental handicap that would have exaggerated SUBLEQ's cost.

Neither machine has indexed addressing, so writing into the output array needs
**self-modifying code** on both: the store instruction's address field is
incremented by 2 each iteration. Both pay this cost, in their own idiom.

## Fairness rules

The result is only meaningful if the two designs are matched in everything except
the instruction set. The rules held constant:

* 16-bit data word, 12-bit address space (4096 words) on both.
* One **single-port synchronous RAM**, 1-cycle read latency, on both. Every
  memory access costs a cycle on both machines. This is the single most
  consequential rule — see "Known biases" below.
* The **same microarchitectural effort** on both: each is a simple FSM, and each
  overlaps the fetch of the next instruction with the last cycle of the current
  one. Neither is pipelined, neither is hand-tuned further than the other.
* The **same program**, the same algorithm, both verified to produce identical,
  correct output.
* No I/O, no interrupts, no halt instruction — "done" is detected by the
  testbench watching for a fetch from a known address, so it costs zero gates on
  either side.

Instruction encodings that follow from the rules:

| | Design A (accumulator) | Design B (SUBLEQ) |
|---|---|---|
| instruction size | 1 word: `{2'bx, op[1:0], addr[11:0]}` | 3 words: A, B, C |
| cycles per instruction | LOAD/STORE/SUB 2, JZ 1 | 6 |
| memory accesses per instruction | 2 (1 for JZ) | 5 |
| architectural state | PC, ACC | PC only |

## Metrics

* **Cycle count** and **instructions executed**, from RTL simulation.
* **Gate count of the CPU core**, as 2-input NAND cells after technology mapping,
  with every flip-flop normalised to a plain D type and counted as 6 NANDs (the
  classic NAND master-slave). Reported both as NAND-only and against a richer
  generic gate set (AND/OR/XOR/MUX/...) as a sanity check.
* **Gate count of the program store**, by synthesising a register-file RAM sized
  to each program and counting its gates the same way. This matters because the
  two machines need different amounts of memory, and memory turns out to dominate
  the gate budget of the whole computer.
* **Fmax**, from real place-and-route on an iCE40-HX8K, so that "performance"
  accounts for critical path and not just cycles.
* **Wall-clock run time** = cycles / Fmax, which is the number that actually
  answers question 2.

## Results

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

**The accumulator machine wins both questions.** It is 1.44x smaller in the core,
1.16x smaller as a complete computer, and 2.47x faster.

### Why

* The **combinational logic is nearly identical**: both machines contain exactly
  one 16-bit subtractor and one comparison, which is why the iCE40 LUT counts come
  out within 1% of each other. The gate difference is not in the datapath.
* The difference is **sequential state**. SUBLEQ must buffer A, B, C and M[A]
  across a single instruction, which is 67 flip-flops against the accumulator
  machine's 31. Flip-flops are the expensive primitive.
* Those same registers widen the address multiplexer and lengthen the critical
  path (subtract -> compare-to-zero -> PC mux -> address mux -> RAM address),
  costing 28% of the clock frequency.
* SUBLEQ executes 43% fewer instructions but each one costs 6 cycles and 5 memory
  accesses, so it loses on cycles anyway.
* Once the program store is counted, the **CPU core is only ~3% of the total gate
  budget**. What actually drives the system-level cost is code density, and 3
  words per instruction is what makes SUBLEQ expensive.

## Known biases, in both directions

Stated explicitly because they bound how far the result generalises.

**Against SUBLEQ:** the single 16-bit memory port. Five of SUBLEQ's six cycles are
memory accesses. Widen the instruction fetch to 48 bits and SUBLEQ drops to about
3 cycles per instruction — roughly 2400 cycles, which would *beat* the accumulator
machine on cycle count. The wider memory costs more gates than the CPU difference
saves, so the system-level conclusion holds, but the cycle-count conclusion does
not survive that change.

**Against the accumulator machine:** the instruction set is deliberately crippled
per the original question. With only `SUB`, computing `a += b` takes six
instructions (negate through a temporary), and an unconditional jump takes
`LOAD zero; JZ`. Adding `ADD` and `JMP` would roughly halve its cycle count for
perhaps 40 extra gates. The measured 2.47x is therefore a **floor**, not a ceiling.

**Neutral but worth noting:** the program store is modelled as a flip-flop
register file, which is what "built from primitive gates" means. Real SRAM is
~6 transistors per bit rather than ~6 gates, which would shrink the memory term
by about an order of magnitude and make the core difference (1.44x) matter
relatively more, not less.

## What this does not claim

It does not claim OISCs are a bad idea. Their appeal was never gate count — it is
minimality and uniformity, which buys real things in other contexts: homomorphic
encryption, code obfuscation, transport-triggered architectures, and teaching.
The claim here is narrow and empirical: for building a working computer out of
gates, one instruction is not cheaper than four.

## Repository layout

```
rtl/     acc_cpu.v      Design A: 4-instruction accumulator CPU
         subleq_cpu.v   Design B: SUBLEQ CPU
         tb.v           RAM model + testbench: runs both, counts cycles, verifies
         top.v          CPU + RAM wrappers for FPGA place-and-route
         ramg.v         gate-level register-file RAM, for area accounting
sw/      asm.py         assemblers + reference emulators for both ISAs
synth/   gates_*.ys     NAND-only technology mapping (area)
         mixed_*.ys     richer generic gate set (area, cross-check)
         ice40_*.ys     iCE40 mapping for nextpnr (speed)
         gates_ram.sh   area of an N-word program store
Makefile               `make` reproduces every number above; `make fmax` adds P&R
```

## Reproducing

```sh
apt-get install iverilog yosys nextpnr-ice40
make          # assemble, simulate, verify, count gates
make fmax     # place & route both designs, report Fmax across 4 seeds
```

`sw/asm.py` contains an independent Python emulator of each ISA; the testbench
checks the RTL output against it and against a directly computed Fibonacci
sequence, so a broken CPU cannot silently produce a plausible cycle count.
