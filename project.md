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

---

# Phase 2: minimising gates across the design space

## Why the phase 1 benchmark had to change

Phase 1 measured one number that reframes the whole question: **one 16-bit word
of gate-built RAM costs ~196 NAND-equivalents**, so the 100-word output array was
19,560 gates — **71% of the entire computer**. The CPU core was 3%.

That makes the original benchmark a poor instrument for comparing instruction
sets, because no ISA change can touch the dominant term. Phase 2 therefore
replaces the output array with a **16-bit output port**: a register plus a
strobe, memory-mapped one address past the last RAM word. The port is inside the
synthesised core for every design point, so all of them carry it equally. The
task is otherwise unchanged — emit F0..F99 mod 2^16.

## Design points

All share one microarchitecture (single-port synchronous RAM, 1-cycle read
latency, overlapped fetch) so the instruction set is the only variable.
`rtl/cpu_acc.v` selects instruction groups at compile time.

| | instructions | notes |
|---|---|---|
| SUBLEQ | 1 | `subleq A,B,C`; reading the port address yields 0 |
| V1 | 4 | LDA STA JZ SUB — the original set |
| V2 | 6 | + ADD, JMP |
| V3 | 8 | + LDC, DJNZ (8-bit counter register) |
| V5 | 12 | + AND, OR, XOR, SHR — *unused by the program*, to find the turning point |
| FIB2 | 9 | two data registers, no data memory, specialised towards the task |
| FSM | 0 | no instruction set at all, benchmark burned into a state machine |

## Results

Gate counts are NAND-equivalent (2-input NANDs after `abc -g NAND`, each D
flip-flop counted as 6). All seven designs were RTL-simulated and verified to
emit F0..F99 correctly.

| design | ops | words | core | RAM code | **total** | ROM code | **total** | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 50 | 807 | 9822 | **10629** | 1096 | **1903** | 4147 |
| LDA STA JZ SUB | 4 | 29 | 704 | 5719 | **6423** | 1237 | **1941** | 2067 |
| + ADD JMP | 6 | 18 | 887 | 3577 | **4464** | 843 | **1730** | 1185 |
| **+ LDC DJNZ** | **8** | **13** | 1078 | 2600 | **3678** | 448 | **1526** | 843 |
| + AND OR XOR SHR | 12 | 13 | 1293 | 2600 | **3893** | 448 | **1741** | 843 |
| 2-register machine | 9 | 9 | 1071 | 1820 | **2891** | 72 | **1143** | 252 |
| hardwired FSM | 0 | 0 | 884 | 0 | **884** | 0 | **884** | 150 |

### The curve does turn up, at 12 instructions

Going 1 -> 4 -> 6 -> 8 instructions cuts total gates by 2.9x, because each added
instruction removes program words, and a word costs ~196 gates while an added
opcode costs ~100-200. Going 8 -> 12 adds 215 gates of ALU and decode and saves
**zero** words, because the program never uses AND/OR/XOR/SHR. That is the
turning point, and the rule behind it is sharp: an instruction pays for itself
only if it removes at least one word of program per ~196 gates it adds.

### Exchange rates, all measured rather than assumed

* **1 word of RAM = ~196 gates.** One saved instruction is worth about a quarter
  of the entire V1 CPU core.
* **1 word of ROM = 3-8 gates**, 25-70x cheaper. Once the output array is gone
  none of these programs self-modify, so their code does not need writable
  storage. Moving it to ROM cuts totals by 2.4-5.6x, which is the single largest
  lever in the whole study — larger than the entire instruction set question.
* **A 16-bit register = ~130 gates**, cheaper than the ~196-gate RAM word it
  replaces, and it needs no address bits in the instruction. This is why the
  register machine wins on both axes at once.

### ROM flattens the ISA question

With code in RAM, SUBLEQ costs 2.9x the best design. With code in ROM it costs
1.25x, and is actually *cheaper than V1* — its 807-gate core is smaller than V1's
704-gate core plus V1's larger program. When memory is cheap, code density stops
mattering and the comparison collapses back to core size, where the
one-instruction machine was never far behind.

## The task is degenerate, and that is the real finding

The lowest-gate machine that computes 100 Fibonacci numbers is **884 gates and
has no instruction set at all**. It is 4.2x smaller and 5.6x faster than the best
programmable design, because a benchmark consisting of one fixed program does not
need a program.

