# The best hand-designed machine

The machine that came out cheapest across five phases of hand design: a
ten-instruction accumulator machine with an index register, at **7,078
NAND-equivalent gates**, running the five-program benchmark suite in 10,333
cycles.

Phase 7 then searched the instruction space mechanically and found a smaller
one — built on reverse subtract, with no ADD, no SUB and no JMP, at 6,959 gates
against this machine's 7,161 when both are compiled by the same automatic
pipeline. See the phase 7 section of `project.md`. This document describes the
hand design, which is still the fastest of the two and the one whose RTL is in
`rtl/cpu_acc.v`.

Everything below is measured, not estimated. `make phase4` reproduces it.

## Instruction set

16-bit word, encoded `{op[3:0], addr[11:0]}`. Only 8 address bits are used
because the whole memory image is 235 words.

| op | instruction | effect | cycles |
|---:|---|---|---:|
| 0 | `LDA m` | `acc <- mem[m]` | 2 |
| 1 | `STA m` | `mem[m] <- acc` | 2 |
| 3 | `SUB m` | `acc <- acc - mem[m]` | 2 |
| 4 | `ADD m` | `acc <- acc + mem[m]` | 2 |
| 2 | `JZ a` | if `acc == 0` then `pc <- a` | 1 |
| 12 | `JN a` | if `acc[15]` then `pc <- a` | 1 |
| 5 | `JMP a` | `pc <- a` | 1 |
| 13 | `LDX m` | `x <- mem[m][7:0]` | 2 |
| 14 | `LDAX m` | `acc <- mem[m + x]` | 2 |
| 15 | `STAX m` | `mem[m + x] <- acc` | 2 |

Opcodes 6-11 are unused. Assigning them costs nothing in memory (the word is 16
bits regardless) and the decode logic for absent opcodes is optimised away, but
adding instructions the workload never executes is a pure loss — see the
14-instruction variant in `project.md`.

Notes on why each is present:

* `JN` is not optional. With only `JZ` and `SUB` there is no bounded-time way to
  compare two numbers — deciding `a < b` costs O(value) steps. The
  four-instruction machine cannot express the benchmark at all.
* `ADD` exists because synthesising `a + b` from `SUB` alone takes six
  instructions (negate through a temporary) rather than three. It costs 149
  gates.
* `JMP` exists because an unconditional jump would otherwise be `LDA zero; JZ`.
  It costs 66 gates.
* `LDX/LDAX/STAX` cost 210 gates and are the reason the whole design works. See
  the last section.

## Microarchitecture

Architectural state is three registers: a 16-bit accumulator, an 8-bit index
register, an 8-bit program counter. 38 flip-flops in total including the FSM.
One 16-bit adder/subtractor is shared by `ADD`, `SUB` and the PC increment; a
separate 8-bit adder computes `m + x` on the address path.

Memory is a single-port synchronous RAM with one cycle of read latency: the CPU
drives the address combinationally, the memory registers it on the clock edge,
data is available the following cycle. Three states:

```
S_D   decode: mdin holds the instruction.
      LDA/SUB/ADD/LDX  drive addr = m           -> S_E
      LDAX             drive addr = m + x       -> S_E
      STA              drive addr = m,     we=1 -> S_W
      STAX             drive addr = m + x, we=1 -> S_W
      JZ/JN/JMP        drive addr = target or pc (this is the next fetch) -> S_D

S_E   mdin holds the operand. Update acc or x, drive addr = pc (next fetch) -> S_D

S_W   the store issued last cycle, drive addr = pc (next fetch) -> S_D
```

The next instruction's fetch is overlapped onto the last cycle of the current
instruction, which is why nothing costs more than two cycles and branches cost
one. Average over the suite: 1.86 cycles per instruction.

Source: `rtl/cpu_acc.v`, built with `-DHAS_SIGN -DHAS_ADD -DHAS_JMP
-DHAS_INDEX`.

## Memory map

