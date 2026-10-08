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

---

# Phase 8: putting the architecture in the search

Phase 7 searched instruction sets inside a skeleton I had chosen — one
accumulator, memory operands, one optional index register. That skeleton was
the last unexamined assumption, and it is the same class of assumption the bias
objection was about: one accumulator with memory operands is what nearly every
small machine has ever had, which is exactly why it needed testing rather than
assuming.

## What was generalised

Two structural axes, with the instruction pool regenerated for each point:

* **R**, the number of general data registers: 1, 2 or 3.
* **X**, the number of index registers: 0, 1 or 2.

For each `(R, X)` the pool contains every arithmetic operation in every
addressing mode targeting every register, a store from every register, every
branch condition testing every register, an index load and increment per index
register, and register-to-register moves when R > 1. Pool sizes run from 26 at
`(1, 0)` to 144 at `(3, 2)`. The compiler, the abstract machine it searches over
and the Verilog generator were all generalised to match; the generated RTL
compiles for every point tested.

**Control:** at `(1, 1)` with the phase 4 instruction set, the generalised
compiler emits exactly the phase 4 expansions — `LD0_D s; ST0_D d` for a move,
`LD0_D d; ADD0_D s; ST0_D d` for an add.

**Still fixed**, and why: 16-bit data words, because phase 4 measured that
storage cost is set by bits stored rather than by words; one memory port, one
word per instruction and the three-state skeleton, because they are constant
across every design in phases 1-8 rather than a variable; and the benchmark and
memory model.

## Results

Modelled gates. The model is the phase 7 one, which was shown there to mis-rank
candidates differing by less than about 3%, so small differences below are not
evidence.

| R | X | best modelled gates | cycles | index scheme |
|---:|---:|---:|---:|---|
| 1 | 0 | 52,271 | 11,591 | self-patching |
| 1 | 1 | 6,820 | 11,669 | index register |
| 1 | 2 | 6,772 | 13,185 | index register |
| 2 | 1 | 6,902 | 13,327 | index register |
| 2 | 2 | 7,319 | 10,948 | index register |
| 3 | 1 | 7,097 | 11,425 | index register |
| 3 | 2 | 50,640 | 11,025 | self-patching |

Across all 13 runs: every machine that could use an index register landed
between 6,772 and 7,319 gates; every machine that had to self-patch landed
between 50,640 and 56,749.

## What this supports

**More registers buy nothing.** Every point from one to three accumulators lands
in the same 6,772-7,319 band, which is inside the model's error. A second
accumulator costs sixteen flip-flops and wider decode, and the compiler cannot
remove enough program words to repay it — the same break-even arithmetic that
governs everything else in this project. The one-accumulator skeleton I assumed
in phase 1 and never questioned turns out to be right, and now on evidence
rather than on my say-so.

**A second index register buys nothing either.** `(1, 2)` and `(1, 1)` differ by
0.7%, well inside the noise.

**The index register itself remains the only thing that matters.** The 8x split
reappears at a third independent point in the space: architectures with an
index register 6,772-7,319, architectures without 50,640-56,749, nothing
between. This is now established from three separate directions — hand-designed
ladders, an instruction-set search, and an architecture sweep.

## What this does not support

The rows are modelled, not measured. The phase 7 lesson was precisely that this
model mis-ranks close candidates, so the ordering *within* the cheap band is not
a result. The honest statement is that R and the second X make no difference
that this method can detect, not that R=1 is optimal by 1.2%.

The two rows that land on self-patching at `(2, 2)` and `(3, 2)` are seeding
luck rather than architecture: a later restart at `(2, 2)` found an
index-register machine at 7,319. With more restarts those rows would move. They
are shown as run rather than quietly dropped, but they should not be read as the
cost of those architectures.

Sampling is the weak point throughout. Uniform random subsets are hopeless at
these pool sizes — the feasible fraction is well under one in a thousand at
`(3, 2)` — so starts were drawn by choosing a working register uniformly and
then one instruction uniformly per structural role, with local search free to
change anything afterwards. The roles are mine. That is a weaker guarantee than
phase 7's uniform sampling at `(1, 1)`, and it is the next thing to fix.

## The remaining assumptions

After this phase the fixed skeleton is: one memory port, one word per
instruction, a three-state fetch/execute/writeback machine, 16-bit data, and the
two array-access strategies. A stack machine, a two-address memory-to-memory
machine, a pipelined machine or a bit-serial datapath cannot be reached from
here. The MOVE machine of phase 5 was a hand-built probe into one of those
directions and lost by 3.5%; the others are untested.

---

# Phase 9: a stack machine, and how much bigger the task would have to be

Two questions from a reader: had I tried a stack machine, given that Forth
generates famously dense code; and would a bigger task change the answer.

## The stack machine

Phases 1-8 could not reach one. The compiler searched over register states and
the pool was built from `(operation x addressing mode x register)`; a
zero-address machine is outside that frame entirely.

`sw/stackmachine.py` adds it on the same terms as everything else: a
mechanically enumerated pool (25 candidates — every binary ALU operation, the
four standard stack shuffles, literal/load/store/fetch/store-indirect, every
branch condition, shifts), a compiler that searches breadth-first over stack
states rather than using hand-written postfix rules, and Verilog generated from
the instruction list and synthesised for real. The top D entries of the stack
live in registers; D is a parameter.

The compiler rediscovers postfix code unaided: `add d,s` comes out as
`LOAD d; LOAD s; ADD; STORE d`.

**Computed addressing is native.** `push base; push i; add; fetch` is how a
stack machine indexes, so it needs neither an index register nor self-modifying
code. It lands in the cheap cluster of phases 3-8 by construction — that is not
an empirical result, it is what the addressing model gives you for free.

### Result

| machine | gates | code words | cycles | core |
|---|---:|---:|---:|---:|
| stack, depth 3, with DUP/SWAP | 7,615 | 238 | 11,121 | 1,936 |
| stack, depth 3, Forth-ish set | 7,630 | 238 | 11,121 | 1,951 |
| stack, depth 4 | 7,909 | 238 | 11,121 | 2,230 |
| accumulator, phase 7 RSB machine | **6,747** | 253 | 11,669 | 1,158 |
| accumulator, phase 4 design | 6,846 | 235 | 10,345 | 1,334 |

**The stack machine loses by about 12%**, and the reason is not what the Forth
argument would predict. Its code is not denser: 238 words against 235 and 253.
Its core is 600-800 gates bigger, because three 16-bit stack registers and the
shifting multiplexers that push and pop them cost far more than one accumulator
and an 8-bit index register.

Going from depth 3 to depth 4 costs about 300 gates and buys nothing: no
expansion the compiler found needs more than three stack cells.

### Why the density did not appear

Two reasons, and both matter for reading the result.

**Half of a stack instruction still carries an address.** `LOAD`, `LIT`,
`STORE` and every branch need an operand field, so only the ALU operations and
shuffles are truly zero-address — 33 of 238 words, 14%. Packing those into
narrower words would save at most 142 gates, which does not change the ranking.

