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

*(Corrected in phase 4: the original table under-counted every design with
submodules, because yosys `stat` reports per module. Numbers below are the
corrected ones; no conclusion changed.)*

| design | ops | words | core | RAM code | **total** | ROM code | **total** | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 50 | 995 | 9822 | **10817** | 1274 | **2269** | 4147 |
| LDA STA JZ SUB | 4 | 29 | 865 | 5719 | **6584** | 1404 | **2269** | 2067 |
| + ADD JMP | 6 | 18 | 1050 | 3577 | **4627** | 1026 | **2076** | 1185 |
| **+ LDC DJNZ** | **8** | **13** | 1240 | 2600 | **3840** | 587 | **1827** | 843 |
| + AND OR XOR SHR | 12 | 13 | 1456 | 2600 | **4056** | 587 | **2043** | 843 |
| 2-register machine | 9 | 9 | 1071 | 1820 | **2891** | 72 | **1143** | 252 |
| hardwired FSM | 0 | 0 | 884 | 0 | **884** | 0 | **884** | 150 |

### The curve does turn up, at 12 instructions

Going 1 -> 4 -> 6 -> 8 instructions cuts total gates by 2.8x, because each added
instruction removes program words, and a word costs ~196 gates while an added
opcode costs ~100-200. Going 8 -> 12 adds 216 gates of ALU and decode and saves
**zero** words, because the program never uses AND/OR/XOR/SHR. That is the
turning point, and the rule behind it is sharp: an instruction pays for itself
only if it removes at least one word of program per ~196 gates it adds.

### Exchange rates, all measured rather than assumed

* **1 word of RAM = ~196 gates.** One saved instruction is worth about a quarter
  of the entire V1 CPU core.
* **1 word of ROM = 4-17 gates** depending on how much content ABC can share,
  against ~196 for RAM. Once the output array is gone
  none of these programs self-modify, so their code does not need writable
  storage. Moving it to ROM cuts totals by 2.1-4.8x, which is the single largest
  lever in the whole study — larger than the entire instruction set question.
* **A 16-bit register = ~130 gates**, cheaper than the ~196-gate RAM word it
  replaces, and it needs no address bits in the instruction. This is why the
  register machine wins on both axes at once.

### ROM flattens the ISA question

With code in RAM, SUBLEQ costs 2.8x the best design. With code in ROM it costs
1.24x, and comes out *exactly level with V1* — its larger core is offset by V1
needing more program words. When memory is cheap, code density stops
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

*(Corrected in phase 4, same counting bug as above.)*

| design | ops | words | core | all-RAM | ROM+RAM | best | cycles | gate-Mcycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 852 | 1241 | 166853 | n/a | 166853 | 47509 | 7927 |
| LDA STA JZ SUB JN | 5 | 309 | 1134 | 61261 | n/a | 61261 | 14873 | 911 |
| + ADD JMP | 7 | 258 | 1360 | 51587 | n/a | 51587 | 11013 | 568 |
| **+ LDX LDAX STAX** | **10** | **246** | 1508 | 49480 | **11420** | **11420** | 10333 | **118** |
| + AND OR XOR SHR | 14 | 246 | 1711 | 49683 | 11623 | 11623 | 10333 | 120 |

*n/a: the machine needs self-modifying code, so its program cannot live in ROM.*

**The minimum is at 10 instructions**, and it is not close: 4.8x better than the
7-instruction machine on area x time, and 67x better than SUBLEQ. The curve turns
up at 14, where four unused instructions add 202 gates and save nothing.

## Why the index register is worth far more than its gates

*(Figures in this section are the phase 3 measurements, at that phase's address
width. Phase 4 re-measures the same group at 198-210 gates depending on whether
the output port is synthesised with the CPU; see DESIGN.md.)*

`LDX/LDAX/STAX` cost 148 gates of core and save only 12 words of program — by the
phase 2 exchange rate that is roughly break-even. The real effect is
**categorical**: without an index register, the only way to compute an address is
to write it into an instruction, so the sort forces the whole program into
writable memory. With one, no program word is ever written, and the code can live
in ROM at ~4 gates/word instead of ~196.

So the index register does not win by making the program shorter. It wins by
**changing which kind of memory the program can live in** — 49480 gates down to
11420, a 4.3x cut for 148 gates spent. Nothing else in the study has that
leverage, and no purely local cost model would have predicted it.

