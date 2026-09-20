# Progress log

Chronological record of how this project was built, including tool installation,
dead ends, and bugs. Newest work at the bottom.

---

## Session 1 — 2026-09-13/14

### 1. Framing the question

Starting point: which is cheaper in gates and faster in wall-clock time, a SUBLEQ
OISC or a 4-instruction accumulator machine, for a Fibonacci program.

Decided early that this had to be *measured*, not reasoned about, because the two
plausible intuitions point in opposite directions: SUBLEQ has one opcode and no
architectural registers (suggests small), but a 3-operand instruction with 5
memory accesses (suggests slow and bulky). Both intuitions turned out to be
partly right.

Key methodological decision: hold everything constant except the instruction set
— same word width, same single-port memory, same 1-cycle read latency, same
amount of microarchitectural effort, same algorithm. Documented as "Fairness
rules" in `project.md`.

### 2. Choosing and installing tools

Surveyed the container first:

```
$ which iverilog verilator yosys ghdl nextpnr-ice40
(nothing)
```

Nothing preinstalled. Picked an open-source flow:

* **Icarus Verilog** — RTL simulation, for cycle counts. (Verilator would be
  faster but the benchmark is ~5000 cycles; compile time dominates, so iverilog
  is the better choice here.)
* **Yosys** — synthesis. This is the tool that actually answers the gate-count
  question: `abc -g NAND` maps a design to 2-input NAND cells and `stat` counts
  them.
* **nextpnr-ice40** — place-and-route, so "performance" includes critical path
  rather than just cycle count.

Installation:

```
$ sudo apt-get install ...        -> /bin/sh: sudo: not found
$ id                              -> uid=0(root)     # already root
$ apt-get update -qq && apt-get install -y -qq iverilog yosys
```

`apt-get update` emitted a 403 for an unrelated third-party nodesource repo;
harmless, the Ubuntu repos are reachable and both packages installed. Versions:
Yosys 0.33, Icarus Verilog present at /usr/bin/iverilog.

`nextpnr-ice40` (0.6) was installed later, once the designs simulated correctly
and it was worth getting real timing numbers.

Considered and rejected: Logisim Evolution / Digital (schematic-level, nice for
teaching but no automatic gate-count extraction and no timing), OpenLane/OpenROAD
(would give a real standard-cell area in um^2, but pulling a PDK is heavy for a
comparison that only needs relative numbers).

### 3. Software first: `sw/asm.py`

Wrote the assembler and reference emulator for both ISAs *before* any Verilog, so
that the RTL would have something to be checked against. This paid off later.

Design decisions made while writing it:

* **F(100) doesn't fit in 16 bits** (~3.5e20 needs 70 bits). Options were bignum
  arithmetic, a wider word, or modulo 2^16. Chose modulo — both machines do
  identical arithmetic so the comparison is unaffected, and bignum code would
  have buried the ISA difference under library code.
* **Unrolled the loop by 2.** The naive `t=a+b; a=b; b=t` needs two register
  copies per iteration, and a SUBLEQ copy is 3-4 instructions. Alternating
  `a += b; b += a` needs zero copies on either machine. Without this the result
  would have overstated SUBLEQ's cost.
* **Self-modifying store pointers.** Neither machine has indexed addressing, so
  both increment the address field of a store instruction in place. SUBLEQ gets
  this cheaply (`subleq m2, p1+1` with `m2 = -2` adds 2 in one instruction); the
  accumulator machine needs LOAD/SUB/STORE, 3 instructions.
* Accumulator encoding chosen as `{2'bx, op[1:0], addr[11:0]}` — 2 opcode bits is
  all four instructions need, and keeping the opcode narrow keeps the decoder to
  almost nothing.

First run:

```
ACC    : code=29 words  data=7  array=100  total=136  instr=1398  cycles=2697  ok=True
SUBLEQ : code=51 words  data=6  array=100  total=157  instr=799  cycles=4794  ok=True
first 10 fib: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
```

Both correct against a directly computed Fibonacci sequence on the first try.
Already informative: SUBLEQ runs 43% fewer instructions but 78% more cycles.

### 4. RTL: `rtl/acc_cpu.v`, `rtl/subleq_cpu.v`

Both written against the same memory contract: the CPU drives the address
combinationally, the RAM registers it on the clock edge, data is available the
*following* cycle. Both FSMs overlap the next instruction fetch with the last
cycle of the current instruction, so neither wastes a cycle the other doesn't.

Resulting schedules:

* accumulator — `S_D` (decode, drive operand address) then `S_E` (consume operand,
  update ACC, drive next fetch). LOAD/SUB/STORE = 2 cycles, JZ = 1 cycle.
* SUBLEQ — `S_F -> S_A -> S_B -> S_C -> S_VA -> S_VB`, 6 cycles: three words of
  instruction, read M[A], read M[B], subtract and write back.

One PC trick worth recording: SUBLEQ increments the PC during each of the three
operand fetches, so after `S_B` the PC already equals `instr+3`, the fall-through
target. That means the design needs only a `+1` incrementer, the same as the
accumulator machine, rather than a `+1/+2/+3` adder. Without this SUBLEQ would
have looked artificially worse.

**Bug found and fixed:** the accumulator CPU's reset dropped straight into the
decode state, where `mdin` is undefined — it would have decoded garbage as its
first instruction. Fixed by resetting into state `2'd3`, which shares the
"drive address = PC, this is a fetch" path with `S_W`, so the fix cost zero
extra logic.

### 5. Testbench and simulation

`rtl/tb.v` instantiates *both* computers side by side with their own RAMs and
runs them concurrently, so the cycle counts come from a single simulation and
can't drift apart through setup differences. Halt is detected by watching for an
instruction fetch from a known address — deliberately not an instruction, so
neither machine pays gates for it. The array contents are then compared against
`expected.txt` written by the Python model.

```
$ iverilog -g2012 -o sim tb.v acc_cpu.v subleq_cpu.v && ./sim
ACC    : 2698 cycles, 1398 instructions
SUBLEQ : 4795 cycles, 799 instructions
verification: 0 errors
```

RTL matches the emulator exactly (the +1 cycle on each is the final halt fetch).
Both machines produce F0..F99 correctly. No RTL bugs beyond the reset issue.

### 6. Gate counting — three iterations to get it right

**Attempt 1.** `synth -top X -flatten; abc -g <gates>; stat`. Output looked
plausible but the flip-flops came back as `$_SDFFE_PP0N_` — D flip-flops with
both a clock enable and a synchronous reset baked in, counted as *one cell each*.
That silently hides the enable multiplexer and reset gate inside a "1", and the
two designs have different numbers of enables, so the comparison was unfair.

**Attempt 2.** Added `dfflegalize -cell $_DFF_P_ 0` to force every flip-flop down
to a plain D type and push the enable/reset logic out into visible gates. The
`$_SDFFE_*` cells were still there afterwards. Cause: the `opt -full` that ran
*after* `dfflegalize` includes `opt_dff`, which cheerfully re-absorbs the enable
and reset logic back into the flip-flops, undoing the normalisation.

**Attempt 3.** Moved `dfflegalize` to immediately before `abc`, with only
`opt_clean` after it (which removes dead cells but does not re-merge flip-flops).
This worked:

```
acc:     31 DFF,  428 NAND + 192 NOT
subleq:  67 DFF,  537 NAND + 222 NOT
```

Counting a NOT as one NAND and a DFF as 6 NANDs: **806 vs 1161 NAND-equivalents,
SUBLEQ 1.44x larger.** Cross-checked against a richer gate library
(AND/OR/XOR/MUX/ANDNOT/ORNOT): 344 vs 439 cells, same 1.28-1.44x direction.

The flip-flop count (31 vs 67) was the moment the result became clear: the area
difference is *sequential state*, not datapath. SUBLEQ has to buffer A, B, C and
M[A] across one instruction.

Confirmed from the other direction by mapping to iCE40 logic cells: **109 vs 108
LUT4s** — the combinational logic is essentially identical, because both designs
contain exactly one 16-bit subtractor. Only the flip-flop count differs (33 vs 70).