**Forth's density comes from factoring, not from the stack.** Threaded code is
dense because a word is a call to another word, and no machine in this project
has CALL or RETURN. This is therefore a stack machine without the mechanism
Forth is actually dense because of. That is a limit of the experiment, not a
verdict on Forth.

## How much bigger the task would have to be

The current benchmark cannot settle the density question, because code is only
13% of the winning machine's gates and data is 65%. Scaling the program while
holding data and per-operation density fixed:

| code size | stack | accumulator | winner |
|---|---:|---:|---|
| x1 | 7,615 | 6,902 | accumulator |
| x4 | 10,686 | 10,166 | accumulator |
| x12 | 18,873 | 18,869 | dead heat |
| x16 | 22,966 | 23,220 | **stack** |

**The crossover is at about 12x the current program — roughly 2,900 words of
code.** Below that the stack machine's larger core dominates; above it, its
6% density advantage compounds faster than the core costs.

That is an extrapolation, and its weak assumption is the one that matters: it
holds per-operation density constant. A program twelve times larger is exactly
the kind that would have repeated sequences worth factoring, and factoring is
where a stack machine's advantage actually lives. Adding CALL and RETURN to
both pools would change the slope, probably in the stack machine's favour, and
would move the crossover down.

## What was not built

The bigger benchmark itself — full-precision Fibonacci printed in decimal,
which phase 1 dodged by working modulo 2^16 — was specified but not
implemented. It would add multi-word arithmetic (and so make carry detection,
which no machine here has, suddenly worth instructions), unrolled code across
word positions, and repeated division for decimal output. The crossover
analysis above says what such a benchmark would have to reach before it changed
the ranking, which is the more useful half of the answer, but it is not a
substitute for running it.

Nor is CALL/RETURN in any pool, which is a third unexamined assumption to add to
the list — and the one most likely to matter for this particular question.

---

# Phase 10: a workload shaped like real firmware

The five-program suite was five textbook kernels. This one is the shape a small
embedded controller actually has: scan a buffer of samples, reduce it, checksum
it, format the results for a serial line. Sixteen samples; compute the wrapping
sum, the minimum and the maximum by indexed scan; compute a CRC-16 with
polynomial 0x1021, most significant bit first; print all four as five decimal
digits each, through **one subroutine called four times**. Twenty outputs,
verified against a directly computed model.

It differs from the old suite in three ways that turn out to matter.

## Finding 1: the phase 4 winner cannot do a checksum at any sensible cost

The CRC needs XOR. The ten-instruction machine that won phases 1 through 6 has
no logic operation at all, because **the old benchmark never needed one** — which
is why phase 2 concluded that AND, OR, XOR and shift were 202 gates of dead
weight.

That conclusion was a property of the benchmark, not of the instruction set. A
machine that cannot compute a checksum is not a practical controller, and
nothing in the first nine phases could see that.

| machine | on the firmware workload |
|---|---|
| phase 4 design (LDA STA ADD SUB JZ JN JMP LDX LDAX STAX) | no XOR; see below |
| phase 7 RSB machine, which has XOR | runs it |

To be precise rather than dramatic: XOR is not unreachable on a machine with
only add, subtract and branches — it can be synthesised bit-serially, testing
and shifting one bit at a time. But the CRC needs about 384 XOR operations, each
becoming roughly 128 virtual operations, so the checksum costs about 50x what it
should. The compiler rejects the machine because it cannot express XOR in
straight-line code; the honest statement is not "cannot run it" but "cannot run
it at a cost anyone would accept".

## Finding 2: CALL and RETURN pay for themselves

No machine in phases 1-9 had a subroutine instruction. The firmware workload
calls its decimal formatter four times, so a machine without CALL must inline
the body at every site.

Adding CALL and RETURN — a link register, one level deep:

| | code words | core gates | total | cycles |
|---|---:|---:|---:|---:|
| calls inlined | 326 | 1,226 | 8,058 | 30,092 |
| with CALL/RETURN | **160** | 1,405 | **7,523** | 30,100 |

**−166 words, +179 gates of core, −535 gates net.** This is the first
instruction group in the whole project that pays for itself once the program is
in ROM, and it does so because the thing it removes is not one word per site but
a whole 55-operation subroutine body, three times over.

Phase 3's break-even rule said an instruction is worth adding if it removes a
word of program per 196 gates it costs. In the ROM regime that bar became
impossible to clear — until an instruction arrived that removes code by the
hundred rather than by the word.

## Finding 3: the stack machine still loses, on the workload built to favour it

Phase 9 found the stack machine 12% worse and predicted the gap would close on a
code-heavy workload with subroutines, since factoring is where Forth's density
actually lives. The firmware workload is exactly that, and both targets now have
CALL and RETURN.

| machine | gates | code words | cycles | core |
|---|---:|---:|---:|---:|
| accumulator + XOR + CALL/RET | **7,523** | 160 | 30,100 | 1,405 |
| stack + XOR + CALL/RET | 8,355 | 179 | 30,204 | 2,155 |

It loses by 11%, essentially the same margin as before. The prediction was
wrong, and the reason is the one phase 9 already identified: `LOAD`, `LIT`,
`STORE` and every branch carry an operand field whatever the machine, so only
the ALU operations are genuinely zero-address. Factoring helps both machines
equally; it does not close a gap that comes from three 16-bit stack registers
costing more than one accumulator and an 8-bit index.

## What a practical machine looks like

Putting the three findings together, the shape that survives a realistic
workload is about **twelve instructions**:

```
LD  ST        load and store, direct
LDX LDAX STAX index register and indexed load/store
RSB           reverse subtract  (does the work of ADD and SUB)
XOR           for checksums
JZ  JN  JMP   branch on zero, on sign, always
CALL RET      subroutine, one level, via a link register
```

7,523 gates for the firmware workload, of which 5,400 is its own data. It is a
PDP-8 with a checksum instruction and a link register — which is to say, it is
close to what small controllers actually were.

## What this says about the earlier phases

Every phase before this one optimised against a benchmark that could not see
logic operations or subroutines. Two of the ten phases' conclusions are now
scoped rather than wrong: "logic instructions are dead weight" holds only for
workloads with no bit manipulation, and "past the ROM boundary instruction count
stops mattering" holds only for workloads with no repeated structure.

The benchmark, not the method, was the limiting factor — which is the same
lesson as phase 2's degenerate Fibonacci task, arriving a second time from a
different direction.

---

# Phase 11: aiming at the working set, and why a GA was not the tool

A reader asked whether genetic programming could find designs the directed
searches never considered, using crossover and mutation. Three measured
properties of this landscape argued against a plain genetic algorithm, and one
argued for aiming any search somewhere else entirely.

## Why a GA over instruction subsets is a poor fit

**Feasibility is vanishingly sparse.** About 1.5% of random 16-instruction
subsets of the 38-instruction pool can run the benchmark; under 0.1% at pool
size 144. Crossing two working machines usually produces a broken one, because
the halves do not each contain a store, a load and a branch that isolates the
needed outcome class.

**The landscape is nearly flat where it is feasible.** Every cheap-cluster
design measured across phases 7 to 10 spans 6,959 to 8,848 gates — 27% end to
end, standard deviation 7.8% of the mean, against a cost model that errs by
about 3%. There is very little gradient for selection to climb.

