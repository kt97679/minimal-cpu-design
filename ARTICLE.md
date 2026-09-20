# One instruction is not cheaper than ten

There is a well-known toy in computer architecture called the one-instruction
set computer. The most famous version is SUBLEQ: subtract one memory word from
another, and branch if the result is not positive. That single operation is
Turing-complete. You can compile C to it. People build them on FPGAs for fun.

A natural question is whether that minimality also buys a smaller machine —
fewer gates in total, counting the memory as well as the processor.

I decided to find out by building it — not by reasoning about it, but by writing
the RTL, synthesising down to 2-input NAND gates with Yosys, and running real
programs on both designs in simulation. The answer is no. The interesting part
is why, and it turns out to have almost nothing to do with instruction counts.

## The exchange rate

The first measurement reframed the question. Building a computer out of gates
means building its memory out of gates too, and the synthesised gate-built RAM
works out to about 196 NAND-equivalents per 16-bit word — that figure is from a
136-word store, and it is synthesised rather than estimated; `synth/gates_ram.sh`
in the repository produces it for any size. The breakdown is sixteen flip-flops
(each normalised to a six-NAND D type), a write decoder, and a share of the read
multiplexer.

The CPU core of that first four-instruction machine, by comparison, was 806
gates against 27,406 for the whole design — three percent. That machine wrote
its results into a 100-word array which I later replaced with an output port,
precisely because the array was swamping everything else, so treat 3% as the
extreme end of the range. In the much leaner machine this ends with, the
processor logic plus its output port is 21%.

Either way you get an exchange rate, and the condition on it turns out to be the
whole story: **so long as the program has to live in writable memory**, one word
of program costs about a quarter of that first CPU. Any instruction that removes
program words pays for itself almost immediately. This is the opposite of the
intuition that minimal instruction sets are cheap, and it is why SUBLEQ loses in
this implementation — three words per instruction, five memory accesses each,
and no comparison that leaves its operands intact, so every `if` becomes a
macro.

## The curve, and where it turns

Sweep instruction sets across a five-program benchmark suite — Fibonacci,
insertion sort, shift-and-add multiply, Euclid's GCD, binary-to-decimal — and
total gate count falls steeply as you add instructions, then flattens and turns
back up.

Where the minimum sits depends on where the program lives, which is worth
looking at directly because it is the break-even rule doing its work:

| instructions | program in writable RAM | program in ROM |
|---|---:|---:|
| 7 | 49,477 | not eligible |
| 10 | 47,295 | **7,078** |
| 12 (adds two immediate forms) | **45,927** | 7,325 |
| 14 (adds AND, OR, XOR, shift) | 47,497 | 7,280 |

So there is a break-even rule, concrete and scoped: while the program must live
in writable RAM, an instruction is worth adding if it removes at least one word
of program per 196 gates it costs. The twelve-instruction variant is the rule
working. Its two immediate forms cost 182 gates of core and remove eight words
of program; in RAM those words are worth 1,568, so it comes out 1,386 gates
ahead — against a measured 1,368. In ROM the same eight words are worth about
34, so the same two instructions are a net loss, and the minimum moves to ten.
The fourteen-instruction variant loses in both columns for the dull reason that
the benchmark never executes its four logic instructions: 202 gates of decode
for nothing.

Note also that past the minimum the ROM column barely moves — 7,078, 7,325,
7,280. "Turns back up" is a 3.5% wobble there, not a cliff. Hold on to that,
and to the condition about writable RAM. The next section removes the condition,
and takes the rule with it.

That instructions reusing existing datapath are nearly free, while instructions
adding new datapath rarely pay, is qualitatively consistent with what Sakamoto,
Ahmed, Anderson and Hara-Azumi measured in *Subleq⊖: An Area-Efficient
Two-Instruction-Set Computer* — a second instruction reusing the existing
subtractor cost 1.33x area for a 2.78x speedup, while variants adding a
dedicated shifter or multiplier cost 1.87x and 5.86x and ran slower in
wall-clock terms. Their ratios are core area only, with memory outside the
comparison, which if anything makes the agreement more interesting.

## The finding that mattered

The curve turned out to be a sideshow. Sorted by gate count, the designs I built
fall into two groups with nothing in between them:

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

("Operations" means distinct primitive operations — opcodes plus memory-mapped
port behaviours — not instruction words. The last section explains why
instruction count turned out to be the wrong axis, and why a machine with one
instruction can sit at three operations.)

The boundary is whether the machine can index an array without modifying its own
code. Under the gate-built memory model used throughout, the cheapest design
that cannot is 6.7x larger than the cheapest design that can. Inside the cheap
group everything sits within 25% of everything else, across a range from three
operations to fourteen — so which side of the boundary a machine lands on has
nothing to do with how many instructions it has.

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
benchmark — ten across the suite's five indexed-access sites, plus the two
constant words the self-modifying version needs as instruction templates.