This also sharpens the phase 2 finding. There, "put the code in ROM" looked like
a free 2.4-5.6x that was independent of the instruction set. It is not
independent at all: **ROM eligibility is an ISA property**, and on a suite with
any array indexing in it, exactly one instruction group buys it.

## The residue: what dominates at the optimum

At the 10-instruction optimum the budget is:

* **9,912 gates** of memory subsystem, of which ~9,000 is 47 words of *data* RAM
  (the 16-word sort array plus scalars and constants) and the rest is the
  200-word code ROM;
* **1,508 gates** of CPU core.

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

Together: **67x worse on area x time**. In phase 2, with code in ROM, SUBLEQ came
within 1.24x of the best design. The difference is entirely the suite: one tight
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
workload, the best design reached by hand is an **accumulator machine with about
ten instructions**: (phase 7's mechanical search later found a smaller one, built
on reverse subtract with no ADD, SUB or JMP -- see that section)
load, store, add, subtract, branch-on-zero, branch-on-sign, unconditional jump,
and an index register with indexed load and store.

Ranked by how much each decision is worth:

1. **Don't store results you can stream out** — 71% of the phase 1 machine.
2. **Get an index register, so code can live in ROM** — 4.3x.
3. **Have ADD and JMP rather than synthesising them** — 1.6x on area x time.
4. **Don't add instructions the workload never executes** — the 14-op variant
   pays 202 gates for nothing.
5. **Core microarchitecture** — 13% of the final budget, and the only term left
   once the others are done.

One instruction is not cheaper than ten. It was never cheaper than four.

---

# Phase 4: can anything beat it? A survey, and three more levers

Phase 3 landed on a 10-instruction accumulator machine. This phase asks whether
any *other* instruction set does better, by (a) reading what has actually been
tried, and (b) testing the ideas that survive contact with our cost model.

## What the literature says

**Sakamoto, Ahmed, Anderson and Hara-Azumi, "Subleq⊖: An Area-Efficient
Two-Instruction-Set Computer"** is the closest published work to phases 1-3.
They start from a SUBLEQ OISC and add exactly one instruction — a bit-reversed
subleq — chosen because it reuses the existing subtractor and turns SUBLEQ's
O(w) right shift into O(1). On a Virtex-6 they measure the baseline SUBLEQ at
147 LUTs and the two-instruction version at 195, a 1.33x area cost for a 2.78x
geometric-mean speedup across twelve benchmarks. Two alternative extensions that
added *dedicated* hardware (a shifter, a multiplier) cost 1.87x and 5.86x area
and were slower in wall-clock terms, because the clock period grew more than the
cycle count shrank.

That is the same shape as our result, arrived at independently: **instructions
that reuse the existing datapath are nearly free, and instructions that add new
datapath rarely pay.** Their 1.33x-for-2.78x is our `ADD`/`JMP`/index-register
story; their shifter and multiplier are our `AND/OR/XOR/SHR` variant.

**Martin Schoeberl's Lipsi** ("probably the smallest processor in the world") is
an 8-bit **accumulator** machine at under 100 logic elements, with its memory in
on-chip RAM. Schoeberl is explicit that he chose an accumulator over a register
file deliberately. **Ultrasmall** and **Supersmall** take the other route — a
2-bit-serial MIPS datapath — and pay about 22 cycles per instruction for it.
**SERV**, the smallest RISC-V core, is fully bit-serial. Puffitsch's Ø processor
generates hardware only for the instructions a given program actually uses,
which is our 14-instruction result turned into a tool.

**Jones's "The Ultimate RISC" (1988)** is the other classic minimum: a single
`MOVE mem,mem` instruction with a memory-mapped ALU and a memory-mapped program
counter. Jones notes in the paper that the three address fields reduce to two if
an accumulator is used — which is most of the distance to our design already.

Across all of it, the convergent answer for minimum area is an **accumulator
machine with a narrow instruction set**. Nothing in the literature suggests a
fundamentally different ISA shape wins; the disagreements are about datapath
width and about how instructions are encoded.

## A counting bug, found and fixed