### 7. Program store as gates

Realised the CPU core is the wrong thing to be comparing in isolation: the
question was about building a whole computer from gates, and the program store is
part of that. Wrote `rtl/ramg.v`, a plain register-file RAM, and ran it through
`memory_map` + the same NAND mapping, sized to each program's actual footprint
(136 and 157 words x 16 bits):

```
136x16:  2192 DFF, 11776 NAND + 1672 NOT  -> 26600 NAND-equivalent
157x16:  2528 DFF, 13592 NAND + 1920 NOT  -> 30680 NAND-equivalent
```

This reframed the whole result: the CPU core is **~3% of the gate budget**. What
dominates is memory, and therefore code density — which is precisely where
SUBLEQ's 3-words-per-instruction encoding hurts. Whole-computer totals: 27406 vs
31841, SUBLEQ 1.16x larger.

### 8. Real timing, not just cycles

Cycle counts alone can't answer "which is faster" — SUBLEQ's longer critical path
had to be measured. Installed `nextpnr-ice40`, wrote `rtl/top.v` wrapping each
CPU with an inferred 1024x16 block RAM, synthesised with `synth_ice40` and placed
and routed on an HX8K across 4 seeds:

```
top_acc routed Fmax: 111.66  101.43  103.71   95.40 MHz   (mean ~103)
top_sub routed Fmax:  78.06   72.33   72.04   74.33 MHz   (mean  ~74)
```

Ran multiple seeds deliberately — a single P&R run has enough placement noise to
be misleading, and the spread (95-112 vs 72-78) shows the gap is real and not
seed luck. SUBLEQ is 28% slower per clock; its critical path is
subtract -> compare-to-zero -> PC mux -> address mux -> RAM address.

**Final answer: 2698 cycles @ 103 MHz = 26.2 us, versus 4795 cycles @ 74 MHz =
64.6 us. The accumulator machine is 2.47x faster.**

One gotcha: `grep`ping nextpnr output for "Max frequency" catches both the
post-placement estimate and the post-routing number, and also the target
frequency echoed in the FAIL message. Had to take the *last* match and strip the
target to get the real routed figure.

### 9. Biases audit

Before writing up, went looking for ways the setup could be unfairly tilted, and
recorded both directions in `project.md`:

* *Against SUBLEQ*: the single 16-bit port. With a 48-bit instruction fetch,
  SUBLEQ would drop to ~3 cycles per instruction (~2400 cycles) and would win on
  cycle count. It would not win on system gates, because the wider memory costs
  more than the core difference saves.
* *Against the accumulator machine*: the 4-instruction set has no `ADD` and no
  unconditional `JMP`, so `a += b` costs six instructions and every unconditional
  jump costs two. Adding both would roughly halve its cycle count for ~40 gates,
  which makes the measured 2.47x a floor rather than a ceiling.

### 10. Repository setup

Restructured the flat working directory into `rtl/`, `sw/`, `synth/` with a
`Makefile` that reproduces every published number, plus `project.md` and this log.

Issues hit while doing it:

* Moving sources into `rtl/` broke every hardcoded path: the Yosys scripts'
  `read_verilog`, the testbench's `` `include "params.vh" `` and its three
  `$readmemh` calls. Fixed by pointing generated artefacts at `build/` and
  sources at `rtl/`, and having `sw/asm.py` create `build/` itself.
* `yosys -p "read_verilog -DNWORDS=136 ..." -s script.ys` does **not** run the
  `-p` command before the `-s` script — the script ran first and died with
  "Module `ramg' not found". Replaced with `synth/gates_ram.sh`, which passes the
  size via `chparam -set N` inside a single `-p` chain.
* `/mnt/user-data/outputs` is mounted `noexec`, so `./build/sim` fails there with
  "Permission denied". The Makefile is correct; verification runs were done from
  a copy under `$HOME`. Worth knowing for anyone re-running in the same sandbox.
* Kept the RAM area model's address width at 8 bits (`ceil(log2(157))`) for both
  sizes, so the address-decoder cost is measured on equal terms.

Verified end to end from a clean tree: `make` reproduces the cycle counts, the
verification pass, and both gate counts; `make fmax` reproduces the frequencies.

### 11. Git

`git init`, `.gitignore` for `build/` and simulator/P&R artefacts, single initial
commit of the RTL, software, synthesis scripts, Makefile and documentation.

---

## Session 2 — 2026-09-14: design-space sweep

### 12. Realising the benchmark was measuring the wrong thing

Divided the phase 1 RAM numbers by word count before starting anything else:
26600/136 and 30680/157 both give **~196 NAND-equivalents per 16-bit word**,
consistent to 0.1%. Two consequences fell out immediately:

* the 100-word output array is 19,560 gates — **71% of the whole computer**, and
  completely insensitive to the instruction set;
* one word of program is worth 24% of the entire V1 CPU core, so almost any
  instruction that removes a word of code pays for itself.

The first point means phase 1's benchmark could not answer the question being
asked. Replaced the output array with a 16-bit memory-mapped output port
(register + strobe, one address past the last RAM word), placed inside the
synthesised core so every design point carries it equally.

### 13. One CPU, instruction groups behind ifdefs

Rather than write five CPUs and hope they were equally well designed, wrote one
`rtl/cpu_acc.v` with `HAS_ADD`, `HAS_JMP`, `HAS_CTR`, `HAS_LOGIC` selecting
instruction groups at compile time. Every design point then provably shares a
microarchitecture and the ISA is the only variable. Yosys optimises away the
decode for absent opcodes, so the smaller variants are not carrying dead logic.

Added two endpoints beyond the ladder: `cpu_fib2`, a 2-register machine with no
data memory, and `fib_fsm`, the benchmark burned into a state machine with no
instruction set at all. Both exist to find where the optimisation actually
terminates.

Programs were re-optimised per ISA rather than transliterated. The V2/V3 loop
exploits the fact that after `STA a` the accumulator already holds the new `a`,
so `ADD b` computes the new `b` with no reload — 8 instructions for the loop
body instead of 11.

### 14. SUBLEQ needs a readable port

`subleq Z, port` computes `M[port] - M[Z]`, so a write-only port breaks the
machine. Defined reads of the port address as returning 0, which makes
`subleq a, Z; subleq Z, port` emit `+a`. In hardware that is one flip-flop and a
16-bit mux (~17 gates) because the RAM has a 1-cycle read latency and the mux
must be driven by the *previous* cycle's address. The alternative — clearing the
port in software with an extra `subleq port, port` per output — would have cost 6
extra words, about 1,200 gates. Cheaper in gates to fix it in hardware.

Also parameterised `subleq_cpu`'s address width, defaulting to 12 so the phase 1
flow still reproduces bit-for-bit.

### 15. Bugs

* `wire iff` failed to compile under `-g2012`: **`iff` is a reserved
  SystemVerilog keyword.** It had gone unnoticed in phase 1 because `top.v` was
  only ever read by Yosys, never by Icarus. Renamed throughout.
* `cpu_fib2` emitted only 3 of 100 values. Cause: the branch target was applied
  to `pc` at the clock edge, but the RAM had already latched the *old* `pc` that
  same cycle, so every taken branch executed one wrong instruction. Fixed by
  driving the branch target combinationally onto the address bus in the branch
  cycle — the same trick `cpu_acc` already used for JZ/JMP — which also makes
  taken branches cost zero bubble.
* Lost the RTL-simulation patch by editing the working copy instead of the repo
  copy and then overwriting it. Noticed because the printed cycle counts were
  emulator values, one lower than the RTL values. Reapplied cleanly, and added
  asserts so the run now fails loudly if RTL and emulator disagree by more than
  2 cycles or if any design emits a wrong value.

All seven design points now RTL-simulated, all verified against F0..F99, zero
mismatches.

### 16. First sweep: the curve turns up at 12 instructions