Those twelve words are worth about 2,350 gates if they sit in RAM and about 50
if they sit in ROM, and both figures matter. Priced as RAM, density alone
repays the index register's ~200 gates roughly tenfold, and the measured
seven-to-ten comparison in the table above confirms it: 2,182 gates saved. So
this is not a case of an architectural feature that fails to pay its way. It is
a case of an architectural feature whose obvious payoff is a rounding error
beside its real one.

Because what the second version also does is never write to a program word. The
program becomes read-only, and read-only storage is a completely different
circuit: a ROM word is a few gates of decode-and-OR that logic synthesis shares
across hundreds of words. Averaged over this image that is 4.3 gates per word
against 196 for RAM, about 46x in this model.

The controlled version of the comparison is this. The same ten-instruction
machine, running the same program, costs **47,295 gates with its program in
writable RAM and 9,344 with it in ROM** — a difference of 37,951 gates, with
nothing changed but where the code sits. About 200 gates of index register are
the only reason the second column is available at all. They do not save 37,951
gates; they make 37,951 gates saveable. The index register is not an
optimisation. It is a permission.

(Moving the program's twelve read-only *constants* into ROM as well takes the
total from 9,344 down to 7,078. That is a memory-map decision rather than an
architectural one, and it is available to any design, so it does not belong in
the comparison above — but it is where the headline 7,078 comes from.)

This also retires the break-even rule from the previous section. Once the
program is in ROM a word costs a few gates, not 196, so no plausible instruction
removes enough program to pay for its decode logic. That is exactly why the
cheap group is so flat: past the boundary, instruction count stops mattering
much. One honest wrinkle — 4.3 is the average over this image, and the marginal
word is content-dependent and can be near zero. The twelve-instruction variant
has eight *fewer* program words yet costs 65 more gates outside its core, which
is synthesis sharing the way synthesis does.

It is worth being plain about the shape of this argument, too. Once you grant
that every word a program writes must be full-price RAM, it follows almost by
construction that a self-modifying machine is expensive. The model is what makes
it true *that* self-modification costs; the measurements are what establish *how
much*.

And that grant is the assumption I would attack first. The expensive group
treats the program store as all-or-nothing: if any word is written, every word
is priced as RAM. That is the memory map I built, but it is not forced. The
addresses a self-modifying program patches are fixed at assembly time — `P` in
the example above is a link-time constant — so the store could be split into ROM
plus a handful of individually decoded writable words, and the seven-instruction
machine would need five of them. Priced at my own per-word figures that lands
somewhere near 8,000 gates, inside the cheap group. I have not built it, and the
last time I reasoned about an unbuilt design in this project I got both its area
and its timing wrong in opposite directions, so treat that as a sketch rather
than a result. What survives regardless is narrower and still worth having: the
index register removes the need for a writable code window altogether, and 6.7x
is what the simple memory map — one ROM region, one RAM region — costs you for
lacking it.

Two smaller caveats, because the 46x ratio is doing so much work. It is partly a
property of the memory model: real SRAM is roughly six transistors per bit
rather than six gates, and mask ROM roughly one, so with real memory macros the
gap narrows substantially, though it does not invert. Those two figures are
technology rules of thumb, not outputs of this synthesis flow. And the split
depends on the workload: my suite sorts a 16-word array, so indexing is on the
critical path. A program that never touches an array, or one you are happy to
let rewrite itself, would move the boundary or erase it.

## The design that won

Ten instructions, 16-bit words: `LDA`, `STA`, `ADD`, `SUB`, `JZ`, `JN`, `JMP`,
`LDX`, `LDAX`, `STAX`. Three registers — a 16-bit accumulator, an 8-bit index,
an 8-bit program counter — for 38 flip-flops once the state machine is included.
One shared 16-bit adder, a three-state FSM, and the next fetch overlapped onto
the last cycle of the current instruction, so nothing costs more than two
cycles.

Total 7,078 gates: 4,597 is the benchmark's own working set in RAM, 1,509 is the
processor and its output port, 912 is the entire program in ROM, and the
remaining 60 is address decode and glue.

The result looks a lot like a stripped-down PDP-8: accumulator, memory operands,
conditional branches, indexed addressing.

## What one instruction actually costs

I also built Jones's Ultimate RISC, a 1988 design whose sole instruction is
`MOVE src,dst`, with the ALU and program counter mapped to memory addresses. It
landed within 3.5% of the ten-instruction machine — which looks like a striking
win for minimalism until you notice that its destination address field selects
among ten behaviours. That is functionally an opcode field, and its core
measured larger, not smaller, because removing the opcode relocates the decoding
rather than eliminating it.

The fair comparison was to give SUBLEQ the same hardware facilities: two
addresses wired to hardware, an index register and an indirect port. Still one
instruction, now three distinct operations. It went from 164,783 gates to 8,848
— an 18.6x improvement — landing squarely in the cheap group.

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
number are in this repository. The transistor-per-bit comparisons and the
hybrid-store sketch are explicitly not. See [DESIGN.md](DESIGN.md) for the
winning machine and [project.md](project.md) for the full method.*