While testing these ideas, the memory-subsystem figure came out *identical* to
the data RAM alone, which was implausible. Cause: yosys `stat` reports cell
counts **per module**, and the parser was reading whichever module printed
first. Every design with submodules — all the `comp_*` cores and both ROM splits
in phases 2 and 3 — was therefore counted from a fragment.

Fixed by adding `flatten` before technology mapping. All phase 2 and phase 3
tables above have been recomputed and corrected. **No conclusion changed**: the
phase 2 minimum is still at 8 instructions, the phase 3 minimum still at 10, and
the turn-up points are unmoved. The corrected phase 3 optimum is 11,420 gates
rather than the 10,581 originally reported.

## Three levers tested

### 1. Read-only data does not belong in writable RAM — 2,266 gates

At the phase 3 optimum, 12 of the 47 data words were **constants**, sitting in
gate-built RAM at ~196 gates each because the memory map put all data in one
region. They are never written. Splitting the map so the ROM covers code *and*
constants moves them to ~4 gates/word.

This needs no ISA change at all — it is a memory-map decision — but it is only
available to a machine that already qualifies for ROM, so it compounds with the
index register rather than being independent of it.

### 2. Variables do not each need their own word — 2,076 gates

The five benchmarks run in sequence, so their working sets never overlap. Phase
3 gave all 18 scalars their own word; pooling them by liveness needs only
**seven** (the maximum live at any point, in the sort and the decimal loop).
Eleven words of RAM removed, for nothing but a renaming.

This is a compiler question, not an architecture one. That it is worth more than
every remaining instruction-set decision put together is itself the finding.

### 3. Immediate operands — no area win, small time win

Once constants cost ~4 gates in ROM, an immediate field has almost nothing left
to save. Adding `LDI`/`ADDI` (12-bit sign-extended) removes the 8 constants that
fit, but costs 182 gates of core: **net 247 gates worse on area**. It does cut
519 cycles by turning two-cycle operand fetches into one-cycle immediates, so it
wins narrowly on area x time (71.9 against 73.1) and loses on area.

That is a genuine and slightly surprising result: immediates are an
*area* optimisation only when constants are expensive to store.

### Narrowing the data RAM's address decoder — 12 gates

Addressing the data RAM with `ceil(log2(NDATA))` bits instead of the full address
width saves 12 gates. Measured and discarded.

## Results

Same five-program suite, all RTL-verified, corrected counting:

| design | ops | words | core | all-RAM | ROM=code | ROM=code+RO | cycles | gate-Mcy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 841 | 1241 | 164783 | n/a | n/a | 47509 | 7829 |
| LDA STA JZ SUB JN | 5 | 298 | 1134 | 59125 | n/a | n/a | 14873 | 879 |
| + ADD JMP | 7 | 247 | 1311 | 49477 | n/a | n/a | 11013 | 545 |
| **+ LDX LDAX STAX** | **10** | **235** | 1509 | 47295 | 9344 | **7078** | 10333 | 73.1 |
| + LDI ADDI | 12 | 227 | 1691 | 45927 | 8019 | 7325 | 9814 | **71.9** |
| + AND OR XOR SHR | 14 | 235 | 1711 | 47497 | 9546 | 7280 | 10333 | 75.2 |

**The 10-instruction machine is still the answer**, now at **7,078 gates** —
1.61x smaller than the corrected phase 3 figure of 11,420, from two changes that
are not instruction-set changes at all.

The 12-instruction immediate variant ties it (71.9 vs 73.1 on area x time) while
being larger, so the choice between them depends on which you are optimising.
The 14-instruction variant remains strictly worse.

## Where the remaining 7,078 gates are

| | gates | share |
|---|---:|---|
| data RAM, 23 words (16-word array + 7 scalars, with decode and mux) | 4,597 | 65% |
| CPU core plus output port | 1,509 | 21% |
| 212-word code+constant ROM | 912 | 13% |
| address decode and glue | 60 | 1% |

Over half is the benchmark's own working set. **No instruction set can remove
it**, which is the sense in which this optimisation is finished.

## Two ideas tested and rejected on measurement

**Narrower data words.** Lipsi is 8-bit; SERV is bit-serial. If a narrower word
made storage cheaper, that would beat every ISA change left. It does not. Storing
the same 368 bits costs:

| organisation | gates | per bit |
|---|---:|---:|
| 23 x 16 bit | 4,597 | 12.49 |
| 46 x 8 bit | 4,626 | 12.57 |
| 92 x 4 bit | 4,705 | 12.79 |
| 368 x 1 bit | 5,296 | 14.39 |

Cost is set by **bits stored, not words**, and narrowing the word only multiplies
the per-word decoder. A 16-bit benchmark on an 8-bit machine would store the same
bits, need double-length arithmetic routines, and shrink only the core. Lipsi's
8-bit choice is right for its cost model — FPGA logic elements with free block
RAM — and wrong for ours, where memory is built from gates.

**Removing instructions from the winner.** `JZ` looks redundant next to `JN`, and
its 16-input zero-detect is ~25 gates. But synthesising `jz` from `jn` costs
roughly 20 extra ROM words and cycles in every loop, for a net loss. The
10-instruction set is a local optimum in both directions.

## The one thing left untested

A **MOVE machine** in Jones's sense — one instruction, `MOVE src,dst`, with a
memory-mapped accumulator, ALU and program counter — is the most plausible
untested alternative, and with an accumulator its instruction fits in one 16-bit
word (two 8-bit address fields) rather than SUBLEQ's three.

Reasoning about it against our cost model: code size would be close to the
accumulator machine's, since both spend about one word per operation. The core
would trade opcode decode for port-address comparators, probably a wash. But
every MOVE needs a source read *and* a destination write plus its own fetch — 3
cycles against our average of 1.86 — and indexed access would need extra
memory-mapped ports. The expectation is a small area win and a ~1.6x cycle loss,
so worse on area x time and possibly better on raw gates.

That is an estimate, not a measurement, and it is the obvious next experiment.

---

# Phase 5: the MOVE machine, measured

Phase 4 left one candidate untested: Jones's Ultimate RISC, a machine whose only
instruction is `MOVE src,dst`, with arithmetic and control flow happening as side
effects of writing to memory-mapped ports. This phase builds it and runs the same
suite.

## The design

With an accumulator, `MOVE` needs only two address fields, so the instruction
packs into a single 16-bit word as `{dst[7:0], src[7:0]}`. Ports occupy the top of
the 256-word address space:

| port | as source | as destination |
|---|---|---|
| ACC | accumulator | `acc <- v` |
| ADD / SUB | — | `acc <- acc +/- v` |
| PC / PCZ / PCN | — | jump, jump if `acc == 0`, jump if `acc < 0` |
| ADR / ADRA | — | index register: `adr <- v`, `adr <- adr + v` |
| IND | `mem[adr]` | `mem[adr] <- v` |
| OUT | — | output strobe |

Timing under the same single-port synchronous RAM as every other design:
`cycles = 1 + (source needs a memory read) + (destination needs a write)`. So
port-to-port costs 1 cycle, memory-to-port and port-to-memory 2, and
memory-to-memory 3. Crucially most real moves are memory-to-port or
port-to-memory, not memory-to-memory.

## Result

| design | ops | words | core | all-RAM | ROM=code | ROM=code+RO | cycles | gate-Mcy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **+ LDX LDAX STAX** | **10** | **235** | 1509 | 47295 | 9344 | **7078** | 10333 | 73.1 |
| + LDI ADDI | 12 | 227 | 1691 | 45927 | 8019 | 7325 | 9814 | **71.9** |
| **MOVE (Ultimate RISC)** | **1** | 225 | 1606 | 45452 | 13784 | 7329 | 10743 | 78.7 |

**It loses, but barely: 3.5% more gates and 7.7% worse on area x time.** After
SUBLEQ came in at 67x worse, a one-instruction machine finishing within 4% of the
best design is the most interesting result in the project.

My phase 4 prediction was "a small area win and a ~1.6x cycle loss". Both halves
were wrong, in opposite directions, and the reasons are worth recording.

## Why the cycle estimate was wrong

I assumed every MOVE costs 3 cycles: fetch, read source, write destination. In
practice the accumulator absorbs one end of almost every move — `MOVE x,ADD` has
no destination write, `MOVE ACC,x` has no source read — so the measured average is
**2.09 cycles per instruction**, against 1.86 for the accumulator machine.

And it needs **fewer instructions**: 5,130 against 5,564. Memory-to-memory moves
are a real instruction on this machine, so `mov d,s` is one word where the
accumulator machine needs `LDA; STA`, and `out s` is one word instead of two.
Its code is **168 words against 200**.