**The one feature that matters is a single bit.** Index-versus-no-index is worth
7x, and hill climbing finds it on the first move. Crossover does not discover
single-bit features; it recombines many-part structures.

The representational fix is real, though, and worth recording for anyone trying
this: **encode roles, not subsets.** A genome carrying a store slot, a load
slot, an arithmetic slot and a branch slot per outcome class — with the choice
*within* each slot evolved — keeps every individual feasible by construction.
Then crossover swaps meaningful parts instead of producing rubble.

## Where the money actually was

The budget at the optimum is core 21%, program in ROM 13%, data RAM 65%. Any
search over instruction sets is working on the small end. The data RAM is 23
words: 16 of array that the benchmark fixes, and seven program scalars.

Those seven are the only part an architecture can touch, and only one way: by
holding them in registers instead of memory. The choice of *which* to hold is a
subset problem with real epistasis, since `add v0,v1` only collapses to a single
instruction when both operands are pinned. That is genuine genetic-algorithm
territory — except there are seven scalars, so the space is 2^7 = 128 and can be
enumerated exactly. For this axis a GA would be solving a problem that fits in a
loop.

## The first answer was wrong, and the way it was wrong is the finding

Enumerated with cores taken from the existing per-register-opcode generator, the
answer came out at 4,786 gates against 6,917 — minus 31% on gates and minus 58%
on cycles, far outside the 12% ceiling I had predicted from the budget. A result
that much better than its own ceiling is a reason to check the measurement
rather than celebrate.

The cores were wrong. With per-register opcodes, eight registers needs 38
opcodes and a 4-bit opcode field allows 16, so the generator had silently
truncated the instruction set — and the set it synthesised for R=8 contained no
store instruction at all. The 967-gate "core" described a machine that cannot
write memory.

The correct encoding puts the register in a *field*: `{op[3:0], reg[2:0],
addr[8:0]}`, selecting into a register file. Synthesised honestly:

| registers | core gates | cost per added register |
|---:|---:|---:|
| 1 | 1,468 | — |
| 2 | 1,874 | 406 |
| 4 | 2,481 | 304 |
| 8 | 3,721 | 310 |

**An addressable register costs 300 to 400 gates. A word of this RAM costs 200.**
Moving a variable from memory into a register makes the machine bigger, not
smaller.

That is the answer to the working-set question, and it reverses the first one
completely:

| pinned to registers | gates | cycles |
|---|---:|---:|
| **none** | **7,053** | 10,402 |
| v2 | 7,151 | 8,942 |
| v0 | 7,173 | 9,773 |
| all seven | 7,540 | 4,384 |

The earlier figure of about 130 gates for a 16-bit register, from phase 2, was
for a *dedicated* register — an accumulator wired to one place. An element of an
addressable file needs a decoder, a read multiplexer and per-register write
enables, and costs two to three times as much. I had carried the dedicated-
register figure into a problem about addressable ones.

## What registers are actually for

They are not an area optimisation, they are a speed one. Pinning three variables
cuts cycles from 10,402 to about 6,900 for roughly 600 extra gates, which is 32%
better on area x time even though it is 6% worse on area alone.

That is worth stating plainly because it is the clean version of a thing this
project keeps rediscovering: **every structure here is cheap on one axis and
expensive on the other, and which one you are optimising decides the
architecture.** Registers buy time with area. ROM buys area with
inflexibility. The index register buys both, which is why it was the only
unambiguous win in eleven phases.

## So: is genetic programming worth it here?

Not for instruction subsets, for the three measured reasons above. Not for the
working set, which turned out to have 128 possibilities and a negative answer.

It would be worth it for one thing this project has not tried: evolving the
*semantics* of instructions as expression trees over `(acc, mem, constants)`
rather than selecting from operations I named. Reverse subtract is the existence
proof — it beat the hand design, and it only entered the pool because I added a
primitive no accumulator machine uses. There is no reason to think it is the
only such operation, and no human-curated pool will contain the ones nobody has
named.

The ceiling on that is bounded by the budget: the core is 21% of the machine, so
even a perfect instruction set caps out around a fifth. But a fifth is larger
than anything the last five phases found.

---

# Phase 12: evolving the instructions themselves

Phase 11 concluded that genetic programming was worth one thing this project had
not tried: evolving instruction *semantics* rather than selecting from
operations I had named. Reverse subtract was the existence proof — it beat the
hand design and only entered the pool because I deliberately added a primitive
no accumulator machine uses.

## The representation

Each ALU instruction is an expression tree over the accumulator and the operand,
built from `{+ - & | ^ ~ <<1 >>1}` and the constants `{0, 1, -1}`. Crossover
swaps subtrees between machines; mutation rewrites one.

Addressing and control stay structural — store, indexed store, index register,
indexed load, and branches on zero, sign and always. That is the fix for the
sparse-feasibility problem that made a plain genetic algorithm useless in phase
11: with the structural instructions fixed, **8% of random genomes compile**
against 1.5% of random instruction subsets.

**Control:** a genome hand-built as load, add, subtract reproduces the phase 4
machine exactly — 6,848 gates, core 1,332, 200 words, 10,345 cycles.

## What it found

Twenty individuals, fourteen generations, converged:

```
A0  acc <- (0 ^ m)                 = m          load
A1  acc <- ((0 + m) | (-1 & 0))    = m          load again
A2  acc <- ((m ^ m) + (-1 - m))    = ~m         load complement
A3  acc <- (m + a)                 = a + m      add
```

**It threw away the subtractor.** Having `~m` and an adder, the compiler
synthesises `d - s` as complement-and-add, and nothing in the machine subtracts.
The core falls from 1,332 gates to 1,205; the program grows from 200 words to
204; cycles rise from 10,345 to 10,515.

That is the same discovery as reverse subtract, reached without being handed the
primitive — which is the thing phase 11 said GP was for.

## And the result is below the resolution of the measurement

| machine | modelled gates | core | words | cycles |
|---|---:|---:|---:|---:|
| evolved, as found | **6,738** | 1,205 | 204 | 10,515 |
| the same, pruned to three slots | 6,750 | 1,217 | 204 | 10,515 |
| phase 7 reverse-subtract machine | 6,747 | 1,158 | 253 | 11,669 |
| phase 4 hand design | 6,848 | 1,332 | 200 | 10,345 |

The evolved machine is 1.6% below the hand design and **0.1% below the best
previously found**. The cost model errs by about 3% against measurement. So the
honest statement is not that GP found a better machine; it is that **GP found a
machine indistinguishable from the best one, by an independent route.**

The pruning test makes the resolution limit concrete. Slots A0 and A1 compute
the same thing, so removing one should save gates. It costs 12. That is
synthesis noise — a different opcode assignment lets ABC share differently — and
it is the same order as the differences the search is now chasing.

## Where that leaves the search

Eleven phases of searching the instruction set have converged on a band between
6,738 and 6,848 modelled gates, which is one and a half percent wide against a
model with three percent error. The remaining differences are not resolvable by
better search; they need a better cost function — per-candidate synthesised ROM
and RAM rather than per-word averages, which costs a few seconds per individual
instead of a few milliseconds.