```
design                  ops  words   core  RAM-code   TOTAL  cycles
SUBLEQ                    1     50    807      9822   10629    4147
LDA STA JZ SUB            4     29    704      5719    6423    2067
+ ADD JMP                 6     18    887      3577    4464    1185
+ LDC DJNZ                8     13   1078      2600    3678     843
+ AND OR XOR SHR         12     13   1293      2600    3893     843
2-register machine        9      9   1071      1820    2891     252
hardwired FSM             0      0    884         0     884     150
```

The minimum is at 8 instructions. The 12-instruction variant is the control: its
four logic instructions are never executed by the program, so it adds 216 gates
of ALU and decode and saves nothing. That gives the break-even rule directly —
an instruction is worth adding only if it removes at least one word of program
per ~196 gates it costs.

### 17. The ROM lever, which turned out to be bigger than the ISA

Noticed that with the output array gone, **none of the programs self-modify any
more** — phase 1 only needed self-modifying code to walk the output pointer. So
the code does not need writable storage.

Wrote `rtl/memsys.v` (code ROM at `[0, NCODE)`, data RAM above it, registered
select) and had the sweep generate a `case`-statement ROM per program and
synthesise the whole memory subsystem as one block. Measured cost per word of
code:

```
RAM: 196-202 gates/word     ROM: 2.6-8 gates/word
```

25-70x cheaper, and it cuts every total by 2.4-5.6x. This is a larger effect than
the entire instruction set question, and it also *flattens* that question: with
code in ROM, SUBLEQ drops from 2.9x the best design to 1.25x, and actually comes
in cheaper than the original 4-instruction machine, because its core is smaller
and code density no longer dominates.

### 18. The degenerate result

The hardwired FSM is 884 gates and 150 cycles: 4.2x smaller and 5.6x faster than
the best programmable design. The 2-register machine at 1143 gates sits halfway
along the same road, with opcodes (`ADDBA`, `ADDAB`, `OUTA`, `OUTB`) that are
really a Fibonacci accelerator in disguise.

This is the honest answer to "which CPU design minimises gates for this task":
**none of them**, because a benchmark of one fixed program does not need a
program. Recorded this in `project.md` along with a proposed phase 3 benchmark —
a five-program suite (Fibonacci, insertion sort, multiply/divide, GCD, binary to
decimal) scored on area x time — and two rules that need fixing up front, since
each is worth more than the ISA choice: whether self-modifying code is allowed
(the ROM/RAM swing), and area x time rather than area alone.

---

## Session 3 — 2026-09-14: phase 3, the five-program suite

### 19. Write each benchmark once, not once per machine

Five benchmarks across five machines is twenty-five assembly programs to write
and debug, and worse, twenty-five chances to accidentally optimise one machine's
code harder than another's — which would silently become the result.

Instead defined a small memory-to-memory **virtual ISA** (`movi mov add sub addi
subi out jmp jz jn ldx stx halt`) and gave each target macro expansions for it.
Each benchmark is written once; every machine provably runs the same algorithm on
the same data. Verification is three-layered: the virtual program is checked
against a directly computed model, each target's expansion against its own
emulator, and each machine against RTL simulation.

### 20. Choosing algorithms that these machines can actually express

Several algorithm choices were forced by what the machines can do:

* **Multiply MSB-first.** The textbook shift-and-add tests the multiplier's low
  bit and shifts right, but none of these machines has a right shift. Testing the
  *high* bit and shifting left needs only `add x,x` and a sign test.
* **Restoring division the same way.** Division by 10 shifts the dividend left
  and pulls its MSB into the remainder, again avoiding any right shift.
* **`jn` rather than a comparison instruction.** All comparison in the suite is
  "subtract, test sign".

That last one has a consequence: a signed 16-bit `a - b` overflows when the
operands span too much of the range, and the comparison then lies. The first run
produced an unsorted array because the test data included 32768 and 65535.
Constrained the sort and GCD inputs below 2^14, which is a property of the
machines rather than of the benchmark — a machine with an overflow flag would not
need it.

### 21. The four-instruction machine cannot run this suite

With only `LDA STA JZ SUB`, there is no bounded-time way to compare two numbers:
branch-on-zero plus subtract can decide `a < b` only by counting down, which is
O(value). So the phase 3 ladder starts at five instructions, with `JN` (branch on
`acc[15]`) in the baseline, and the four-instruction set is recorded as unable to
express the workload rather than as a slow data point. This is an expressiveness
result, not an engineering one, and it is the first time in the project that an
instruction set has failed outright.

### 22. Bugs

**SUBLEQ's sign test is wrong for exactly one value.** The natural expansion of
"`s < 0`" is "not (`-s <= 0`)", which costs 3 instructions. It misclassifies
`s = -32768`, because negating it overflows to itself. Both the multiply and the
divide shift an operand through exactly `0x8000`, so the bug was live: the
product came out short by exactly `2 * multiplicand`, which is what pointed at a
single missed conditional add in the second-to-last iteration. Replaced with a
test of `(s + 1) <= 0`, exact everywhere except `s = +32767`, which the suite
never produces. Cost: two extra instructions per `jn`.

**Halt detection.** The emulators stopped when an instruction jumped to itself,
which never fires on the 5-instruction machine because its unconditional jump is
two instructions (`LDA zero; JZ`), so the halt is a two-instruction loop. It span
to the 10-million-instruction limit and reported 15,003,124 cycles. Changed both
emulators and the testbench to stop at the 123rd output, which is the fair
measure anyway.

**Zero-width concatenation.** `iad + {{(AW-8){1'b0}}, xreg}` is illegal when
`AW == 8`, which is exactly the width the winning design needs. Plain `iad +
xreg` zero-extends correctly.

### 23. Results, and the surprise

```
design                    ops  words    core  all-RAM  ROM+RAM     best   cycles  gate-Mcy
SUBLEQ                      1    852    1043   166655      n/a   166655    47509    7917.6
LDA STA JZ SUB JN           5    309     958    61085      n/a    61085    14873     908.5
+ ADD JMP                   7    259    1182    51603      n/a    51603    11013     568.3
+ LDX LDAX STAX            10    247    1335    49501    10581    10581    10333     109.3
+ AND OR XOR SHR           14    247    1543    49709    10789    10789    10333     111.5
```

The minimum is at **10 instructions**, 5.2x better than 7 on area x time and 72x
better than SUBLEQ, with the curve turning up at 14 exactly as in phase 2.

The surprise is *why* the index register wins. It costs 153 gates and saves only
12 words of program, which by the phase 2 exchange rate is break-even. Its real
effect is categorical: without it, the only way to compute an address is to write
it into an instruction, so the sort drags the entire program into writable RAM.
With it, no program word is ever written and the code can sit in ROM at ~4
gates/word instead of ~196. That turns 49,501 gates into 10,581 — a 4.7x cut
bought with 153 gates.

This retro-corrects the phase 2 write-up, which treated "put the code in ROM" as
a lever independent of the instruction set. On any workload containing array
indexing, **ROM eligibility is an ISA property**, and precisely one instruction
group buys it.

### 24. Where the budget ends up

At the optimum: 9,246 gates of memory subsystem (of which ~9,200 is 47 words of
*data* RAM and only ~836 is the 200-word code ROM) against 1,335 gates of core.
Data has replaced code as the dominant term, which is the right place for the
optimisation to stop — what remains is the problem's own working set, and no
instruction set can remove it. Further ISA work would be chasing 13% of the
budget.

---

## Session 4 — 2026-09-14: literature survey and further reduction

### 25. Reading before building

Surveyed published work on minimal processors before touching the RTL.

The most directly relevant is Sakamoto, Ahmed, Anderson and Hara-Azumi's
"Subleq⊖: An Area-Efficient Two-Instruction-Set Computer". They add exactly one
instruction to SUBLEQ — a bit-reversed subleq that reuses the existing
subtractor — and measure 147 LUTs to 195 LUTs (1.33x) for a 2.78x geometric-mean
speedup, while two alternatives that added dedicated shifter or multiplier
hardware cost 1.87x and 5.86x and were *slower* in wall-clock terms. That is
independently the same finding as our phase 2 and 3 turn-up: instructions that
reuse the datapath are nearly free, instructions that add datapath rarely pay.