Net effect on cycles: 10,743 against 10,333, a 4% loss, not 60%.

## Why the area estimate was wrong

I expected the core to shrink, since a MOVE machine has no opcode to decode. It
grew, by 97 gates. Removing the opcode does not remove the decoding — it moves
it. The machine needs two 8-bit port comparators (one per address field), an
index register with its own adder, a multiplexer to substitute `adr` for either
address field when `IND` is used, and a three-way address mux. A 4-bit opcode
field feeding a small decoder is simply cheaper than comparing two 8-bit
addresses against a port range.

## The real cost: constants

Look at the `ROM=code` column, where only code goes in ROM: the MOVE machine is
**13,784 gates against 9,344** — far worse. But at `ROM=code+RO` the two are
within 3.5%.

The reason is that a MOVE machine cannot encode a branch target in its
instruction. `jmp L` is `MOVE K,PC` where `K` is a memory word containing `L`, so
**every branch site needs its own constant word**. The suite needs 34 constants
on the MOVE machine against 12 on the accumulator machine — 22 extra words, all
of them branch targets.

At ~196 gates per RAM word that would be 4,300 gates and the MOVE machine would
be soundly beaten. At ~4 gates per ROM word it costs about 90 and the race is
close. **The Ultimate RISC is only competitive because read-only storage is
cheap** — which is exactly the lever found in phase 4, and it matters roughly
four times as much to this machine as to the accumulator machine.

## Revised conclusion

The final ranking on this benchmark, cheapest first:

| | gates | area x time |
|---|---:|---:|
| 10-instruction accumulator + index register | **7,078** | 73.1 |
| 12-instruction, with immediates | 7,325 | **71.9** |
| MOVE / Ultimate RISC | 7,329 | 78.7 |
| 14-instruction | 7,280 | 75.2 |
| SUBLEQ | 164,783 | 7,829 |

Three quite different architectures — 10 instructions, 12 instructions, and one
instruction — land within 3.5% of each other, while a fourth one-instruction
machine is 23x worse. The spread between them is far smaller than the spread
created by decisions that are not about the instruction set at all: whether
read-only data sits in ROM (2,266 gates), and whether variables share storage
(2,076 gates).

That is the honest end of this investigation. Once the memory hierarchy is right,
the instruction set stops being the interesting variable — and the choice of
*which* one instruction matters enormously more than the choice of *how many*.
SUBLEQ and MOVE are both OISCs, and they differ by a factor of 23.

---

# Phase 6: the MOVE comparison was unfair, and fixing it changes the story

## The objection

The MOVE machine is an OISC only by a technicality. It has a full ALU; you reach
it by moving a value to one address and collecting the result from another. Its
destination address field selects between ten different behaviours, which is
exactly what an opcode field does. Comparing it to SUBLEQ as "one instruction
versus one instruction" is not a like-for-like comparison.

This is correct, and phase 5's headline — "a one-instruction machine finishes
within 4% of the best design" — was misleading. The measurements themselves
already said so: the MOVE core came out **larger** than the 10-instruction
accumulator machine, and the reason given was that removing the opcode relocates
the decoding rather than eliminating it. That should have been the conclusion
rather than a footnote.

Mapping the two machines against each other makes the point unarguable:

| MOVE port | accumulator instruction |
|---|---|
| `MOVE m,ACC` / `MOVE ACC,m` | `LDA m` / `STA m` |
| `MOVE m,ADD` / `MOVE m,SUB` | `ADD m` / `SUB m` |
| `MOVE k,PC` / `PCZ` / `PCN` | `JMP` / `JZ` / `JN` |
| `MOVE m,ADR` / `MOVE m,ADRA` | `LDX m` (index register) |
| `MOVE IND,m` / `MOVE m,IND` | `LDAX` / `STAX` |

It is the same ten operations. The MOVE machine is the 10-instruction
accumulator machine with the opcode moved out of a dedicated field and into the
destination address. Its near-tie with that machine is not a surprising result
about OISCs; it is two encodings of one architecture landing in the same place.

**The instruction count was the wrong axis.** What matters is the number of
distinct primitive operations the hardware implements, wherever the selection
bits happen to live. All tables below count operations, not instruction formats.

## The fair experiment

