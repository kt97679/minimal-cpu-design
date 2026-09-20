# One instruction is not cheaper than ten

There is a well-known toy in computer architecture called the one-instruction
set computer. The most famous version is SUBLEQ: subtract one memory word from
another, and branch if the result is not positive. That single operation is
Turing-complete. You can compile C to it. People build them on FPGAs for fun.

Most of the stated interest is pedagogical and theoretical, but alongside it
runs an implicit hope: that minimality also buys a smaller machine.

I decided to check that hope by building it — not by reasoning about it, but by
writing the RTL, synthesising down to 2-input NAND gates with Yosys, and running
real programs on both designs in simulation. The answer is no. The interesting
part is why, and it turns out to have almost nothing to do with instruction
counts.

## The exchange rate

The first measurement reframed the question. Building a computer out of gates
means building its memory out of gates too, and a 16-bit word of gate-level RAM
costs about 196 NAND-equivalents: sixteen flip-flops (each normalised to a
six-NAND D type), its own write decoder, and its share of the read multiplexer.

The CPU core of that first four-instruction machine, by comparison, was 806
gates against 27,406 for the whole design — three percent. Even in the much
leaner machine this ends with, the core is only 21%.

That gives you an exchange rate: one word of program costs about a quarter of
the entire CPU. Any instruction that removes even a handful of program words
pays for itself immediately. This is the opposite of the intuition that minimal
instruction sets are cheap, and it is why SUBLEQ loses — three words per
instruction, five memory accesses each, and no comparison primitive, so every
`if` becomes a macro.

## The curve, and where it turns

Sweep instruction sets across a five-program benchmark suite — Fibonacci,
insertion sort, shift-and-add multiply, Euclid's GCD, binary-to-decimal — and
the total gate count falls steeply as you add instructions, then turns back up.

Among the sets I measured it bottoms out at ten. Below that you pay in program
size: without `ADD`, computing `a + b` takes six instructions instead of three;
without an unconditional jump, every `goto` costs two. Above ten you pay in
decode logic for instructions the workload never executes — adding `AND`, `OR`,
`XOR` and a shift cost 202 gates and saved nothing at all.

So there is a break-even rule, concrete under this cost model: an instruction is
worth adding if it removes at least one word of program per 196 gates it costs.
Cheap instructions clear that bar easily. Instructions that add new datapath
usually do not — which matches what Sakamoto and Anderson found independently
when they extended SUBLEQ: a second instruction reusing the existing subtractor
cost 1.33x area for a 2.78x speedup, while variants adding a dedicated shifter
or multiplier cost 1.87x and 5.86x and ran slower in wall-clock terms.

## The finding that mattered

The curve turned out to be a sideshow. Sorted by gate count, every design I
built falls into one of two clusters, with nothing in between:

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

The boundary is whether the machine can index an array without modifying its own
code. Inside a cluster the instruction set is worth at most 25%; across the
boundary it is worth 7x — and which side a machine lands on has nothing to do
with how many instructions it has. (The top of the cheap cluster is a SUBLEQ
variant; more on that below.)

Here is the mechanism. None of these machines can express "element *i* of the
array" in an instruction, because the address field is a constant baked into the
instruction word. The address has to be computed somewhere. Without an index
register you compute it in software, and the only place to put the result is
inside an instruction:

```
    LDA tmpl
    ADD i
    STA P        ; overwrites the instruction below
P:  LDA 0        ; just rewritten
    STA d
```

With an index register, an 8-bit adder on the address path does it:

```
    LDX i
    LDAX ARR
    STA d
```

Five instructions become three, saving twelve words of program across the whole
benchmark. Those words live in ROM at 4.3 gates each, so that is about 50 gates
— nowhere near justifying the index register's 210.

What justifies it is that the second version never writes to a program word. The
program becomes read-only, and read-only storage is a completely different
circuit: a ROM word is a few gates of decode-and-OR that logic synthesis shares
across hundreds of words. Measured, that is 4.3 gates per word against 196 for
RAM — a ratio of 46x.

So 210 gates bought a 42,399-gate saving, by making the program eligible for
ROM. The index register is not an optimisation. It is a permission.

Two caveats, because that 46x ratio is doing all the work. It is partly a
property of the memory model: real SRAM is about six transistors per bit rather
than six gates, which would shrink the memory term by roughly an order of
magnitude and narrow the gap considerably. It would not invert it — mask ROM is
about one transistor per bit — but don't carry 46x into a world with real memory
macros. And the split depends on the workload: my suite sorts a 16-word array,
so indexing is on the critical path. A program that never touches an array, or
one you are happy to let rewrite itself, would move the boundary or erase it.

## The design that won

Ten instructions, 16-bit words: `LDA`, `STA`, `ADD`, `SUB`, `JZ`, `JN`, `JMP`,
`LDX`, `LDAX`, `STAX`. Three registers — a 16-bit accumulator, an 8-bit index,
an 8-bit program counter — for 38 flip-flops total. One shared 16-bit adder, a
three-state FSM, and the next fetch overlapped onto the last cycle of the
current instruction, so nothing costs more than two cycles.

Total: 7,078 gates, of which 4,597 is the benchmark's own working set in RAM,
1,509 is the CPU, and 912 is the entire program in ROM.

It resembles a stripped-down PDP-8. That is not a coincidence; it is what the
constraints produce.

## What one instruction actually costs

I also built Jones's Ultimate RISC, whose only instruction is `MOVE src,dst`,
with the ALU and program counter mapped to memory addresses. It landed within
3.5% of the ten-instruction machine — which looks like a striking win for
minimalism until you notice that its destination address field selects among ten
behaviours. That is an opcode field wearing a disguise, and its core measured
larger, not smaller, because removing the opcode relocates the decoding rather
than eliminating it.

The fair test was to give SUBLEQ the same privilege: two addresses wired to
hardware, an index register and an indirect port. Still one instruction. It went
from 164,783 gates to 8,848 — an 18.6x improvement — landing squarely in the
cheap cluster.

SUBLEQ's famous inefficiency was never really about having one instruction. It
was about having no way to touch an array.

The compact version of all of it: a computer built from gates is mostly memory,
memory you have to be able to write costs far more per word than memory you
don't, and under those constraints the instruction set's decisive job is
deciding which kind your program is allowed to live in.

---

*All figures are measured, not estimated. The RTL, the benchmark suite, the
synthesis scripts and a Makefile that reproduces every number are in this
repository; see [DESIGN.md](DESIGN.md) for the winning machine and
[project.md](project.md) for the full method.*