That is the real stopping condition, and it is worth stating as the result
rather than as an apology. The instruction set stopped being the binding
constraint around phase 6. Everything since has confirmed it from a new
direction each time: a mechanical search, an architecture sweep, a stack
machine, a practical workload, the working set, and now evolved semantics. The
machine is memory, and the memory is the benchmark's.

---

# Phase 13: the clock period, which eleven phases assumed was constant

Fmax was measured once in this project, in phase 1, for two designs, and found a
28% spread. Every phase since compared machines by cycle count. That is only a
proxy for time if the clock period is the same across them, and there was a
specific reason to doubt it: the index register — the central finding of the
whole project — puts an adder in the *address* path, which is exactly what costs
Fmax.

Each machine wrapped with a memory, synthesised for an iCE40 HX8K, placed and
routed with nextpnr across six seeds. Seed spread is about 6.5%, standard
deviation about 2.4%, so differences below roughly 5% are not real.

| machine | Fmax (6 seeds) | cycles | wall-clock | by time | by cycles |
|---|---:|---:|---:|---:|---:|
| 7 instructions, no index | 93.8 ± 2.3 | 11,013 | 117.4 µs | **−5.6%** | +6.6% |
| phase-4 winner (index) | 83.1 ± 1.9 | 10,333 | 124.4 µs | 0.0% | 0.0% |
| phase-7 RSB machine | 84.1 ± 2.0 | 11,669 | 138.7 µs | +11.5% | +12.9% |
| stack machine, depth 3 | 89.2 ± 2.7 | 11,121 | 124.6 µs | **+0.2%** | +7.6% |
| phase-12 evolved | 92.5 ± 2.2 | 10,515 | 113.7 µs | **−8.6%** | +1.8% |

## The index register costs 11.5% of the clock

93.8 MHz without it, 83.1 with — an 8.8-sigma difference, far outside seed
noise. The hypothesis was right: the address-path adder lands on the critical
path.

This reframes the project's central finding rather than overturning it. The
index register buys a **7x reduction in area** and costs **11.5% of the clock**.
It is an area optimisation that costs time, which is the opposite of how index
registers are usually sold.

## Three conclusions change sign

**The seven-instruction machine.** By cycles it is 6.6% slower than the phase-4
winner. By wall-clock it is 5.6% *faster*. The whole of phase 2's ladder was
scored on cycles.

**The stack machine.** Phase 9 reported it 7.6% slower on cycles. On wall-clock
it is level — +0.2%, inside the noise. Its datapath has no address adder at all,
and it recovers on clock exactly what it loses on cycles. The conclusion that it
loses on *area* stands at 11%; the conclusion that it is also slower does not.

**The evolved machine.** Phase 12 reported it 1.8% slower on cycles and called
the gate difference below measurement resolution. On wall-clock it is 8.6%
*faster*, because throwing away the subtractor shortens the critical path:
92.5 MHz against 83.1. That is a 4.6-sigma difference and the clearest result in
the phase.

So the phase-12 machine is the best design the project has produced: tied on
gates with everything else in the band, and the fastest of the lot in real time.
Genetic programming found it, and the metric in use at the time hid most of its
advantage.

## What this says about the preceding eleven phases

Every area-times-time figure computed from phase 2 onward used cycles as if the
clock were constant. It is not, and the spread between these five machines is
13%, which is larger than most of the differences those figures were used to
argue about.

The gate counts are unaffected — they were measured, not assumed. What is
affected is every statement of the form "smaller but slower", and there are
several. The corrected version is usually milder: the designs that save gates by
removing datapath tend to *gain* clock, so the time penalty is smaller than the
cycle count suggests, and twice it reverses.

This is the third time in this project that a conclusion turned out to rest on
the measurement rather than on the thing measured — after the benchmark that
admitted a hardwired answer, and the benchmark that could not see logic
instructions. The pattern is consistent enough to be the most useful thing here:
**check what your metric cannot see, before trusting what it says.**

---

# Phase 14: the hybrid program store, measured at last

Phase 4 named this as the weakest assumption in the project and declined to
build it:

> The addresses a self-modifying program patches are fixed at assembly time, so
> the store could be split into ROM plus a handful of individually decoded
> writable words — five of them for the seven-instruction machine. At my own
> per-word figures that lands near 8,000 gates, inside the cheap group. I have
> not built it, so treat it as a sketch.

Built now. The overlay is N 16-bit registers, each with an address comparator,
multiplexed into the read path ahead of the ROM. Functionally it is
indistinguishable from RAM at those addresses, so the program verified in phase
3 behaves identically; only the area changes.

| writable words | memory gates | total | marginal cost per word |
|---:|---:|---:|---:|
| 0 (pure ROM) | 5,625 | 6,936 | — |
| 1 | 5,831 | 7,142 | 206 |
| 2 | 6,080 | 7,391 | 227 |
| **5** | **6,830** | **8,141** | **241** |
| 10 | 7,860 | 9,171 | 223 |
| 20 | 9,920 | 11,231 | 214 |

A writable overlay word costs about 220 gates — a 16-bit register plus a
comparator plus a mux leg, against 200 for a word of the ordinary RAM. That is
the number the whole thing turns on.

## The 6.7x gap is 1.15x

| store | seven-instruction machine | ten-instruction machine |
|---|---:|---:|
| monolithic: one RAM region for everything writable | 47,295 | — |
| monolithic: one ROM region, one RAM region | not eligible | 7,078 |
| **hybrid: ROM plus five writable words** | **8,141** | 7,078 |

The sketch estimated 8,000 and the measurement is 8,141, which is the one
satisfying part of a result that demolishes the headline figure.

**So the index register is worth 15%, not 570%.** Everything about the mechanism
survives: writable storage still costs about 220 gates a word against 4.3 for
read-only, and that ratio is still the largest single number in the project.
What does not survive is the claim that a machine which rewrites its own code
must pay for a writable *program store*. It pays for the words it actually
writes — five of them — because their addresses are link-time constants.

## What the article should say instead

The two-group structure was real but it was a property of the memory map, not of
the architectures. The defensible claim is narrower and, I think, more
interesting:

* Self-modifying code costs **one expensive word per patch site**, not an
  expensive program store. Five sites, about 1,100 gates.
* The index register removes those five words and 35 words of program, and is
  worth about 1,200 gates on a 7,000-gate machine — 15%, still the largest
  single instruction-set effect measured anywhere in this project.
* The 6.7x figure is what a *coarse* memory map costs you, and coarse memory
  maps are a design choice rather than a law.

## What is still not measured

The overlay puts a comparator and a mux leg in the memory read path, and phase 13
showed that path-length changes of this kind are worth 10% of the clock. The
hybrid store's Fmax has not been measured. Given phase 13, the expectation should
be that it costs some, and the honest position is that the 15% area figure has an
unmeasured timing penalty attached to it.

---

# Phase 15: searching the memory, where the gates actually are

Twelve phases searched instruction sets and converged into a band one and a half
percent wide. The budget had been saying why that was the wrong place to look
since phase 1, and decomposing the data RAM says it precisely:

```
23 words x 16 bits, gate-built
  flip-flops       2,304 gates   50%   irreducible: 368 bits of state
  decode and mux   2,293 gates   50%   a design choice
```

**2,293 gates is 32% of the whole machine** — against the 1.5% the
instruction-set searches were arguing over. Everything below is synthesised, the
same way every other figure here was.

| organisation | memory | whole machine | cycles | area x time |
|---|---:|---:|---:|---:|
| flat, registered read (current) | 4,597 | 7,078 | 10,333 | 73 |
| flat, combinational read | 4,501 | 6,982 | 10,333 | **72** |
| split: scalars and array separately | 4,612 | 7,093 | 10,333 | 73 |
| banked x2 / x4 / x8 | 4,839–4,851 | — | — | worse |
| **scalars flat, array in a ring** | **3,850** | **6,331** | 12,883 | 82 |
| everything in a ring | 3,421 | 5,902 | 55,730 | 329 |

## Three results

**Registering the read output costs 96 gates and buys nothing.** A combinational
read drops the 16-flip-flop output register. It is free, and it is 1.4% of the
machine. I have not retrofitted it: every published figure in this project was
measured with the registered version, and changing it would invalidate all of
them for 1.4%. It is recorded here as measured and left alone, which is the
honest trade.

**Banking and splitting do not help.** A two-level mux needs its own pipeline
register, and that costs more than the narrower mux saves. Splitting the scalars
from the array — which reads like it should help, since the array is only
addressed through the index register and the scalars only directly — comes out
15 gates worse. Both are the kind of idea that sounds right and measures wrong.

**A circulating store is the largest single win so far** — and phase 17 retracts this, because the storage element found in phase 16 is both cheaper per word and constant-time. Read the two together. Put the
sixteen array words in a ring that shifts past one port, with no decoder and no
mux at all, and the memory falls from 4,597 gates to 3,850: the whole machine
goes from 7,078 to **6,331, a 10.6% reduction**. Nothing found by searching
instruction sets across twelve phases came within a third of that.

It costs time, because an access waits for its word to come round: on the
benchmark's 340 array accesses, at an average wait of 7.5 cycles, 12,883 cycles
against 10,333 — 25% more. Putting *everything* in a ring saves 17% of the
machine and costs 5.4x the time, which is the wrong end of the same trade.

## What is measured and what is not

The areas are synthesised. The cycle figures are computed from the benchmark's
measured access counts and an average wait of (N-1)/2, not simulated.

**The machine that uses a ring has not been built.** A ring memory is not
functionally transparent the way the hybrid program store of phase 14 was: it
needs a `ready` line and the processor needs to stall on it, which is a change
to the state machine and costs gates I have not counted. Treat the 10.6% as the
memory's own measurement plus an unbuilt CPU change, not as a working machine —
and note that the last time this project reasoned about an unbuilt design, it
got both the area and the timing wrong in opposite directions.

The ring's Fmax is also unmeasured. Its critical path is flip-flop to flip-flop
with no decoder in it, so phase 13's logic suggests it would clock *faster* than
the mux it replaces, which would make the time cost smaller than the cycle count
implies. That is a guess until it is measured.

## Why this was the last place looked

The project spent twelve phases on 21% of the machine and one on the 65%. The
reason is worth naming: the instruction set is the part that looks like
architecture. Memory organisation looks like implementation, so it was treated
as a constant — and it was the only constant in the whole project that was
never questioned until the search had exhausted everything else.

---

# Phase 16: the storage element, which fifteen phases took as given

Every figure in this project counts a stored bit as a positive-edge-triggered D
flip-flop, six NAND gates. That convention is correct for a flip-flop. What was
never examined is whether a register file needs flip-flops at all.

It does not. An addressed RAM writes one word at a time, with the address stable
for the whole write, so there is no shift race and the cells can be
level-sensitive. A gated D latch is four NAND gates.

| 23 words x 16 bits, both with combinational read | combinational | cells | gates | per word |
|---|---:|---:|---:|---:|
| edge-triggered D flip-flop, 6 NAND | 2,293 | 368 | 4,501 | 196 |
| gated D latch, 4 NAND | 1,191 | 368 | **2,663** | **116** |

**1,838 gates, 26% of the whole machine, with no cycle cost at all.** Stable
across sizes: 116 gates a word at 23, 136 and 256 words, against 194–196 for
flip-flops.

## Only 40% of that is the storage element

The decomposition is the part worth keeping:

```
storage element    368 bits x (6 - 4)   =   736 gates
hold path          2,293 - 1,191        = 1,102 gates
```

An edge-triggered cell has to be told its own value when it is not being
written: `D = write ? din : Q`, a two-to-one multiplexer per bit, 368 of them. A
latch does not — it holds by not being enabled. **The majority of the saving is
not the cheaper cell, it is the multiplexer the cheaper cell makes unnecessary.**

That is why the combinational half of the RAM halves too, which is not what you
would predict from "4 gates instead of 6".

## What it changes, and what it does not

The ROM-to-RAM ratio falls from 45x to 27x. The mechanism the articles rest on
survives at a smaller magnitude, exactly as it did under phase 14's hybrid
store.

Scaling each machine's RAM portion by the measured 116/196:

| | flip-flop RAM | latch RAM |
|---|---:|---:|
| ten-instruction machine | 7,078 | 5,201 |
| seven-instruction, all-RAM store | 49,477 | 29,817 |
| seven-instruction, hybrid store | 8,141 | 5,785 |
| gap between the first two | 7.0x | 5.7x |

(The 7.0x here and the 6.7x quoted elsewhere differ because that one compares
against the cheapest machine on the other side rather than this one.)

For the ten-instruction machine specifically, taking both changes in order:

```
measured, registered read, flip-flops      7,078
combinational read instead                 6,982   -96
latch cells, no hold multiplexer           5,144   -1,838
```

So this is a large absolute result and a modest relative one — the best shape a
late finding can have, since every comparison in the project survives while
every machine in it gets about a quarter smaller.

## Not retrofitted, and why

Every published figure was measured with flip-flops, and the comparisons are
internally consistent. Re-measuring all of them would change forty numbers to
make each machine 26% smaller and leave every conclusion as it was. The figures
stay as measured, with the convention stated and this phase recorded beside it.

## Not verified

A latch-based file needs a clean write-enable: a glitch on the decode while the
enable is high corrupts a word, which is why synchronous design prefers
flip-flops and why this is a real engineering trade rather than free money. The
three-state machine here holds its address stable for the whole write cycle, so
it ought to be sound — but "ought to be sound" is not a simulation, and this has
not had one.

---

# Phase 17: the ring does not scale, and never won in the first place

Phase 15 called the circulating store "the largest single win in the project".
Phase 16, one phase later, measured a cheaper storage element. Asked whether the
ring scales with capacity, the answer turns out to retract phase 15's headline
rather than qualify it.

## Area per word is flat; time per access is not

