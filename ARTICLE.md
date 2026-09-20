# One instruction is not cheaper than ten

There is a well-known toy in computer architecture called the one-instruction
set computer. The most famous version is SUBLEQ: subtract one memory word from
another, and branch if the result is not positive. That single operation is
Turing-complete. You can compile C to it. People build them on FPGAs for fun.

A natural question is whether that minimality also buys a smaller machine —
fewer gates in total, counting the memory as well as the processor.

I decided to find out by building it — not by reasoning about it, but by
writing the RTL, synthesising down to 2-input NAND gates with Yosys, and
running real programs on both designs in simulation. The answer is no. The
interesting part is why, and it turns out to have almost nothing to do with
instruction counts.

## The exchange rate

The first measurement reframed the question. Building a computer out of gates
means building its memory out of gates too, and the synthesised gate-built RAM
works out to about 196 NAND-equivalents per 16-bit word at the sizes involved
here: sixteen flip-flops (each normalised to a six-NAND D type), its own write
decoder, and its share of the read multiplexer. That figure is synthesised
rather than estimated; `synth/gates_ram.sh` in the repository produces it for
any memory size.

The CPU core of that first four-instruction machine, by comparison, was 806
gates against 27,406 for the whole design — three percent. Even in the much
leaner machine this ends with, the processor logic plus its output port is only
21%.

That gives you an exchange rate, and it is worth stating the condition on it up
front, because the condition turns out to be the whole story: **so long as the
program has to live in writable memory**, one word of program costs about a
quarter of the entire CPU. Any instruction that removes program words pays for
itself almost immediately. This is the opposite of the intuition that minimal
instruction sets are cheap, and it is why SUBLEQ loses in this implementation —
three words per instruction, five memory accesses each, and no comparison
primitive, so every `if` becomes a macro.

## The curve, and where it turns

Sweep instruction sets across a five-program benchmark suite — Fibonacci,
insertion sort, shift-and-add multiply, Euclid's GCD, binary-to-decimal — and
the total gate count falls steeply as you add instructions, then turns back up.

Among the instruction sets I measured, total area bottoms out at ten. Below
that you pay in program size: without `ADD`, computing `a + b` takes six
instructions instead of three; without an unconditional jump, every `goto`
costs two. Above ten you pay in decode logic for instructions the workload
never executes — adding `AND`, `OR`, `XOR` and a shift cost 202 gates and saved
nothing at all.

So there is a break-even rule, concrete and scoped: for a program that must
live in writable RAM under this cost model, an instruction is worth adding if
it removes at least one word of program per 196 gates it costs. Cheap
instructions clear that bar easily; instructions that add new datapath usually
do not — which is qualitatively consistent with what Sakamoto, Ahmed, Anderson
and Hara-Azumi measured in *Subleq⊖: An Area-Efficient Two-Instruction-Set
Computer*, where a second instruction reusing the existing subtractor cost
1.33x area for a 2.78x speedup, while variants adding a dedicated shifter or
multiplier cost 1.87x and 5.86x and ran slower in wall-clock terms.

Hold on to that condition about writable RAM. The next section removes it, and
takes the rule with it.

## The finding that mattered

The curve turned out to be a sideshow. Sorted by gate count, every design I
built falls into one of two clusters, with nothing in between:

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

The boundary is whether the machine can index an array without modifying its
own code. Under the gate-built memory model used throughout, the cheapest
design that cannot is 6.7x larger than the cheapest design that can — and how
much of that gap belongs to the model rather than to the architectures is a
question I come back to at the end of this section. Inside the cheap cluster
everything sits within 25% of everything else, across a range from three
operations to fourteen — so which side of the boundary a machine lands on has
nothing to do with how many instructions it has. (The top of that cluster is a
SUBLEQ variant; more on it below.)

Here is the mechanism. None of these machines can express "element *i* of the
array" in an instruction, because the address field is a constant baked into
the instruction word. The address has to be computed somewhere. Without an
index register you compute it in software, and the only place to put the result
is inside an instruction:

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
benchmark — ten words across the suite's five indexed-access sites, plus the
two constant words the self-modifying version needs as instruction templates.
Those words live in ROM at 4.3 gates each, so that is about 50 gates — nowhere
near justifying the index register's 210.