Also surveyed: Schoeberl's **Lipsi** (8-bit accumulator, <100 logic elements,
explicitly chose accumulator over a register file), **Ultrasmall/Supersmall**
(2-bit-serial MIPS, ~22 cycles per instruction), **SERV** (bit-serial RISC-V),
Puffitsch's **Ø processor** (generates hardware only for instructions the program
uses — our 14-instruction result as a tool), and Jones's **"The Ultimate RISC"**
(1988), a single `MOVE mem,mem` with memory-mapped ALU and PC. Jones notes in
that paper that three address fields reduce to two with an accumulator.

Convergent answer in the literature: accumulator machine, narrow instruction
set. The live disagreements are about datapath width and encoding, not shape.

### 26. Sizing the prize before building

Broke down the 47 data words at the phase 3 optimum: 16 array, 19 mutable
scalars, **12 constants**. The constants were sitting in writable RAM at ~196
gates each for values that never change — 2,352 gates of pure waste, and 22% of
the machine. Also found `_t0` allocated unconditionally although only the
no-ADD backend uses it.

### 27. The counting bug

While isolating the ROM/RAM split, the combined memory-subsystem figure came out
as **exactly** the data RAM measured alone — 4,597 either way. An improbable
coincidence, so it was worth chasing.

Cause: yosys `stat` prints cell counts **per module**, and the parser took the
first block after "Printing statistics". For a flat design that is the whole
design; for anything with submodules it is a fragment. Every `comp_*` core and
both ROM splits in phases 2 and 3 were affected — the CPU cores were being
counted without the CPU inside them.

Fixed by adding `flatten` before technology mapping. Recomputed and corrected
every affected table in `project.md` and `README.md`. **No conclusion moved**:
phase 2's minimum is still 8 instructions, phase 3's still 10, both turn-up
points unchanged. The phase 3 optimum corrects from 10,581 to 11,420 gates.

Worth recording why it was caught: not by a test, but by a number being *too
round*. Two independently computed quantities agreeing exactly is a signal.

### 28. Three levers

**Read-only data out of RAM.** Reordered the memory map to code, constants,
scalars, array, so the ROM region covers code *and* constants. No ISA change,
**2,266 gates saved**. It only compounds with the index register, though, since
a self-modifying machine has no ROM region at all.

**Variable pooling.** The five benchmarks run in sequence and their working sets
never overlap, so 18 scalars pool down to **seven** — the maximum live at any
one point. Eleven RAM words removed for a renaming: **2,076 gates**. This is a
compiler decision worth more than every remaining ISA decision combined, which
is itself the finding.

**Immediates.** Added `LDI`/`ADDI` with a 12-bit sign-extended field. Once
constants live in ROM at ~4 gates each, immediates have almost nothing left to
save: they remove 8 constant words but cost 182 gates of core, a **net 247-gate
loss**. They do save 519 cycles, so the 12-instruction machine wins narrowly on
area x time (71.9 vs 73.1) and loses on area. Immediates turn out to be an area
optimisation only when constants are expensive to store.

Also measured and discarded: narrowing the data RAM's address decoder to
`ceil(log2(NDATA))` bits, worth 12 gates.

### 29. Testing the narrow-datapath hypothesis

Lipsi is 8-bit and SERV is bit-serial, so if a narrower word made *storage*
cheaper it would dominate everything else. Measured the same 368 bits in four
organisations:

```
 23 x 16b -> 4597 gates (12.49/bit)
 46 x  8b -> 4626 gates (12.57/bit)
 92 x  4b -> 4705 gates (12.79/bit)
368 x  1b -> 5296 gates (14.39/bit)
```

Cost is set by bits stored, not by words; narrowing the word only multiplies the
per-word decoder. So an 8-bit machine would store the same bits, need
double-length arithmetic, and shrink only the core. Lipsi's choice is right for
its cost model — FPGA logic elements with free block RAM — and wrong for ours.

### 30. Result

The 10-instruction machine is still the answer, now at **7,078 gates**, 1.61x
below the corrected phase 3 figure, from two changes that are not instruction-set
changes at all. Remaining budget: 37% the benchmark's own 16-word array, 21%
core, 16% scalars, 13% ROM, 13% glue. Over half is the problem's working set,
which no ISA can remove.

Left untested: a MOVE machine in Jones's sense. With an accumulator its
instruction fits one 16-bit word, code size should be close to ours, and the core
trades opcode decode for port comparators — but every MOVE costs a read, a write
and a fetch, ~3 cycles against our 1.86 average. Expectation is a small area win
and a ~1.6x cycle loss. That is reasoning, not measurement, and it is the obvious
next experiment.

---

## Session 5 — 2026-09-14: the MOVE machine

### 31. Building Jones's Ultimate RISC

Implemented `rtl/cpu_move.v`: one instruction, `MOVE src,dst`, packed as
`{dst[7:0], src[7:0]}` in a single 16-bit word, with accumulator, ALU, program
counter and index register all memory-mapped to ports at the top of the address
space. Added a `Move` backend and emulator to `sw/suite.py` and a `DUT_MOVE`
branch to the testbench. Verified on the full suite: 123 correct outputs.

Timing model: `cycles = 1 + (source needs a read) + (destination needs a write)`,
so port-to-port is 1 cycle, memory-to-port and port-to-memory 2, and
memory-to-memory 3.

### 32. Both halves of my phase 4 prediction were wrong

I predicted "a small area win and a ~1.6x cycle loss". Measured: a small area
*loss* and a 4% cycle loss.

**Cycles.** I had assumed 3 cycles per MOVE. But the accumulator absorbs one end
of nearly every move — `MOVE x,ADD` has no destination write, `MOVE ACC,x` has no
source read — so the average is 2.09 cycles per instruction against the
accumulator machine's 1.86. And the machine needs *fewer* instructions (5,130 vs
5,564) and less code (168 words vs 200), because memory-to-memory move is a real
instruction: `mov d,s` is one word where the accumulator machine needs two, and
`out s` likewise. Net: 10,743 cycles against 10,333.

**Area.** I expected the core to shrink without an opcode to decode. It grew by
97 gates. Removing the opcode relocates the decoding rather than eliminating it:
the machine needs two 8-bit port comparators, an index register with its own
adder, a mux to substitute `adr` into either address field for `IND`, and a
three-way address mux. A 4-bit opcode feeding a small decoder is cheaper than
comparing two 8-bit addresses against a port range.

### 33. What the MOVE machine actually pays for

The `ROM=code` column is stark: 13,784 gates against the accumulator machine's
9,344. At `ROM=code+RO` they are within 3.5%.

The cause is that a MOVE machine cannot encode a branch target in its
instruction. `jmp L` is `MOVE K,PC` with `K` a word holding `L`, so every branch
site needs a constant word: **34 constants against 12**. Those 22 extra words
cost ~4,300 gates in RAM and ~90 in ROM. The Ultimate RISC is only competitive
because read-only storage is cheap — the phase 4 lever, worth about four times
more to this machine than to the accumulator machine.

### 34. Final standing

```
10-instruction accumulator + index    7078 gates   73.1 gate-Mcy
12-instruction, with immediates       7325         71.9
MOVE / Ultimate RISC                  7329         78.7
14-instruction                        7280         75.2
SUBLEQ                              164783       7828.7
```

Three architectures with 10, 12 and 1 instructions land within 3.5% of each
other, while a fourth one-instruction machine is 23x worse. The instruction-set
spread is much smaller than the spread from decisions that are not about the
instruction set: read-only data in ROM (2,266 gates) and variable pooling (2,076).

The project's closing finding: once the memory hierarchy is right, *which* single
instruction you pick matters far more than *how many* you have. SUBLEQ and MOVE
are both OISCs and they differ by a factor of 23.

---

## Session 6 — 2026-09-14: the MOVE comparison was unfair

### 35. The objection, and why it lands

Raised against phase 5: the MOVE machine is an OISC only by technicality. It has
a full ALU reached by moving a value to one address and collecting the result
from another, so its destination address field selects between ten behaviours —
which is what an opcode field does. Comparing it to SUBLEQ as one instruction
against one instruction is not like for like.