This is not a quirk of Fibonacci. Any single fixed task has this property: the
optimisation always terminates at a hardwired FSM, and the ISA ladder merely
describes how far along that road you have travelled. The 2-register machine at
1143 gates is the same phenomenon halfway down — its ADDBA/ADDAB/OUTA/OUTB
opcodes are a Fibonacci accelerator wearing an instruction set.

So "find the minimum-gate CPU for this task" has no interesting answer. The
question only becomes meaningful under a constraint that makes programmability
worth paying for.

## Proposed benchmark for phase 3

Replace one program with **a small suite that the same machine must run**, scored
as `core + memory sized for all programs` against `total cycles for all
programs`. A suite chosen so each member stresses something different:

1. **Fibonacci to 100 terms** — keep it, for continuity with phases 1 and 2.
2. **Insertion sort of 32 words** — needs indexed addressing and
   compare-and-branch. The strongest ISA differentiator in the set: machines
   without an index register must self-modify, which forces code back into RAM
   and re-prices the ROM lever.
3. **16x16 multiply and divide by shift-and-add** — needs shifts, carry and
   conditional accumulate. SUBLEQ pays enormously here.
4. **Euclid's GCD** — signed comparison and a data-dependent loop.
5. **Binary to decimal conversion** — repeated division and digit output, which
   is what a real machine of this size actually spends its time doing.

Two rules are worth fixing up front, because each is worth more than the ISA
choice itself:

* **Is self-modifying code allowed?** This decides whether code lives in ROM
  (3-8 gates/word) or RAM (~196 gates/word) — a 2.4-5.6x swing.
* **Score on area x time, not area alone.** Otherwise the answer degenerates
  toward hardwired logic again. A suite makes that much harder; the AT product
  removes the incentive entirely.

Under those rules the expected winner is an 8-12 instruction accumulator machine
with an index register — essentially a PDP-8 — and the interesting question
becomes *which* instructions rather than *how many*.

---

# Phase 3: a suite, and a non-degenerate answer

## Setup

Phase 2 ended with the benchmark defeating itself: the cheapest machine that
computes 100 Fibonacci numbers is a hardwired FSM with no instruction set. Phase
3 replaces the single program with a **five-program suite that one machine must
run in a single image**, which is what makes programmability worth paying for.

| benchmark | what it stresses |
|---|---|
| 100 Fibonacci numbers | loop, accumulate — continuity with phases 1-2 |
| insertion sort of 16 words | **indexed addressing**, compare-and-branch |
| 16x16 multiply, shift-and-add | sign testing, conditional accumulate |
| Euclid's GCD by subtraction | signed comparison, data-dependent loop |
| binary to decimal, 5 digits | restoring division by 10, repeated |

123 output values in total, emitted through the port.

Each benchmark is written **once** in a small memory-to-memory virtual ISA
(`movi mov add sub addi subi out jmp jz jn ldx stx halt`), and each target
supplies macro expansions. That guarantees every design point runs the identical
algorithm on identical data, and removes the risk of hand-optimising one
machine's assembly harder than another's. The virtual program is checked against
a directly computed model, then every target's expansion is checked by its own
emulator, then by RTL simulation — three independent checks before any gate is
counted.

## Design points

| | instructions |
|---|---|
| SUBLEQ | 1 |
| A5 | LDA STA JZ SUB **JN** |
| A7 | + ADD JMP |
| A10 | + **LDX LDAX STAX** (8-bit index register) |
| A14 | + AND OR XOR SHR — *unused by the suite*, to locate the turning point |

`JN` (branch on sign) is in the baseline this time because without it the
original four-instruction set cannot compare two numbers in bounded time: with
only branch-on-zero and subtract, deciding `a < b` costs O(value) steps. That is
a real expressiveness result, and it is why the phase 3 ladder starts at five.

## Results

Gate counts are NAND-equivalent. All five were RTL-simulated over the full suite
with zero output mismatches.