If a memory-mapped functional unit is allowed for MOVE, it must be allowed for
SUBLEQ. So: SUBLEQ with the same amenity, and nothing else changed. Two
addresses are wired to hardware instead of storage:

* `ADR` — an index register. `subleq ADR,ADR` clears it, `subleq K,ADR` adds to
  it.
* `IND` — reads `mem[ADR]`, writes `mem[ADR]`.

That is still literally one instruction, and it makes indexed access possible
without the program modifying its own code: an indexed load drops from 9
instructions to 9 but an indexed *store* drops from 15 to 9, and neither
self-modifies any more.

## Result

| design | ops | words | core | all-RAM | ROM=code | ROM=code+RO | cycles | gate-Mcy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SUBLEQ | 1 | 841 | 1241 | 164783 | n/a | n/a | 47509 | 7829 |
| **SUBLEQ + ADR/IND** | **3** | 805 | 1441 | 157979 | 11544 | **8848** | 44953 | 398 |
| LDA STA JZ SUB JN | 5 | 298 | 1134 | 59125 | n/a | n/a | 14873 | 879 |
| + ADD JMP | 7 | 247 | 1311 | 49477 | n/a | n/a | 11013 | 545 |
| **+ LDX LDAX STAX** | **10** | 235 | 1509 | 47295 | 9344 | **7078** | 10333 | 73.1 |
| + LDI ADDI | 12 | 227 | 1691 | 45927 | 8019 | 7325 | 9814 | **71.9** |
| MOVE, 9 ports | 9 | 225 | 1606 | 45452 | 13784 | 7329 | 10743 | 78.7 |
| + AND OR XOR SHR | 14 | 235 | 1711 | 47497 | 9546 | 7280 | 10333 | 75.2 |

**Two memory-mapped ports take SUBLEQ from 164,783 gates to 8,848 — 18.6x
smaller, and 19.7x better on area x time.** It goes from 67x worse than the best
design to 1.25x worse on gates.

So the "23x gap between two one-instruction machines" reported in phase 5 was
almost entirely an *addressing* gap, not an instruction-set gap. The objection
was right, and correcting it costs the earlier conclusion.

## What survives the correction

SUBLEQ is still **4.35x slower in cycles** (44,953 against 10,333), which is
5.4x worse on area x time. That part is genuine and not about addressing at all:

* three words per instruction, so every operation costs five memory accesses;
* no native comparison, so `jn` is five instructions and `jz` is five;
* no native add, so `a += b` is three.

Those are properties of the instruction itself. Wiring up ports cannot fix them,
and this is the residue of the phases 1-3 result that remains true.

## The finding that replaces the old one

Sorting the whole field by gate count produces two clusters, and the boundary is
not where the instruction count changes:

| | gates |
|---|---|
| **cannot index without self-modifying code** | 47,295 – 164,783 |
| **can index without self-modifying code** | 7,078 – 8,848 |

Every design in the cheap cluster is within **25%** of every other, and they
range from 3 operations to 14. Every design in the expensive cluster is at least
**5.3x** more expensive than the whole cheap cluster, and they range from 1
operation to 7.

The dominant variable in this entire study is a single binary property: **can the
machine compute an address without writing into its own program?** If yes, the
program is read-only, lives in ROM at ~4 gates/word, and the machine costs
7-9k gates. If no, the program is writable, lives in RAM at ~196 gates/word, and
the machine costs 47-165k. Everything else — the instruction count, the
encoding, whether the opcode lives in its own field or in an address — is a
sub-25% effect on top of that.

SUBLEQ's famous inefficiency was never really about having one instruction. It
was about having no way to touch an array.

## A closing note on what "one instruction" means

Both surviving OISCs here reach their performance by making address decoding do
the work that an opcode would otherwise do. In the MOVE machine that is the whole
architecture; in ported SUBLEQ it is two addresses. Once a machine is competitive,
the instruction count has stopped describing anything real about it — which is
probably the most useful thing this project has to say about OISCs.

---

# Phase 7: searching the space instead of choosing from it

## The objection

Every design compared in phases 1-6 was one I picked, and the ones I picked are
the branches that historically existed: SUBLEQ, an accumulator machine, a
PDP-8-alike, Jones's MOVE machine. A model that has read the history of computer
architecture proposing those four and then announcing which one wins is not
running a search. It is recalling an answer and dressing it as an experiment.