Correct, and phase 5's own measurements had already said so without my drawing
the conclusion: the MOVE core came out *larger* than the 10-instruction machine,
and I wrote that "removing the opcode relocates the decoding rather than
eliminating it". That was the finding; I filed it as a footnote.

Wrote out the port-to-instruction mapping and it is 1:1 across all ten
operations. The MOVE machine *is* the a10 accumulator machine with the opcode
moved into the destination address. Its near-tie with a10 is two encodings of one
architecture landing in the same place, not a result about OISCs.

Changed every table to count **distinct primitive operations** — opcodes plus
port behaviours, excluding the output port that every design has — rather than
instruction formats. MOVE is relabelled from 1 operation to 9.

### 36. Giving SUBLEQ the same amenity

If memory-mapped functional units are allowed for MOVE they must be allowed for
SUBLEQ. Built `rtl/comp_subleq2.v`: the same SUBLEQ core, with two addresses
wired to hardware — `ADR` (an index register; `subleq ADR,ADR` clears it,
`subleq K,ADR` adds to it) and `IND` (reads and writes `mem[ADR]`). Still exactly
one instruction.

Indexed store drops from 15 instructions to 9, and — the point — nothing
self-modifies any more, so the program can live in ROM.

**Bug:** the first run produced correct Fibonacci output and then `x` for every
sorted value. Cause: `adr` had no reset, and the program clears the index with
`subleq ADR,ADR`, which computes `x - x = x` — so the register never became
defined. The emulator started it at 0 and disagreed. Real hardware powers up the
same way, so the fix is a genuine reset, not a simulation workaround.

### 37. Result: the objection costs the phase 5 conclusion

```
SUBLEQ            164783 gates   AT 7829
SUBLEQ + 2 ports    8848 gates   AT  398     18.6x smaller, 19.7x better
a10                 7078 gates   AT   73
```

Two memory-mapped ports take SUBLEQ from 67x worse than the best design to 1.25x
worse on gates. The "23x gap between two one-instruction machines" from phase 5
was almost entirely an **addressing** gap.

What survives: SUBLEQ is still 4.35x slower in cycles (44,953 vs 10,333) and 5.4x
worse on area x time, because three words per instruction, no native comparison
and no native add are properties of the instruction itself that no port can fix.

### 38. The finding that replaces the old one

Sorted by gate count the field splits into two clusters, and the boundary is not
the instruction count:

```
cannot index without self-modifying code   47,295 - 164,783 gates   (1-7 ops)
can index without self-modifying code        7,078 -   8,848 gates   (3-14 ops)
```

Within the cheap cluster everything is inside 25% of everything else, spanning 3
to 14 operations. The expensive cluster is at least 5.3x worse, spanning 1 to 7.

The dominant variable in the whole project is one binary property: **can the
machine compute an address without writing into its own program?** Yes means the
program is read-only at ~4 gates/word; no means writable at ~196. Instruction
count, encoding, and whether the opcode lives in its own field or in an address
are all sub-25% effects on top of that.

SUBLEQ's famous inefficiency was never really about having one instruction. It
was about having no way to touch an array.

### 39. Design document

Added `DESIGN.md`: a standalone reference for the winning machine rather than a
narrative of how it was found. Instruction table with encodings and cycle counts,
the three-state microarchitecture and its overlapped fetch, the memory map, the
gate budget by component, core cost per instruction group, and the index-register
argument with the two qualifications that keep it honest (it saves nothing by
itself — it is a permission to use ROM, and the saving only appears when the
permission is used).

All figures cross-checked against `build/phase4.json` and fresh synthesis runs
before writing: core 1,335 plus 174 for the output port, 38 flip-flops, ROM 912
gates for 212 words, data RAM 4,597 for 23 words, total 7,078.

### 40. Article

Added `ARTICLE.md`, a short write-up aimed at someone who has not read the
repository: the gates-per-word exchange rate, where the instruction-count curve
turns, and the two-cluster finding with the index register as the boundary.
Added `ARTICLE.ru.md`, a Russian translation. Both linked from the README.

Figures in the article are the same measured ones used in `DESIGN.md`: 196
gates per RAM word against 4.3 per ROM word, the 210-gate index register buying
a 42,399-gate saving, 7,078 gates total for the winning machine, and SUBLEQ
going from 164,783 to 8,848 once given the same memory-mapped ports.

### 41. Review prompt

Added `review-prompt.md`: a prompt for having `ARTICLE.md` critiqued by a model
or reviewer that has not seen this work. Written to draw out objections rather
than praise — it states the method and its modelling choices up front so the
reviewer can judge whether the conclusions follow, names the six load-bearing
claims so each is attacked individually rather than the piece being assessed as
a whole, declares new experiments and renumbering out of scope, and puts "what
it does well" last and conditional on being true.

The modelling choices most likely to be challenged are listed explicitly in the
prompt rather than left for the reviewer to find: flip-flop RAM instead of SRAM,
a small benchmark, and the 16-word array being a large share of the winning
design's memory.

### 42. External review of the article, and what was accepted

Ran `review-prompt.md` against the article. The review came back "publishable
after specific fixes". Recording the disposition of each point, since the
article is now the public face of the work.

**Accepted and fixed:**

* *The 42,399-gate saving is an artefact of the flip-flop-RAM model.* Fair. The
  46x ROM-to-RAM ratio is doing all the work and the article presented the
  saving as a property of the index register. Added an explicit paragraph: the
  claim is scoped to the gate-level memory model, real SRAM (~6 transistors per
  bit rather than ~6 gates) would shrink the memory term by about an order of
  magnitude, and mask ROM at ~1 transistor per bit means the gap narrows without
  inverting. The direction survives any memory technology; the magnitude does
  not.
* *The two-cluster split is a property of this benchmark, not of the design
  space.* Fair. Softened, and added a sentence naming the dependency: the suite
  sorts a 16-word array, so indexing is on the critical path; a workload that
  never touches an array would move or erase the boundary.
* *"806 gates, three percent" is inconsistent with the later 1,241-1,509 gate
  cores.* Not an error — 806 is the phase 1 four-instruction machine against a
  27,406-gate design, and it is a flat module unaffected by the phase 4 counting
  bug — but the article never said which machine, so it reads as inconsistent.
  Attributed it, and added that the core is 21% in the final machine.
* Straw-manning OISC advocates (most claim pedagogical interest, not area);
  flip-flops normalised to 6 NANDs not stated in the body; "bottoms out at ten"
  asserted beyond the measured points; break-even rule stated as
  technology-independent; the augmented SUBLEQ sitting unremarked at the top of
  the cheap cluster; "it is, roughly, a PDP-8"; the closing sentence
  over-generalising the job of an instruction set. All fixed as suggested.

**Rejected:**

* *"A Harvard machine with a separate instruction ROM was always available."*
  This is the one point that misreads the result. A self-modifying program
  cannot live in ROM, so the Harvard split is not an alternative to the index
  register — it is the thing the index register makes legal. The article already
  says this; no change, though the qualification paragraph above now sits next
  to it.
* *"196 x 12 = 2,352, not ~50 gates."* The reviewer half-retracted this in the
  same sentence. The twelve words saved are code, which lives in ROM at 4.3
  gates each, so ~50 is right. Reworded to say "twelve words of program ... in
  ROM at 4.3 gates each" so the juxtaposition cannot confuse.

Russian translation updated to match, change for change.

### 43. Prose pass, and a silently failed edit

Second review pass on the article, this time for prose rather than claims.
Found something worse than a prose problem first.

**The most important fix from session 42 had never been applied to the English
article.** The search-and-replace for the index-register paragraph used a source
string containing `**bold**` markers that the file did not have, so it matched
nothing and did nothing — silently. The Russian translation used a different
source string, which did match, so for one commit the two languages disagreed on
the single most contested claim in the piece: the SRAM qualification existed in
Russian and not in English.

Caught by reading the file instead of trusting the earlier `grep` count, which
had been satisfied by unrelated occurrences of the same words. Lesson recorded:
a replace that reports no error is not a replace that happened; verify by
reading the changed region, not by counting keywords.