| words | ring, flip-flops | addressed, flip-flops | addressed, latches | ring access |
|---:|---:|---:|---:|---:|
| 16 | 148/word | 193/word | 114/word | 8 cycles |
| 23 | 149/word | 196/word | 116/word | 11 cycles |
| 64 | 146/word | 194/word | 116/word | 32 cycles |
| 128 | 145/word | 194/word | 116/word | 64 cycles |
| 256 | 145/word | 194/word | 116/word | 128 cycles |

All three are linear in capacity with a flat per-word cost, so the ring's area
advantage over a flip-flop file neither grows nor shrinks. **What scales is the
access time**, at (N-1)/2 cycles: eleven at 23 words, 128 at 256, 512 at 1024.
On the benchmark's 340 array accesses that is 3,700 extra cycles at 23 words and
174,000 at 1024. The ring is a design for memories small enough that you do not
mind waiting for them, and nothing else.

## And it was never the cheapest, even at 23 words

**146 gates a word for the ring against 116 for a latch-addressed file.** The
ring loses on area too, at every capacity measured, while also being the only
one of the three with non-constant access time.

The mechanism is worth stating because it is not obvious. A ring stage cannot
use a latch — shifting requires edge triggering, or a two-phase clock and a pair
of latches per stage, which costs more than the flip-flop it replaces. So the
ring pays six gates a bit where an addressed file pays four. And it does not
even escape the multiplexer: each stage still needs one to choose between
shifting, holding and being written. It trades a shared decoder for a
distributed mux, keeps the expensive cell, and buys linear access time with the
difference.

## What this retracts

Phase 15's result stands as measured — a ring is 25% smaller than the
**flip-flop** file it was compared against — and that comparison is no longer
the relevant one. Against the storage element phase 16 found, the ring is
dominated outright: more area, more time, at every size tested.

So the project's best memory is the plainest one: an addressed file of gated D
latches with a combinational read, 116 gates a word, constant access time. The
exotic organisation lost to a cheaper cell in the ordinary one.

This is the second time in three phases that a structural idea measured worse
than the boring alternative, after banking and splitting in phase 15. The
pattern is consistent enough to be worth naming: **in this cost model, cleverness
in the organisation of memory keeps losing to cheapness in its unit.**

---

# Phase 18: why there is nothing left for a search to find in the memory

Asked whether genetic programming could find a better memory design still. The
honest answer is no, and the reason is measurable rather than a matter of taste.

**The space is small and now enumerated.** Flat, split by use, banked by two,
four and eight, circulating, registered and combinational read, flip-flop and
latch cells: eight organisations, all synthesised. Every exotic one measured
worse than the plain one.

**The remaining cost is two terms, and neither responds to reorganisation.**
Measured marginally, a word costs 64 gates of storage (sixteen latches at four)
plus 54 of decode and multiplexer — 116 in total, flat from 1 word to 32.

**The multiplexer is already at the tool's floor.** Writing it out explicitly as
a one-hot AND-OR tree, rather than letting synthesis infer it from `mem[addr]`,
produces 1,196 gates either way — identical to the gate. There is no slack to
recover by writing better RTL, so there is nothing for a search over RTL shapes
to find.

**And bit-serial access, the one structural idea left, measures worse.** Reading
and writing the same 368 bits one at a time costs 3,496 gates against 2,668.
The reason is worth keeping, because it is the general rule the whole phase
reduces to:

```
a multiplexer costs about one 2:1 cell per INPUT bit,
regardless of how its outputs are grouped

  23:1 over 16-bit words   368 inputs, 16 outputs   16 x 22 = 352 cells
  368:1 over single bits   368 inputs,  1 output         367 = 367 cells
```

Identical. Serialising the datapath does not shrink the multiplexer at all — it
only makes the write decode per-bit instead of per-word, which is where the
extra 828 gates go.

## What the memory costs, finally

**7.25 gates per stored bit:** four for the latch, 3.25 for its share of the
multiplexer. Both scale with the number of bits stored and neither with how
those bits are arranged.

So the only remaining lever on memory is **storing fewer bits**, which is not a
hardware search at all — it is a question about what the program needs, and
phase 4 already measured that storage cost is set by bits rather than words.

## When a search would have been the right tool, and why not here

Genetic programming earned its place in phase 12 because the space of
instruction semantics was large, non-obvious, and had the property that useful
operations existed which no curated pool would contain. None of those hold here:
eight organisations is not a space, the cost decomposes into two terms with
known mechanisms, and the one genuinely non-obvious structure anyone has
proposed — the ring — was measured and lost.

The useful general form: **search where the space is large and the mechanism is
unknown; measure where it is small and the mechanism is understood.** Four
phases of memory work ended with the plainest possible design, and the value was
in the measurements that ruled the alternatives out.

---

# Phase 19: the same machine built from transistors, diodes and resistors

Asked what changes if the machine is built from discrete parts rather than NAND
gates, and which logic family is cheapest. This is a second cost model over the
same designs, and it moves things the gate model could not see.

The structures below are textbook, stated as a convention the way the six-NAND
flip-flop was, not measured here. Prices are bulk hobbyist figures.

## One gate, one stored bit, one ROM bit

| family | a 2-input gate | parts | cost |
|---|---|---:|---:|
| RTL — NOR, one transistor and one base resistor per input, one pull-up | 2T 3R | 5 | $0.052 |
| DTL — diode AND into a transistor inverter | 3D 1T 3R | 7 | $0.056 |
| CMOS — discrete MOSFETs | 2 n-ch 2 p-ch | 4 | $0.160 |

| family | a gated D latch | parts | cost |
|---|---|---:|---:|
| RTL | 8T 12R | 20 | $0.208 |
| DTL | 12D 4T 12R | 28 | $0.224 |
| CMOS | 3 n-ch 3 p-ch | 6 | $0.240 |

And a ROM bit, in any family, is a diode where the bit is one and nothing where
it is zero: **half a component on average, $0.004.**

## Which family

| | parts | cost |
|---|---:|---:|
| RTL | 20,377 | **$201** |
| DTL | 26,871 | $214 |
| CMOS | **12,690** | $374 |

**RTL if you are buying the parts; CMOS if the constraint is how many parts you
can physically place.** CMOS needs a third of the components and costs nearly
twice as much, because a p-channel MOSFET is two and a half times the price of
an NPN transistor. DTL loses on both counts and is only worth it for the fan-out
and noise margin that this model does not price.

That ordering is also the historical one: discrete machines were built from RTL
and DTL precisely because, as the Wikipedia article on RTL puts it, in circuits
using discrete components the transistors were the most expensive part.

## The finding this project is about gets stronger

A stored bit against a ROM bit:

| | count ratio | cost ratio |
|---|---:|---:|
| gate model, flip-flops | 46x | — |
| gate model, latches | 27x | — |
| **discrete RTL** | **40x** | **52x** |
| real silicon, SRAM against flash | 6x | — |

So the thing the index register buys — permission to keep the program in
read-only storage — is worth *more* with discrete parts than with gates, and far
more than on silicon. A diode matrix is the cheapest storage anyone has ever
built, and a discrete flip-flop is among the most expensive.

## But the balance inside the machine inverts

| RTL, ten-instruction machine | parts | cost | share |
|---|---:|---:|---:|
| processor core | 8,875 | $92.30 | 46% |
| data RAM, 23 words | 7,360 | $76.54 | 38% |
| program ROM, 212 words | 3,620 | $28.05 | 14% |