```
   0 .. 199    code                 |  read-only  ->  ROM
 200 .. 211    constants            |  212 words, 4.3 gates/word
 -----------------------------------+------------------------------
 212 .. 218    7 scalar variables   |  writable   ->  RAM
 219 .. 234    16-word array        |  23 words, 200 gates/word
         235   output port          |  register + strobe
```

Two things about this layout matter as much as the instruction set:

* **Constants are read-only and belong in ROM.** Leaving the 12 constants in the
  data region cost 2,266 gates for values that never change.
* **Variables are pooled by liveness.** The five benchmarks run in sequence and
  their working sets never overlap, so 18 scalars share 7 words. Worth 2,076
  gates, and it is a compiler decision, not an architectural one.

## Gate budget

| | gates | share |
|---|---:|---|
| Data RAM, 23 words x 16 bits | 4,597 | 65% |
| CPU core (1,335) + output port register (174) | 1,509 | 21% |
| Code and constant ROM, 212 words | 912 | 13% |
| Address decode and glue | 60 | 1% |
| **total** | **7,078** | |

Gates are 2-input NAND cells after `abc -g NAND`, counting each D flip-flop as
six. RAM costs ~200 gates per word; ROM costs 4.3. That **46x** ratio is the
most important number in the project.

Core cost by instruction group, measured at identical address width:

| instruction set | core gates | added |
|---|---:|---:|
| `LDA STA JZ SUB JN` | 910 | — |
| `+ ADD` | 1,059 | +149 |
| `+ JMP` | 1,125 | +66 |
| `+ LDX LDAX STAX` | 1,335 | +210 |

Measured on the CPU alone. Synthesised together with the output port (the `core`
column of the phase 4 table) the same group comes to +198; the 12-gate
difference is synthesis sharing across the module boundary. The article rounds
this to "about 200".

## Why the index register is the whole design

Neither machine can say "element `i` of the array" in an instruction — the
address field is a constant baked into the instruction word. The address has to
be computed, and there are only two places to compute it.

**Without an index register you compute it in software, and the only place to
put the result is inside an instruction:**

```
    LDA tmpl        ; tmpl is the constant word (LDA<<12 | ARR)
    ADD i
    STA P           ; <-- overwrites the instruction at address P
P:  LDA 0           ; <-- this word was just rewritten
    STA d
```

**With an index register you compute it in hardware, in an 8-bit adder on the
address path:**

```
    LDX i
    LDAX ARR
    STA d
```

Five instructions become three, which saves 12 words across the whole benchmark
— about 50 gates of ROM. By itself that does not justify 210 gates. Code density
is not the argument.

The argument is that the second version **never writes to a program word**. That
makes the entire program read-only, and read-only storage is a different circuit
entirely: a ROM word is a few gates of decode-and-OR that logic synthesis shares
across all 212 words, while a RAM word is 16 flip-flops plus its own write
decoder and read multiplexer, none of which can be shared.

| | program store | total |
|---|---:|---:|
| 7 instructions, code must be writable | 247 words RAM = 48,166 | 49,477 |
| 10 instructions, code can be read-only | 212 ROM + 23 RAM = 5,569 | **7,078** |

210 gates spent, 42,399 saved: a return of roughly 200x.

Three qualifications, because this is easy to overstate:

* **It does not save gates by itself.** The same 10-instruction machine with its
  code in RAM costs 47,295 gates, barely better than the 7-instruction machine.
  The index register is a permission, not a saving; the saving appears only when
  the permission is used.
* **It does not win on code size.** Twelve words.
* **It wins because "can this program be read-only?" is a property of the
  instruction set**, and exactly one instruction group decides it.
  Self-modification is not a style choice that can be refactored away — on a
  machine with no address arithmetic it is the only mechanism for indexing.

This is why the whole design space splits into two clusters with nothing between
them:

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

Within a cluster the instruction set is worth at most 25%. Between clusters it is
worth 7x. SUBLEQ with two memory-mapped ports (`ADR`, `IND`) sits in the cheap
cluster at 8,848 gates, 1.25x the optimum, despite still being one instruction.

## The compact statement

A computer built from gates is mostly memory; memory that must be writable costs
about 46x more per word than memory that does not; and the instruction set's main
job is to decide which kind your program needs.