Both articles have been rewritten from scratch rather than patched further, so
their structure now matches section for section.

**Prose changes:**

* Dangling modifier: "Sweeping instruction sets over a suite, the total gate
  count falls" — the sweeping does not fall. Now imperative: "Sweep ... and the
  total gate count falls".
* Moved the workload-generality caveat out from between the cluster claim and
  its explanation, where it interrupted the argument, down to sit beside the
  memory-model caveat after the payoff. Both caveats now land together, after
  the reader has the result.
* "I set out to check the hardware claim by building it" — "it" referred to a
  claim, which cannot be built. Rewritten.
* "A footnote on OISCs" undersold the section that contains the sharpest result
  in the piece; retitled "What one instruction actually costs".
* Removed the duplicated 7x (stated once before the table and once after),
  tightened the ragged line wrapping left by the earlier patches, and trimmed
  the closing sentence, which the previous revision had made accurate but flat.

**Figure correction:** both articles said the four unused logic instructions
cost 203 gates; the measured delta is 202 (1,711 - 1,509). `project.md` also
carried 215 for the phase 2 equivalent, where the measurement is 216. Both
corrected everywhere they appeared. Neither changes any argument, but a wrong
number in the one document outsiders will read is worse than a wrong number
anywhere else in the repository.

### 44. Second external review: three real errors

A sharper review than the first. Three of its findings are errors rather than
matters of emphasis, and all three are now fixed.

**1. The 25% claim was simply false as written.** The article said "inside a
cluster the instruction set is worth at most 25%". That is true of the cheap
cluster (7,078 – 8,848 = 1.25x) and false of the expensive one (47,295 –
164,783 = 3.48x), and a reader can compute the contradiction from the table
printed directly above the sentence. `README.md` had the correct formulation all
along — "everything in the cheap cluster is within 25% of everything else" — and
the article had generalised it while rewording. Now scoped to the cheap cluster.

**2. The break-even rule was stated unconditionally when it only holds for RAM.**
"An instruction is worth adding if it removes one word of program per 196 gates"
is a rule about program words priced as writable memory. In ROM a word costs 4.3
gates, so the same instruction would have to remove forty-seven words to justify
200 gates of decode. The article introduced the rule in section two and then
spent section four demolishing its premise without ever saying so. Now the rule
carries its condition explicitly, a sentence at the end of that section tells the
reader the condition is about to be removed, and the ROM argument closes the loop
by retiring the rule — which also explains, rather than merely asserting, why the
cheap cluster is so flat.

**3. "210 gates bought a 42,399-gate saving" was not a controlled comparison.**
It subtracted the 7-instruction machine's total from the 10-instruction
machine's, so the difference contained a different program, a different program
size, the memory-map changes and the index hardware all at once. Replaced with a
genuinely controlled pair: the *same* ten-instruction machine running the *same*
program costs 47,295 gates with its code in RAM and 7,078 with it in ROM, and
the index register is the only reason the second is legal. The wording now says
the 210 gates "do not save 40,217 gates; they make 40,217 gates saveable",
which is the claim the evidence actually supports.

**Also fixed:** "all figures are measured" sat in the same document as
transistor-per-bit rules of thumb, which a hostile reader could fairly call out —
the footer now separates measured results from technology estimates, and the
"order of magnitude" phrasing has been dropped. The 21% figure is core *plus
output port*, now stated as such. Sakamoto et al. get their full four-author
attribution and the paper title. "Five memory accesses" is marked as an
implementation property of my SUBLEQ, not of SUBLEQ. The 196 figure is described
as the synthesised RAM at these sizes rather than an intrinsic cost of a word.
"Never really about having one instruction" narrowed to "in this experiment".
The PDP-8 line no longer claims causal inevitability, Jones's Ultimate RISC is
dated and defined, and "the same privilege" became "the same hardware
facilities".

**Partially accepted:** the reviewer proposed reordering the article so that
ROM-eligibility leads and the instruction-count curve follows, which would make
the conclusion feel more inevitable. I kept the discovery order — it is the
article's spine, and the piece is honest that the curve turned out to be a
sideshow — but adopted the substance of the point by scoping the break-even rule
on first use and signposting forward to where it gets retired. The logical
inversion the reviewer identified was real; the fix did not require the
restructure.

### 45. Third review: half of it hit a stale prompt

A third review came back "publishable after specific fixes" with three serious
problems listed. Checking the quoted text against the files:

```
"An index register costs 210 gates and buys a 42,399-gate saving"  -> 0 hits in ARTICLE.md, 1 in review-prompt.md
"The design space splits into two clusters separated by 7x"        -> 0 hits in ARTICLE.md, 1 in review-prompt.md
"making the CPU core ~3% of the machine"                           -> 0 hits in either; paraphrase of prompt claim 1
```

All three of the headline problems quote the **claims list in
`review-prompt.md`**, not the article — and that list still described the
article as it stood two commits earlier, before the second review's fixes. The
reviewer duly attacked "42,399-gate saving" and recommended replacing it with
the controlled RAM-versus-ROM comparison, which the article had already adopted.
Same for the unconditional break-even rule and the 3% framing.

This is a defect in my prompt, not in the review. A summary of an artefact that
lives beside the artefact will drift, and a reviewer reading both will trust the
summary. Fixed by regenerating the claims list from the current text, adding a
line stating that the article governs where the two disagree, and appending a
note to the prompt requiring the list to be updated in the same commit as any
material article change. Also added a check that every figure quoted in the
prompt still appears in the article.

**What was genuinely new and has been applied:**

* The 6.7x figure now carries "under the gate-built memory model used
  throughout" adjacent to the table, with a forward pointer to the caveats,
  rather than relying on a qualification forty lines later.
* Added an honest paragraph about the shape of the argument: once you grant that
  every written word must be full-price RAM, a self-modifying machine is
  expensive almost by construction. The model makes it true *that* it costs; the
  measurement establishes *how much*. The reviewer's "this is a property of your
  memory model, not of indexing" is close to fair, and saying so outright is
  better than letting a reader find it.
* The 196 figure now points at `synth/gates_ram.sh` so it can be reproduced
  rather than taken on trust.
* The twelve saved words are broken down: ten across the suite's five
  indexed-access sites, plus two constant words the self-modifying version needs
  as instruction templates. Verified against the assembler (a7: 210 code + 14
  constants; a10: 200 + 12).
* Opening says "smaller" in what — fewer gates in total, memory included.
* "An opcode field wearing a disguise" became "functionally an opcode field".
  Not for the reviewer's stated reason (smugness) but a better one: the original
  implies Jones was concealing something, and a 1988 design that never claimed
  area minimality deserves better.

**Not applied:** the suggestion to give both the 3% and 21% figures up front and
to condition the exchange rate on writable memory — both were already done in
the previous revision, which is exactly the drift described above.

### 46. Fourth review: the best one, and it cost the most

This reviewer read the repository rather than only the article, declared that
deviation from the prompt up front, and found three real problems plus two stale
figures I had left lying around. Nearly all of it is accepted.

**1. The controlled comparison still carried a confound.** Session 44 replaced
an uncontrolled pair with "the same machine costs 47,295 gates with code in RAM
and 7,078 with it in ROM". But 7,078 is the `ROM=code+RO` column — code *and
constants* in ROM — while the column that isolates code placement is `ROM=code`
at 9,344. The 2,266-gate difference is the constants relocation, which
`DESIGN.md` itself labels a memory-map change available to any design. So the
figure overstated the index register's leverage by 2,266. Now stated as 47,295
to 9,344 = 37,951, with the constants move given separately as the route to the
headline 7,078. Two rounds of fixing the same sentence; it is now actually
controlled.

**2. "Bottoms out at ten" was false in the regime its own section had just
defined.** The sentence sat inside the section scoped to programs in writable
RAM, and in the all-RAM column the minimum is *twelve* (45,927), not ten
(47,295). Ten wins only once code is in ROM — a condition that section had not
yet introduced. Worse, the supporting argument skipped the twelve-instruction
variant, which is the actual next point on the curve and goes *down*.