Raised by a reader, and correct. The response is not an argument, it is code.

## What is mechanical now

**The instruction pool is enumerated, not curated.** It is the cross product
{LD, ADD, SUB, AND, OR, XOR} x {direct, immediate, indexed}, plus store in two
modes, plus a branch for every one of the six ways to test the outcome classes
{negative, zero, positive}, plus index and shift instructions. 31 candidates.
Nothing is in the pool because a real machine had it and nothing is out because
none did.

**Code generation is a search.** For every virtual operation, a breadth-first
search over instruction sequences, verified on random test vectors. There are no
hand-written macro expansions at all. Branch sequences are found by covering the
required outcome classes with whatever conditional jumps the candidate set
happens to contain.

**The Verilog is generated from the instruction list**, so the decoder matches
the set exactly, and is synthesised for real.

**The starting points are rejection-sampled.** Random 16-instruction subsets are
drawn and thrown away until one can run the benchmark, which happens about 5% of
the time. Then local search adds, drops and swaps single instructions.

## The compiler reproduces the hand-written code

The first useful result is a control: given the phase 4 instruction set, the
search-based compiler emits exactly the sequences I wrote by hand in phase 3.
`mov` is `LD_D s; ST_D d`. `add` is `LD_D d; ADD_D s; ST_D d`. Given a set with
no ADD it finds, unprompted, the six-instruction
`LD_D Kz; SUB_D d; ST_D t0; LD_D s; SUB_D t0; ST_D d` — the a + b = a - (0 - b)
expansion I had written by hand. Given a set with JN and JNN but no JZ it
correctly reports that the set cannot isolate the zero case and is unusable.

It also caught two bugs in my own abstract machine: it was exploiting an
accumulator initialised to zero on entry, and it was clobbering the destination
before the final store, which breaks at the `add p,p` call site in the suite.
Both fixed before any search was run.

## Calibration

The search prices memory from the per-word figures measured in phases 1-4 and
synthesises each candidate core for real. Against three designs measured
end-to-end in phase 4:

| design | model | measured | cycles model | cycles measured |
|---|---:|---:|---:|---:|
| 10-instruction winner | 6,846 | 7,078 | 10,345 | 10,333 |
| 7-instruction | 50,120 | 49,477 | 11,025 | 11,013 |
| 5-instruction | 59,706 | 59,125 | 14,885 | 14,873 |

Cycles within 0.1%, gates within 3%.

## Results, twelve restarts

| gates | n | cycles | scheme | instruction set |
|---:|---:|---:|---|---|
| **6,771** | **8** | 13,185 | reg | JN JZ LDX_D LD_D LD_X ST_D ST_X SUB_D |
| 6,782 | 9 | 13,185 | reg | + SUB_X |
| 6,845 | 11 | 10,345 | reg | ADD_D JMP JN JZ LDX_D LD_D LD_X ST_D ST_X SUB_D SUB_X |
| 6,883 | 11 | 10,665 | reg | ADD_D ADD_X JMP JN JP LDX_D LD_D LD_X ST_D ST_X SUB_D |
| 6,887 | 10 | 10,665 | reg | ADD_D JMP JN JP LDX_D LD_D LD_X ST_D ST_X SUB_D |
| 6,910 | 12 | 11,053 | reg | ...JNN instead of JN... |
| 50,118 | 8 | 11,025 | patch | ADD_D JMP JN JZ LD_D ST_D SUB_D SUB_X |
| 50,120 | 7 | 11,025 | patch | ADD_D JMP JN JZ LD_D ST_D SUB_D |
| 59,367 | 10 | 12,226 | patch | ...LD_I instead of LD_D... |

Three things fall out.

**The two-group split is reproduced, not assumed.** Every run that chose the
index-register scheme landed between 6,771 and 6,910 gates; every run that chose
self-patching landed between 50,118 and 59,367. The search found the boundary
that phases 3-6 argued for, without being told it existed.

**My hand-designed machine is a local optimum, and the search finds it.** The
third row is the phase 4 winner plus `SUB_X`, at 6,845 against the model's 6,846
for the phase 4 set itself. Independent confirmation that the hand design was
not wrong.