What justifies it is that the second version never writes to a program word.
The program becomes read-only, and read-only storage is a completely different
circuit: a ROM word is a few gates of decode-and-OR that logic synthesis shares
across hundreds of words. Measured, that is 4.3 gates per word against 196 for
RAM — about 46x in this model.

The controlled version of the comparison is this. The same ten-instruction
machine, running the same program, costs **47,295 gates with its program in
writable RAM and 7,078 with it in ROM**. The 210 gates of index register are
the only reason the second column is available at all. They do not save 40,217
gates; they make 40,217 gates saveable. The index register is not an
optimisation. It is a permission.

It also retires the break-even rule from two sections ago. Once the program is
in ROM a word costs 4.3 gates, so an instruction would have to remove
forty-seven words to justify 200 gates of decode. Nothing in a sane instruction
set does that, which is exactly why the cheap cluster is so flat: past the
boundary, instruction count stops mattering much.

It is worth being plain about the shape of this argument, too. Once you grant
that every word a program writes must be full-price RAM, it follows almost by
construction that a self-modifying machine is expensive. The model is what
makes it true *that* self-modification costs; the measurements are what
establish *how much* — 46x per word, and 6.7x across the complete machine.

Which brings us to two caveats, because that 46x ratio is doing all the work.
It is partly a property of the memory model: real SRAM is roughly six
transistors per bit rather than six gates, and mask ROM roughly one, so with
real memory macros the gap narrows substantially — though it does not invert.
Those two figures are technology rules of thumb, not outputs of this synthesis
flow, and the 46x should not be carried out of this model. The split also
depends on the workload: my suite sorts a 16-word array, so indexing is on the
critical path. A program that never touches an array, or one you are happy to
let rewrite itself, would move the boundary or erase it.

## The design that won

Ten instructions, 16-bit words: `LDA`, `STA`, `ADD`, `SUB`, `JZ`, `JN`, `JMP`,
`LDX`, `LDAX`, `STAX`. Three registers — a 16-bit accumulator, an 8-bit index,
an 8-bit program counter — for 38 flip-flops total. One shared 16-bit adder, a
three-state FSM, and the next fetch overlapped onto the last cycle of the
current instruction, so nothing costs more than two cycles.

Total: 7,078 gates, of which 4,597 is the benchmark's own working set in RAM,
1,509 is the processor and its output port, and 912 is the entire program in
ROM.

The result looks a lot like a stripped-down PDP-8: accumulator, memory
operands, conditional branches, indexed addressing.

## What one instruction actually costs

I also built Jones's Ultimate RISC, a 1988 design whose sole instruction is
`MOVE src,dst`, with the ALU and program counter mapped to memory addresses. It
landed within 3.5% of the ten-instruction machine — which looks like a striking
win for minimalism until you notice that its destination address field selects
among ten behaviours. That is functionally an opcode field, and its core
measured larger, not smaller, because removing the opcode relocates the
decoding rather than eliminating it.

The fair comparison was to give SUBLEQ the same hardware facilities: two
addresses wired to hardware, an index register and an indirect port. Still one
instruction. It went from 164,783 gates to 8,848 — an 18.6x improvement —
landing squarely in the cheap cluster.

In this experiment, then, SUBLEQ's large area penalty was driven far more by
addressing than by having one instruction. It still loses on time — three words
per instruction, no native compare and no native add are properties of the
instruction that no amount of wiring fixes — but the area gap was never really
about the instruction count.

The compact version of all of it: a computer built from gates is mostly memory,
memory you have to be able to write costs far more per word than memory you
don't, and under those constraints the instruction set's decisive job is
deciding which kind your program is allowed to live in.

---

*All gate counts and cycle counts here are measured, not estimated: the RTL, the
benchmark suite, the synthesis scripts and a Makefile that reproduces every
number are in this repository. The transistor-per-bit comparisons in the
caveats are technology rules of thumb rather than outputs of this flow. See
[DESIGN.md](DESIGN.md) for the winning machine and [project.md](project.md) for
the full method.*