The fix is a strict improvement on the original claim, so it is worth recording
in full. Both minima are now shown in a table, and the break-even rule predicts
them: the two immediate instructions cost 182 gates of core and remove eight
program words, worth 1,568 in RAM, so they should come out ~1,386 ahead — and
measured, they come out 1,368 ahead. In ROM the same eight words are worth ~34,
so the same instructions are a net loss and the minimum moves to ten. A rule
that predicts a different optimum in each regime, to within 1.3%, is much better
evidence than a rule stated once and left.

Also added: past the minimum the ROM column runs 7,078 / 7,325 / 7,280, so
"turns back up" is a 3.5% wobble there rather than a cliff.

**3. The two-group split assumes a monolithic program store, and the article
never said so.** The expensive group exists because I priced any design that
writes one program word as though every program word were RAM. The addresses a
self-modifying program patches are link-time constants, so a store could be
split into ROM plus a handful of individually decoded writable words — five of
them for the seven-instruction machine — which the reviewer estimates lands near
8,000 gates, inside the cheap group. I have not built it. The article now says
so plainly, prices the sketch as a sketch, and notes that the last time I
reasoned about an unbuilt design here (the MOVE machine) I got both area and
timing wrong in opposite directions. What survives is narrower: the index
register removes the need for a writable window at all, and 6.7x is what the
simple one-ROM-one-RAM map costs you for lacking it.

**Smaller fixes, all accepted:** the 3% figure is now labelled as coming from
the design whose 100-word output array I later replaced; "a quarter of the
entire CPU" is "a quarter of *that first* CPU" (against the final processor it
is 13%); "no comparison primitive" is wrong — SUBLEQ branches on the sign of a
difference, which is the same primitive the winner uses — corrected to "no
comparison that leaves its operands intact"; the 196 figure names the store it
came from; the Sakamoto ratios are marked as core-area-only; the `operations`
column is defined on first use, which removes an apparent contradiction with
"still one instruction" two sections later; "two clusters, nothing in between"
became "two groups ... among the designs I built"; the 38 flip-flops regained
the "including the FSM" qualifier that made 16+8+8 add up; and the 7,078
breakdown regained the 60-gate glue row that made it sum.

**One I had been wrong about twice.** A previous reviewer said the twelve saved
words were worth ~2,350 gates, not ~50, and I rejected it on the grounds that
they end up in ROM. That was answering a different question. The question is
whether code density justifies buying the index register, and the counterfactual
for that is *no index register*, where the words are RAM. Priced correctly,
density alone repays the register about tenfold — and the measured
seven-versus-ten row confirms it at 2,182 gates. Both prices are now given. The
section is stronger for it: it stops a reader suspecting the ~50 was chosen
because it was the small number.

**Two stale figures in the repository**, which the reviewer found by grepping
and which would have been found by anyone else the same way. `README.md` and
`project.md` still described the index register as costing 148 gates, the
phase 3 measurement, against the article's ~200. And `project.md`'s phase 4
budget decomposed the 7,078 differently from `DESIGN.md` — array + scalars +
decode versus data RAM + glue — so the two could not both be right. The phase 3
section is now labelled as phase 3 figures, and the budget table matches
`DESIGN.md`.

While reconciling those I found a third, unreported by anyone: the index group
measures +210 gates on the CPU alone and +198 synthesised together with the
output port. Both are correct; they differ by synthesis sharing across a module
boundary. `DESIGN.md` now records both, and the article says "about 200" rather
than claiming three significant figures it cannot support.

**Declined:** retitling. The reviewer is right that the body spends its second
half arguing instruction count is the wrong axis, which sits oddly against "one
instruction is not cheaper than ten". But the title is true of plain SUBLEQ, the
reversal is deliberate and signposted ("the curve turned out to be a sideshow"),
and a title that already contains the article's conclusion gives a reader less
reason to read it. Recorded as a judgement call rather than an oversight.

### 47. Fifth review: two accepted, one refuted by arithmetic

Diminishing returns, but three points were worth acting on and one was worth
checking rather than accepting.

**Accepted.** "Which side of the boundary a machine lands on has nothing to do
with how many instructions it has" overstated: the cheap group is not flat, it
spans 7,078 to 8,848. Softened to "depends far less on instruction count than on
whether the program can be kept read-only", and the article now says something
more interesting in its place — the spread inside the group does not track
instruction count either, since the fourteen-operation machine beats the
twelve-operation one. Also added that ROM eligibility is binary with no partial
credit, and a forward pointer from the 6.7x to the hybrid-store caveat at the
end of the section, which previously appeared without warning.

**Accepted.** "SUBLEQ's area penalty was driven far more by addressing than by
having one instruction" now says "one opcode", and notes that the three-word
instruction format survives the port change untouched and is most of the 25%
still separating the ported SUBLEQ from the winner. That is a more precise
attribution of what the ports did and did not fix.

**Refuted.** The reviewer argued that the twelve-word density calculation and
the measured seven-versus-ten delta "are not the same experiment", the latter
still containing a self-modification tax. Checked: twelve words at 196 gates
less 198 gates of extra core predicts 2,154; measured is 2,182. A 28-gate
residual, which is synthesis noise, not a tax. They are the same experiment and
they agree. Rather than leave "confirms it" as an assertion, the article now
shows the arithmetic — which is a better paragraph than either version, so the
point was productive even though its premise was wrong.

**Smaller, accepted:** "a quarter of that first CPU" -> "that first core"
(against the final processor it is nearer an eighth); "the curve turned out to
be a sideshow" -> "secondary", since with the two-regime table the curve now
does real work predicting both minima; "a rounding error beside its real one" ->
"an order of magnitude smaller than its real one", which is the same claim
without the swagger; and the Jones paragraph now pre-empts the obvious objection
by saying why a destination field selecting the operation is not merely a
memory-mapped control register.

**Declined:** rewriting the closing sentence to "enabling the program to live in
ROM without self-modification". More literally accurate, but flatter, and three
of the five reviewers have independently said the current closing lands. Kept,
recorded as a judgement call.

`review-prompt.md` claim 4 updated in the same commit, per its own note.

### 48. The four-instruction machine was never introduced

Raised against the Russian text: "Ядро той первой четырёхинструкционной машины"
refers to a machine the article has not mentioned. Checking the English, the
same hole is there and is arguably worse — the opening said "running real
programs on both designs", and never says which two. The four-instruction
accumulator machine is the reason the project exists and it first appears, with
a definite article, two sections in.

Fixed in both languages by splitting the opening into two paragraphs: the first
names the contest (SUBLEQ against the smallest conventional machine I could
construct — load, store, subtract, branch-if-zero), the second says SUBLEQ lost
and that chasing the reason turned a two-way comparison into a search for the
minimum. That also gives the piece the shape it actually had, instead of
starting mid-search.

While fixing it, a second gap in the same area: the regime table starts at seven
instructions with no explanation of where four and five went. Added the
five-instruction row (59,125 gates) and a paragraph saying the original
four-instruction set cannot run the suite at all — with only branch-if-zero and
subtract there is no bounded-time comparison, so deciding `a < b` costs steps
proportional to the values. It needs branch-on-sign before it can sort anything,
which is why the ladder starts at five. That fact was in `project.md` from phase
3 and had never made it into the article, where it answers the obvious question.

Two process notes. Patch-by-string-replacement against a wrapped file kept
failing, because the wrapping moves under the replacement; wrote `/tmp/edit.py`
to unwrap paragraphs, edit, and rewrap, which is how the later edits in this
session were done. And a `python3 -c` with backticks inside a double-quoted
shell string silently ate the code span in `«`a < b`»`, leaving `«»` in the
Russian text — caught by reading the result, not by the command succeeding.

`review-prompt.md`'s method summary updated in the same commit, per its own note.

---

## Session 7 — 2026-09-20: a search, after a charge of bias

### 49. The objection

From a reader: every design compared in phases 1-6 was one I chose, and the ones
I chose are the branches that historically existed. A model whose weights
contain the whole history of computer architecture, proposing SUBLEQ, an
accumulator machine, a PDP-8-alike and Jones's MOVE machine and then announcing
a winner, is not searching. It is recalling. The asked-for remedy was code that
searches impartially rather than prose defending the choice.