In the gate model the data RAM was 65% of the machine and the core 21%. Here the
core is the largest item. The reason is the multiplexer: in gates it was half
the cost of the RAM, and in a discrete build it is a diode matrix — 368 diodes
and a handful of resistors, under $4 — so the RAM collapses to just its latches.

**That reverses the project's own conclusion about where to look.** Twelve
phases of instruction-set search were fighting over 21% of a gate-built machine.
In a discrete build they would be fighting over 46%, and the phase 12 result —
the evolved machine with no subtractor, whose core is 20% smaller — would be
worth about 9% of the whole build rather than the fraction of a percent it was
worth in gates.

## What this model does not price

RTL's fan-out is poor and its noise margin is small, so a real build needs
buffering that is not counted here; this is the main reason DTL was worth its
extra parts. Diode matrices need pull-downs and are slow to rise, which at the
sizes above would matter. And nothing here is measured — these are textbook
structures and catalogue prices, which is a weaker footing than the rest of this
project and should be read as such.

---

# Phase 20: capacitors

Asked whether the memory could be made from capacitors. It can, it is the
cheapest writable storage in this model, and the idea is older than the thing it
is now called.

**The Atanasoff–Berry Computer did it in 1942.** Its memory was a pair of drums
of 1,600 capacitors each, rotating once a second, with the charge rewritten on
every rotation. Wikipedia's term for it is *regenerative capacitor memory*, and
DRAM, twenty-four years later, is the same idea with the drum removed. So this
is not a modern trick retrofitted to a discrete build — it is what the first
electronic digital computer used, for exactly the reason it is attractive here.

## The cells

| cell | parts per bit | total parts | cost | what it needs around it |
|---|---:|---:|---:|---|
| RTL gated D latch (phase 19) | 20 | 7,360 | $76.54 | nothing — it is static |
| 4T DRAM, cross-coupled | 4 | 1,532 | $50.16 | refresh counter and timer |
| 3T DRAM plus an explicit capacitor | 4 | 1,532 | $42.80 | refresh counter and timer |
| **1T1C DRAM** | **2** | **924** | **$23.92** | refresh, and a sense amp per column |

**1T1C is 3.2x cheaper than the static latch file**, and the two intermediate
cells are worth knowing because they trade that saving for not needing a sense
amplifier. A 3T cell reads through its own transistor, so the stored charge
never has to be detected on a shared line — which with discrete parts is the
difficult bit, and the reason a hobbyist build would plausibly pay the extra $19
for 3T rather than fight a sense amplifier made of loose transistors.

Discrete capacitors help twice over, incidentally: a ceramic capacitor in the
nanofarad range holds far more charge than an on-chip cell of a few tens of
femtofarads, so retention is seconds rather than milliseconds and refresh is
nearly free in cycles.

## What it does to the machine

| discrete build | core | data RAM | ROM | total | core's share |
|---|---:|---:|---:|---:|---:|
| with static latches | $92 | $77 | $28 | $197 | 47% |
| with 1T1C DRAM | $92 | $24 | $28 | **$144** | **64%** |

A 27% cheaper machine, and the processor is now almost two thirds of it.

## The ratio, for the fourth time

| writable bit against read-only bit | ratio |
|---|---:|
| discrete, static RTL latches | 52x |
| gate-built, flip-flops | 47x |
| gate-built, latches | 29x |
| **discrete, 1T1C DRAM** | **16x** |
| real silicon, SRAM against flash | 6x |

Capacitor memory moves the discrete build from the expensive end of this table
towards the silicon end, which makes sense: it is the same cell silicon uses. The
finding survives at every point — read-only storage is always much cheaper than
writable — but the span across technologies is now nearly an order of magnitude,
from 6x to 52x, and any claim about *how much* the index register is worth has to
name which of these it assumes.

## And the project's own advice inverts completely

In the gate-built model the data RAM was 65% of the machine and twelve phases of
instruction-set search were fighting over 21%. In a discrete build with
capacitor memory the data RAM is 17% and the processor is 64%. **The same
project, run on a bench instead of in a synthesis tool, would have spent its
effort in almost exactly the opposite place** — and phase 12's evolved core,
twenty percent smaller, would be worth about 13% of the build rather than a
fraction of a percent.

Which is the general lesson of both cost models together: the question "where
should I look for savings" has no answer independent of what you are building
the machine out of.

---

# Phase 21: what clock a discrete build would actually run at

Asked what frequency is realistic for the discrete machine of phases 19 and 20.
The answer is grounded two ways: the critical path of this design is measured,
and real discrete computers give the per-gate delay.

## The measurement

Mapped to 2-input NANDs, the ten-instruction machine's **longest combinational
path is 43 gate levels**. For scale, the Megaprocessor's critical path is its
16-bit ripple adder at about 30 levels, and it runs at 20–50 kHz.

## What people have actually built

| machine | devices | clock |
|---|---|---|
| Megaprocessor | discrete NMOS, 2N7000 | 20 kHz, later 50 |
| MOnSter 6502 | discrete NMOS | tens to low hundreds of kHz |
| Spikeputor | discrete NMOS | 3.3 kHz (built for visibility, not speed) |
| **MT15** | **discrete bipolar** | **2 MHz** |

The gap is the whole story. Jesús Arias' analysis of the first two blames the
gate capacitance of discrete MOSFETs: the packaged transistors are physically
large, so their gates are large, and driving them through a pull-up resistor is
slow. Fixing it by shrinking the pull-ups twenty-fold would reach 1 MHz and
dissipate over a hundred watts. **Bipolar transistors are about forty times
faster in this application**, which is the same conclusion phase 19 reached on
cost — RTL is both the cheapest discrete family and the fastest practical one.

## This design, at 43 levels

| family | ns per level | logic path | logic-only clock |
|---|---:|---:|---:|
| discrete NMOS (Megaprocessor class) | 700 | 30.1 µs | 33 kHz |
| bipolar RTL, saturated, no speed-up capacitors | 250 | 10.8 µs | 93 kHz |
| bipolar RTL with speed-up capacitors | 60 | 2.6 µs | 388 kHz |
| bipolar non-saturating, ECL-style | 15 | 0.6 µs | 1.55 MHz |

The 33 kHz for discrete NMOS is a check rather than a prediction: it lands on
what the Megaprocessor actually achieves, from a path half again as long, which
is the right sort of agreement for a model this rough.

Saturated bipolar logic is slow for a specific reason — charge stored in the
base when the transistor saturates has to be removed before it turns off, and
that storage time dominates. A speed-up capacitor across the base resistor
shunts it out, which is why the family is sometimes written RCTL, and it is
worth roughly a factor of four.

## Then the memory

A discrete DRAM read drives a bit line loaded by every cell on it plus
centimetres of wiring, and that is often slower than the logic:

| bit line | pull-up | three time constants |
|---:|---:|---:|
| 30 pF | 1 kΩ | 0.1 µs |
| 50 pF | 2.2 kΩ | 0.3 µs |
| 100 pF | 4.7 kΩ | 1.4 µs |