| design | ops | words | core | all-RAM | ROM+RAM | best | cycles | gate-Mcycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 852 | 1043 | 166655 | n/a | 166655 | 47509 | 7918 |
| LDA STA JZ SUB JN | 5 | 309 | 958 | 61085 | n/a | 61085 | 14873 | 909 |
| + ADD JMP | 7 | 259 | 1182 | 51603 | n/a | 51603 | 11013 | 568 |
| **+ LDX LDAX STAX** | **10** | **247** | 1335 | 49501 | **10581** | **10581** | 10333 | **109** |
| + AND OR XOR SHR | 14 | 247 | 1543 | 49709 | 10789 | 10789 | 10333 | 112 |

*n/a: the machine needs self-modifying code, so its program cannot live in ROM.*

**The minimum is at 10 instructions**, and it is not close: 5.2x better than the
7-instruction machine on area x time, and 72x better than SUBLEQ. The curve turns
up at 14, where four unused instructions add 208 gates and save nothing.

## Why the index register is worth far more than its 153 gates

`LDX/LDAX/STAX` cost 153 gates of core and save only 12 words of program — by the
phase 2 exchange rate that is roughly break-even. The real effect is
**categorical**: without an index register, the only way to compute an address is
to write it into an instruction, so the sort forces the whole program into
writable memory. With one, no program word is ever written, and the code can live
in ROM at ~4 gates/word instead of ~196.

So the index register does not win by making the program shorter. It wins by
**changing which kind of memory the program can live in** — 49501 gates down to
10581, a 4.7x cut for 153 gates spent. Nothing else in the study has that
leverage, and no purely local cost model would have predicted it.

This also sharpens the phase 2 finding. There, "put the code in ROM" looked like
a free 2.4-5.6x that was independent of the instruction set. It is not
independent at all: **ROM eligibility is an ISA property**, and on a suite with
any array indexing in it, exactly one instruction group buys it.

## The residue: what dominates at the optimum

At the 10-instruction optimum the budget is:

* **9,246 gates** of memory subsystem, of which ~9,200 is 47 words of *data* RAM
  (the 16-word sort array plus scalars and constants) and only ~836 is the
  200-word code ROM;
* **1,335 gates** of CPU core.

Data has replaced code as the dominant term. That is the correct end state — the
machine has been optimised until what remains is the problem's own working set,
which no instruction set can remove. Further ISA work would be chasing 13% of the
budget.

## SUBLEQ on a realistic workload

SUBLEQ's cost rises sharply once the workload is more than arithmetic in a loop:

* **801 words of code** against 200, because every comparison is a macro. `jn` is
  5 instructions, `jz` is 5, an indexed load is 9 and an indexed store is 15.
* **No ROM eligibility**, since indexed access is self-modification by
  construction — this is not an implementation choice, it is what the
  architecture is.
* **47,509 cycles** against 10,333.

Together: **72x worse on area x time**. In phase 2, with code in ROM, SUBLEQ came
within 1.25x of the best design. The difference is entirely the suite: one tight
arithmetic loop flatters it, and anything with an array in it does not.

## A correctness note worth recording

SUBLEQ's natural sign test, "branch if `-s <= 0`", is wrong for exactly one
value: `s = -32768`, where negation overflows. Both the multiply and the divide
shift an operand through exactly `0x8000`, so the bug is live, and it produced a
product short by exactly `2 * multiplicand`. The correct expansion tests
`(s + 1) <= 0`, which costs two more instructions and is exact everywhere except
`s = +32767`.

Relatedly, all these machines compare by subtracting and testing the sign, which
is only valid when the difference fits in a word. The sort and GCD inputs are
therefore kept below 2^14. That constraint is a property of the machines, not of
the benchmark, and a machine with a carry or overflow flag would not need it.

## Conclusion across all three phases

For building a small computer out of gates and running a realistic mixed
workload, the answer is an **accumulator machine with about ten instructions**:
load, store, add, subtract, branch-on-zero, branch-on-sign, unconditional jump,
and an index register with indexed load and store.

Ranked by how much each decision is worth:

1. **Don't store results you can stream out** — 71% of the phase 1 machine.
2. **Get an index register, so code can live in ROM** — 4.7x.
3. **Have ADD and JMP rather than synthesising them** — 1.6x on area x time.
4. **Don't add instructions the workload never executes** — the 14-op variant
   pays 208 gates for nothing.
5. **Core microarchitecture** — 13% of the final budget, and the only term left
   once the others are done.

One instruction is not cheaper than ten. It was never cheaper than four.