**And it proposed a machine I would not have.** The best set found by the model
is eight instructions with **no ADD and no JMP** — every historical accumulator
machine has both, and I never questioned including them. By the search's own
cost model that set is 1.1% smaller than the hand design.

## The pool was not as mechanical as claimed

I wrote that the pool contained "a branch for every one of the six ways to test
the outcome classes". There are seven, and the one I omitted was
branch-if-not-positive — SUBLEQ's own condition. The arithmetic slots were
filled with the operations real accumulator machines have. Both are exactly the
pattern-narrowing the objection predicted.

Corrected: the missing branch, plus two primitives no accumulator machine used —
reverse subtract (`acc = m - acc`) and NAND, in all three addressing modes. Pool
of 38.

## Uniform random sampling, no hill climbing

About 8,800 draws of a uniformly random size and a uniformly random subset; 129
of them can run the benchmark. They fall into the same two groups as phase 3,
now by random draw rather than by my choice:

| | modelled gates | count |
|---|---|---:|
| index-register machines | 7,505 – 7,900 | 4 |
| self-patching machines | 50,755 – 87,715 | 125 |

Nothing landed between. Reverse subtract appears in all four of the best random
machines, which is what prompted the local search to be re-run over the larger
pool.

## Measured: the search wins

Two errors in my own tooling had to be fixed first, and both flattered the
answer I already had.

* The search's cost model priced program words at the ROM *average* of 4.3
  gates. The marginal ROM word is about 1.8 gates and a data word about 200, so
  the model mis-ranked candidates whose programs were longer.
* The emitter allocated a scratch variable that no generated code referenced — a
  200-gate penalty applied only to searched machines, since the hand-written
  assembly did not use it.

With both fixed and every machine compiled by the same automatic pipeline:

| machine | gates | cycles | core | code words |
|---|---:|---:|---:|---:|
| phase 4 hand design | 7,161 | 10,332 | 1,508 | 200 |
| 8 instructions, no ADD or JMP | 7,168 | 13,172 | 1,287 | 235 |
| **RSB machine** | **6,959** | 11,656 | 1,332 | 219 |

The winner is `JN JZ LDX_D LD_D LD_X RSB_D RSB_X ST_D ST_X XOR_D XOR_X`: **no
ADD, no SUB, no JMP.** Reverse subtract does the work of both arithmetic
instructions. The compiler emits `a + b` as `LD d; RSB Kz; RSB s; ST d` — load,
negate against zero, reverse-subtract — and `a - b` in three instructions with no
SUB in the machine. Unconditional jumps are `LD Kz; JZ`.

2.8% smaller than the hand design through the same compiler, 1.7% smaller than
the hand-assembled version of it (7,078), and 13% slower. ROM synthesis varies
by about 50 gates with content, so the margin is real but modest — roughly two
to four times the noise.

The two XOR instructions in the winning set are never used by any template: the
climb stopped at a local optimum with dead weight in it. Removing them gives
6,966, which is inside the noise, so the trim neither helps nor hurts measurably.

## The objection was right

A machine built around reverse subtract, with no add, no subtract and no
unconditional jump, resembles nothing in the historical record. It is smaller
than the design I reached by recognising a PDP-8. The reader who said a model
with the history of computer architecture in its weights would not search but
recall was correct, and it took a mechanically enumerated pool — including two
primitives chosen precisely because no real machine had them — to get past it.

## What is still biased, stated plainly

* **The skeleton.** One accumulator, an optional index register, memory
  operands, a single-port synchronous memory, a 16-bit word and a 4-bit opcode
  field. The search explores instruction sets within that frame; it does not
  question the frame. A stack machine, a two-address machine or a transport
  architecture cannot be reached from here.
* **The two array-access strategies.** An index register and in-place patching
  are both offered to every candidate, and the search picks between them by
  cost. It did not invent either.
* **The benchmark and the memory model**, unchanged from phase 3, with the
  qualifications already recorded.
* **The search is local**, from rejection-sampled starts. Twelve restarts over a
  space of C(31, <=16) subsets is sampling, not exhaustion.

The honest summary is that this moves the work from "I compared four machines I
already knew about" to "I searched a mechanically enumerated instruction space
within an architecture I chose." That is a real improvement and a partial
answer. It is not a machine designed from nothing, and the sections above should
not be read as claiming otherwise.