Taking RTL with speed-up capacitors and a 50 pF bit line: 2.6 µs of logic plus
0.3 µs of memory, **about 340 kHz**.

## The answer

**150–400 kHz** for this design built from discrete bipolar transistors with
reasonable care, and **20–50 kHz** if built from discrete MOSFETs like the two
best-known examples. Getting to MT15's 2 MHz would need the critical path
shortened as well as the family chosen — 43 levels is a lot, and most of it is
the 16-bit adder's carry chain, which is exactly what a carry-select or
carry-lookahead structure exists to fix, at a cost in components this project
has not priced.

At 340 kHz the benchmark's 10,333 cycles take **30 milliseconds**, against 124
microseconds on the FPGA of phase 13. Three hundred times slower, for a machine
costing $144 in parts that you can watch working.

---

# Phase 22: what it would cost to build

Asked for the bill of materials three ways: discrete parts minimising component
count, discrete parts minimising money, and simple logic ICs. All twenty-four
discrete combinations of core, logic family and memory cell were costed.

Parts prices are bulk hobbyist figures and nothing here is a quotation. Board,
sockets and the several thousand solder joints are not priced at all, and for a
build this size they are the real cost.

## The two discrete optima are different machines

| | core | family | memory | parts | cost |
|---|---|---|---|---:|---:|
| **(a) fewest parts** | evolved, no subtractor | CMOS | 1T1C DRAM | **9,363** | $223.76 |
| **(b) lowest cost** | evolved, no subtractor | RTL | 1T1C DRAM | 11,316 | **$104.57** |

Two of the three choices agree, and one does not.

**Both pick the evolved core from phase 12** — the machine genetic programming
found, with no subtractor. In the gate-built model that core was worth a
fraction of a percent and sat below the measurement noise. Here it is worth
$14 of $118, because the processor is most of a discrete build.

**Both pick 1T1C capacitor memory.** Nothing else comes close: it is two parts a
bit where a static latch is twenty.

**They disagree on the logic family, and by a factor of two in money.** Discrete
CMOS needs 17% fewer parts and costs 114% more, because a p-channel MOSFET is
two and a half times an NPN transistor. DTL matches RTL on cost exactly and
needs 23% more parts, so it is only worth buying for the fan-out and noise
margin this model does not price.

If you are paying for parts, build it from bipolar transistors. If you are
paying for board area or solder joints, build it from MOSFETs — and accept, per
phase 21, that it will then run at 20–50 kHz instead of 150–400.

## Simple logic ICs

| build | ICs | passives | cost |
|---|---:|---:|---:|
| gate ICs throughout, memory included | 1,782 | — | $356.40 |
| gate ICs, memory as memory chips | **271** | — | **$59.74** |
| gate ICs, SRAM chip, diode-matrix ROM | 270 | 3,620 | $77.98 |

The logic itself is 251 of the 74HC00 quad NANDs and 17 of the 74HC74 dual
flip-flops: **$54 for the whole processor**.

The interesting row is the first. Building the *memory* from gate ICs costs
$303 of the $356 — six times the processor — which is the same finding this
project started with, in a fourth cost model. Two memory chips and an EEPROM
replace 1,514 ICs and $300.

## The answer

| build | parts | cost | clock |
|---|---:|---:|---|
| discrete, fewest parts | 9,363 | $224 | 20–50 kHz |
| discrete, lowest cost | 11,316 | **$105** | 150–400 kHz |
| logic ICs plus memory chips | 271 | **$60** | 2–10 MHz |

**About $105 in discrete transistors, or about $60 in 74HC parts** — and the IC
version is cheaper, smaller, forty times fewer parts, and an order of magnitude
faster. The discrete build is not an engineering choice; it is an aesthetic one,
and the figures say it costs roughly double for a hundredth of the performance.

Which is worth stating plainly because it is the honest end of the whole
exercise: the machine this project spent twenty-two phases minimising can be
bought as a $1 microcontroller that is ten thousand times faster. What the
exercise produced is not a cheap computer. It is a set of measurements about
where cost lives in one, and those turned out to transfer across four cost
models that disagree with each other about almost everything else.

---

# Phase 23: a mutation audit, borrowed from a neighbouring project

A reader pointed at a Habr article on running Niklaus Wirth's RISC5 processor —
the same genre as this project, built the same way, with agent reviewers and
agent auditors. Two of its methods were worth importing, and both have been run
here.

## Does the spelling of the Verilog change the gate count?

That project rewrote its processor four ways with logically neutral edits — extra
parentheses, an OR with zero — and found the area moved by about as much as the
feature it was trying to measure. They could honestly only report "less than one
percent".

That is a direct threat to this project, where everything rests on synthesised
gate counts and several comparisons are narrower than two percent. So it was
measured: the ten-instruction machine, rewritten seven ways that change nothing —
extra parentheses, AND with ones, OR with zero, double negation, a commuted
adder, a redundant wire, XOR with zero.

**All seven synthesise to 1,334 gates. Zero spread.**

The difference is the flow. That project measured standard-cell area against a
timing constraint, where the mapper's choices are sensitive to how the input is
written. This one runs `abc -g NAND`, which optimises technology-independently
and maps to a single gate type, so logically equivalent inputs converge on the
same netlist. The noise that invalidated their sub-one-percent claims does not
exist here, and that is now measured rather than assumed.

It does not cover everything. The ~50-gate variation seen in phase 12, when
removing a redundant instruction changed the opcode assignment, is
content-dependent rather than spelling-dependent, and that one is real.

## Do the checks catch broken hardware?

Their harsher finding: they injected thirty plausible bugs into their processor
and their tests caught ten. Two thirds of broken processors passed as healthy.

This project had shown one check could fail — the baseline, by corrupting a
recorded figure — but had never asked it of the RTL verification. So
`sw/mutate.py` injects eleven plausible slips: a swapped operator, an inverted
flag, a wrong bit field, a dropped write enable, an ignored index register.

First run: **8 of 10 caught**, and both misses were worth more than the eight.

**The test data was too kind.** The array base is 45 and the index was 2, and
45 | 2 = 45 + 2 = 47. A mutation replacing the index adder with an OR was
therefore invisible. Changing the index to 3 — where 45 | 3 = 47 and 45 + 3 = 48
— catches it. The verification had been passing partly by arithmetic
coincidence.

**The design states its branch condition twice.** The generated RTL writes
`zf ? iad : pc` once for the fetch address and once for the program counter
update. Mutating one of the two is invisible; mutating both is caught at once. A
bug in one of two mirrored expressions is a real blind spot, and the right
response is to note it rather than to fix the mutation.

After fixing the data: **10 of 11 caught**, with the remaining miss being that
mirrored-expression case, kept in the suite as a known gap rather than quietly
removed.

## What it cost to find out

Two experiments, both cheap, both borrowed. One confirmed that a threat to the
entire project does not apply to it, which is worth more than it sounds — that
claim had been assumed through twenty-two phases. The other found that a check
this project has leaned on since phase 7 was passing partly because 45 | 2
happens to equal 45 + 2.

The general form, which the other project states better than I would: if a check
has never gone red, you do not know what it checks.