Correct, and the strongest criticism the project has had.

### 50. What was built

`sw/autosearch.py`: pool enumerated as a cross product (31 candidates), code
generated by breadth-first search over instruction sequences verified on random
test vectors, branch sequences found by covering the outcome classes with
whatever conditional jumps a candidate happens to have, Verilog emitted from the
instruction list and synthesised for real, starting points rejection-sampled.

Two controls passed before any search ran. The compiler reproduces every macro I
wrote by hand in phase 3 — including, unprompted, the six-instruction
`a + b = a - (0 - b)` for sets without ADD. And the cost model, calibrated
against three phase 4 designs, is within 0.1% on cycles and 3% on gates.

The search also found two bugs in my abstract machine: it was exploiting an
accumulator initialised to zero, and clobbering the destination before the final
store, which breaks at the `add p,p` call site. Both fixed.

### 51. Result

Twelve restarts. The two-group split reappeared unprompted: index-register runs
6,771-6,910 gates, self-patching runs 50,118-59,367. The hand-designed machine
turned up as a local optimum at 6,845.

Then it beat it. Best set: eight instructions, **no ADD and no JMP** —
`JN JZ LDX_D LD_D LD_X ST_D ST_X SUB_D`, 6,771 gates. Both missing instructions
are in every historical accumulator machine and I never questioned including
them. In the ROM regime they do not pay: ADD costs ~149 gates of core and saves
24 words of ROM at 4.3 gates, a net loss of 46; JMP costs ~66 and saves 43.
Predicted 69 gates, measured 74.

That is this project's own break-even rule, applied in the regime where a word
costs 4.3 gates rather than 196 — and I had not applied it there. The article
said instruction count "stops mattering much" past the boundary; the search
shows that past the boundary you should be *removing* instructions, and the two
I kept are exactly the two habit would keep.

The winner is 1.1% smaller and 27% slower, so it wins on gates and loses on
gates x time. On the objective this project actually stated, the search wins.

### 52. Verification

Not trusted from the model: the winner's Verilog was generated, a program
exercising all eight opcodes and both branch outcomes was assembled against it,
and a reference emulator and Icarus Verilog running the generated RTL were
compared. Exact agreement, including the double-subtract addition, indexed load
and store, and the branches that must not fire. `sw/verify_generated.py`.

### 53. What is still biased

Recorded in `project.md` rather than buried: the skeleton (one accumulator,
memory operands, 16-bit word, 4-bit opcode field) is mine and unquestioned by
the search; both array-access strategies are mine and the search only chooses
between them; the benchmark and memory model are unchanged; and twelve restarts
over C(31, <=16) subsets is sampling, not exhaustion.

The work has moved from "I compared four machines I already knew" to "I searched
a mechanically enumerated instruction space inside an architecture I chose".
That is a real improvement and a partial answer, and the write-up says so.

### 54. The search's winner does not survive measurement

Asked whether the optimum is now 6,771 gates. It is not, and the question was
the right one to ask: 6,771 was a *modelled* figure and 7,078 is a *measured*
one, so putting them side by side would have been the same apples-to-oranges
error two reviewers already caught. The article had been updated with the
modelled number, which was wrong of me.

Built `sw/emit.py` to close the gap: it assembles the benchmark for an arbitrary
searched instruction set, verifies the 123 outputs, and synthesises the ROM,
data RAM and core exactly as phases 1-6 did.

Measured, like for like (the generated CPU has no output port, so 174 gates are
added to match `comp_acc`):

```
                          search winner   phase 4 winner
CPU core, synthesised              1113             1335
output port register                174              174
memory, synthesised                6032             5569
TOTAL                              7319             7078
program words                       273              235
cycles                            13172            10333
```

**3.4% larger and 27% slower**, where the model had said 1.1% smaller. The hand
design remains the best measured machine at 7,078.

The cause is a flaw in my search's cost model that the article itself warns
about. It priced program words at 4.3 gates, the *average* over the ROM image.
The eight-instruction machine needs 38 more words, and their *marginal* cost is
12.2 gates each. Dropping ADD and JMP saves 222 gates of core and costs 463 of
memory: net loss 241, where the model predicted a gain of 75. "The marginal word
is not the average word" is a caveat I wrote and then ignored one section later
in my own tooling.

Two smaller emitter bugs found while doing this: it allocated a constant word
for both `+imm` and `-imm` at every immediate whether referenced or not (24
constants instead of 13), and the sizing pass indexed the symbol table before it
existed.

Corrected in `project.md`, `README.md` and chapter 6 of both articles. The
honest version is better than the one it replaces: the hand design now survives
a search that tried to beat it and was refuted by measurement, instead of
surviving because I picked it. That is a stronger answer to the bias objection
than "the search agreed with me" would have been.

### 55. Not a truly random search — and what fixing that changed

Pressed on whether the phase 7 search was really random, or whether it had
patterns in it that narrowed the variants tried. It had, and finding them
changed the result twice.

**The pool was not mechanical.** I had written that it contained "a branch for
every one of the six ways to test the outcome classes". There are seven. The one
missing was branch-if-not-positive — SUBLEQ's own branch condition, absent from
a pool built for a project about SUBLEQ. The arithmetic slots, meanwhile, held
exactly the operations real accumulator machines have. Both are the
pattern-narrowing the objection named.

Corrected by adding the missing branch and two primitives chosen *because* no
accumulator machine used them: reverse subtract (`acc = m - acc`) and NAND, in
all three addressing modes. Pool of 38.

**Uniform random sampling, no hill climbing at all.** 8,800 draws of a random
size and a random subset, 129 feasible. The two-group split appears from random
draw alone: index-register machines 7,505-7,900 modelled gates, self-patching
50,755-87,715, nothing between. Reverse subtract turned up in all four of the
best random machines, which is what sent me back to local search over the larger
pool.

**Two of my own tools were wrong, both in the direction of the answer I already
had.** The cost model priced program words at the ROM *average* of 4.3 gates;
decomposing the measurement properly shows the marginal ROM word is about 1.8
gates and a data word about 200, so the model mis-ranked any candidate with a
longer program. And the emitter allocated a scratch variable no generated code
referenced — a 200-gate penalty applied only to searched machines, because the
hand-written assembly never asked for it. My earlier diagnosis in entry 54, that
the marginal ROM word costs 12.2 gates, was wrong: it lumped ROM and RAM
together.

So the sequence was: model says the search wins, measurement says it loses,
finding my own handicap says it wins after all. Recorded in that order because
the middle step was published.

**Result.** Every machine compiled by the same pipeline:

```
phase 4 hand design              7161 gates  10332 cycles
8 instructions, no ADD or JMP    7168        13172
RSB machine                      6959        11656
```

Winner: `JN JZ LDX_D LD_D LD_X RSB_D RSB_X ST_D ST_X XOR_D XOR_X` — no ADD, no
SUB, no JMP. `a + b` compiles to `LD d; RSB Kz; RSB s; ST d`; `a - b` needs three
instructions with no SUB in the machine; unconditional jumps are `LD Kz; JZ`.
2.8% below the hand design through the same compiler, 1.7% below its
hand-assembled version, 13% slower. ROM synthesis varies ~50 gates with content,
so the margin is two to four times the noise.

The two XOR instructions in the winning set are dead — no template uses them.
The climb stopped at a local optimum carrying weight it did not need. Trimming
them gives 6,966, inside the noise.

**The objection was right.** A machine built on reverse subtract, with no add,
no subtract and no unconditional jump, resembles nothing in the historical
record, and it is smaller than the design I reached by recognising a PDP-8. It
took a pool containing two primitives chosen precisely because no real machine
had them to find it.

Still not randomised: the skeleton. One accumulator, memory operands, 16-bit
word, 4-bit opcode field, three-state FSM, and the two array-access strategies.
That is the next thing to put in the search, and until it is, this is a search
of an instruction space inside an architecture I chose.
