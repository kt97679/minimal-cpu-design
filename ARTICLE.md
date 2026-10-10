# One instruction is not cheaper than ten

Computer architecture has a pretty idea in it: a processor with only one
instruction. It is called an OISC — one instruction set computer.

The best known example is SUBLEQ. It does exactly one thing: subtract the number
at address A from the number at address B and, if the result is not greater than
zero, jump to address C.

SUBLEQ is Turing complete. Any program at all can be written for it.

Because there is only one instruction, the processor needs no instruction
decoder, and its arithmetic unit comes out primitive.

One operation has a downside, though. A program written for SUBLEQ comes out
very long: where an ordinary machine manages with one command, SUBLEQ spends
several.

Which means SUBLEQ needs a lot of memory. And since every part of a computer,
memory included, is built from gates, each extra word of program is literally
extra gates.

So the question is which way it goes: does the saving on the decoder outweigh
the overspend on memory for a longer program?

## What I measured, and how

**How I counted.** The synthesiser turns a circuit into two-input NAND gates and
I count how many came out. Memory counts too: a word of RAM is flip-flops plus
the circuit that picks the right word on a write and on a read.

I count one flip-flop as six gates — the standard figure for a flip-flop built
from NANDs.

**What I measured it on.** Five programs: Fibonacci numbers, insertion sort of a
16-word array, multiplication, Euclid's algorithm, conversion to decimal.

The programs are written once in a common intermediate language and then
translated automatically into the commands of each machine.

Every machine is checked in simulation first: it has to produce the same numbers
as a reference model running on an ordinary computer. Only then do I count its
gates.

**What I compared with what.** First I compared SUBLEQ against a machine built
from the same elementary actions, but performing them separately.

Take SUBLEQ apart. It loads a value into the accumulator (the register where the
machine keeps an intermediate result), subtracts another value from it, stores
the result at an address, and jumps if the result is not greater than zero. Four
actions, four instructions.

SUBLEQ lost. At which point the question widened: which instruction set solves
this set of tasks with the fewest gates at all? To answer it I worked through
several architectures.

## 1. A machine is mostly memory

The first thing I measured was the price of memory. One 16-bit word costs 116
gates if built from latches and 196 if built from flip-flops. Where that
difference comes from, and why I quote both, comes next.

The processor of the four-instruction machine is 806 gates. The whole processor
costs as much as seven words of memory.

Which shows where to look for the minimum. There are two ways to make the
machine smaller: make the program occupy fewer words, or make a word cheaper.
Touching the processor is close to pointless — it is small already.

Take the second way first, it is short.

A memory cell has to hold a bit. The familiar way is a flip-flop: it captures
whatever is on its input at the moment of a clock pulse. Built from NAND gates,
a flip-flop costs six of them.

Memory does not need that strictness. During a write the address does not
change and exactly one word is written, so there is nothing to catch a precise
moment for. A latch is enough: while writing is enabled it passes the value
straight through, and the moment it is disabled it holds whatever was there. A
latch costs four gates instead of six.

The saving comes out larger than the difference in the cell. A flip-flop
triggers on every clock, so a word that is not being written has to be fed its
own value back — one switch per bit. A latch needs no switch: it simply is not
enabled. Of the 80 gates saved per word, the cell itself accounts for 32 and the
vanished switches for 48.

Every machine in this article was built and checked in simulation with
flip-flop memory, and the numbers in the tables are counted at 196. That does
not affect the comparison between machines: they all use the same memory, and
the swap would shrink them all by about the same amount. Chapter 4 shows what
the winner becomes with latches.

And one more thing already visible here. Neither SUBLEQ nor the four-instruction
machine can reach an array element by a computed index, so both patch their own
commands as they run. Which means their program cannot live entirely in
read-only memory. What that costs is chapter 3.

## 2. Where the minimum is

Where the minimum sits depends on where the program lives. And here two kinds of
memory have to be told apart.

RAM is memory you can write to. Each of its words is a set of flip-flops plus
the selection circuit, hence the 196 gates.

ROM is read-only memory. You cannot write to it, but it needs no flip-flops
either: the required bits are simply wired into the circuit. So a word of ROM
costs single-digit gates rather than hundreds.

A program that does not alter itself can live in ROM. A program that rewrites
itself cannot. Hence the two columns.

| instructions | program in writable RAM | program in ROM |
|---|---:|---:|
| 4 | 65,462 | not available |
| 5 | 59,125 | not available |
| 7 | 49,477 | not available |
| 10 | 47,295 | **7,078** |
| 12 (plus two immediate forms) | **45,927** | 7,325 |
| 14 (plus AND, OR, XOR, shift) | 47,497 | 7,280 |

The first two rows say "not available" in the second column, and that is not a
misprint. Machines with four and five instructions cannot reach an array element
by a computed index, so they are forced to patch their own commands as they run.
And you can only patch something that lives in writable memory.

The row with ten instructions is the first where an index register appears. That
is the architectural difference which opens the second column. What exactly it
does is the subject of chapter 3.

The first row is that dismantled SUBLEQ: load, store, subtract, jump if not
greater than zero. The machine works and passes every test.

But its only branch tests "not greater than zero", and programs need other tests
as well. Equality with zero has to be checked twice: first that x is not greater
than zero, then that minus x is not greater than zero. Seven words where the
next machine manages with two.

Split that branch in two — zero separately, negative separately — and the core
grows from 1,063 gates to 1,134 while the program shrinks from 331 words to 298.
That is 65,462 against 59,125: the fifth instruction pays for itself sixfold.

This is the first instance of the rule discussed below. An instruction is worth
adding if it shortens the program enough to justify its own circuitry.

Now the rule. While the program lives in writable RAM, an instruction is worth
adding if it removes at least one word of program per 196 gates it costs.

The twelve-instruction variant is that rule in action. Its two immediate forms
cost 182 gates and remove eight words of program. In RAM those words cost 1,568,
so the gain should be about 1,386. Measured: 1,368.

In ROM those same eight words cost about 34. The same two instructions become a
loss, and the minimum shifts to ten.

The fourteen-instruction variant loses in both columns for a duller reason: the
benchmark never once executes its four logic instructions. That is 202 gates of
decoding for nothing.

Remember that conclusion, because part 2 shows it to be wrong. There the same
machines get a task that has to compute a checksum, and the logic instructions
turn from ballast into necessities.

This behaviour is not mine alone. In the paper *Subleq⊖* by Sakamoto, Ahmed,
Anderson and Hara-Azumi, a second instruction reusing the existing subtractor
cost 1.33x the area for a 2.78x speedup, while variants with a dedicated shifter
or multiplier cost 1.87x and 5.86x and ran slower.

Past the minimum the ROM column barely moves: the difference between 7,078,
7,325 and 7,280 is 3.5%, not a cliff.

And remember the condition about writable RAM. The next chapter removes it, and
the rule goes with it.

## 3. The thing that actually mattered

The table above shows the minimum, but not the main point. The main point shows
up if you simply sort every machine by gate count: they fall into two groups,
with nothing between the groups.

One property divides them — whether a machine can reach an array element without
rewriting its own code. The one that cannot is forced to patch its own
instructions in memory; this is called self-modifying code, and I will show what
it looks like.

| | gates | operations |
|---|---|---|
| cannot index without self-modifying code | 47,295 – 164,783 | 1–7 |
| can index without self-modifying code | 7,078 – 8,848 | 3–14 |

```
5,000    10,000       20,000          50,000       100,000     200,000
┬───────────┬────────────┬───────────────┬────────────┬───────────┬
      oo  o                             xx  x                  x
      └───┘                             └──────────────────────┘
      7,078 - 8,848                     47,295 - 164,783
```

Every machine measured, by total gate count, logarithmic scale. `o` can index an
array without rewriting its own code; `x` cannot.

"Operations" here means distinct elementary actions, not instruction words.
Chapter 5 explains why instruction count is the wrong axis.

"Nothing between the groups" is a claim about something not found, so here is
where I looked. Of 129 machines drawn at random and able to run the tests, 4
landed in the cheap group and 125 in the expensive one. None in between.

Inside the cheap group everything sits within 25% of everything else, across a
range from three operations to fourteen. And that spread does not follow
instruction count either: the fourteen-operation machine beats the
twelve-operation one.

Whereas the ability to put the program in ROM is not something you get half of.
A machine either never writes to a word of program or it does. There is no third
option, and that is what splits the machines into two groups.

### Two ways to compute an address

Where does the boundary come from? None of these machines can express "element i
of the array" in an instruction: the address field is a constant wired into the
command word.

So the address has to be computed somewhere. Without an index register it is
computed in software, and the only place to put the result is the instruction
itself:

```
    LDA tmpl
    ADD i
    STA P        ; overwrites the instruction below
P:  LDA 0        ; just rewritten
    STA d
```

With an index register a small adder on the address path does it:

```
    LDX i
    LDAX ARR
    STA d
```

Five instructions become three. Across the whole benchmark that is twelve words:
ten at the five indexed-access sites, plus two constant words that the
self-modifying version needs as templates.

### Why 200 gates buy 37,951

Those twelve words cost about 2,350 gates in RAM and about 50 in ROM. Both
figures matter.

In RAM, code density alone repays the index register's 200 gates tenfold. And
that is not a separate calculation: twelve words at 196 gates less 198 gates of
extra core gives 2,154, against a measured seven-to-ten difference of 2,182. A
residue of 28 gates.

So this is not a feature that fails to pay its way. It is a feature whose
obvious payoff is an order of magnitude smaller than its real one.

The real one is this. The second version never writes to a word of program. The
program becomes read-only.

And read-only memory is an entirely different circuit. A word of ROM is a few
gates that synthesis shares between hundreds of words. On average 4.3 gates a
word against 196 for RAM — a factor of 46.

Now let us compare so that exactly one thing changes. The same ten-instruction
machine, running the same program, costs **47,295 gates with its program in RAM
and 9,344 with its program in ROM**. Only the place the code sits changes.

The index register is the only reason the second column exists at all. It does
not save those 37,951 gates. It makes them saveable.

**An index register is not an optimisation. It is a permission.**

(Moving the program's twelve constants into ROM as well brings the total down to
7,078, which is where the headline figure comes from. But that is a memory-map
decision available to any machine, so it has no place in the comparison.)

This also retires the rule from chapter 2. When the program is in ROM a word
costs single-digit gates, not 196. No sensible instruction removes enough code
to justify its own decoding. Which is exactly why the cheap group is so flat.

With one exception, which part 2 comes to: an instruction that removes code by
the hundred words rather than one at a time.

### What this does not prove

*4.3 is an average, not the price of the next word.* The average is taken over
the whole program image. The twelve-instruction variant has eight fewer words of
program and costs 65 gates more outside its core, because synthesised ROM is
priced by address width and content structure, not by word count.

*The argument is partly circular.* Once we accept that any word a program writes
to must be full-price RAM, the expense of a self-modifying machine follows almost
by definition. The model makes it true *that* self-modification costs. The
measurements establish *how much*.

*The indivisibility of program memory was an assumption.* When I finally checked
it, almost nothing was left of the factor of 6.7.

The addresses a self-modifying program patches are known at assembly time. So
the store can be made of ROM plus a handful of individually decoded writable
words: the seven-instruction machine needs five, one per indexed-access site.

Each such word costs about 220 gates: a register, a comparator and a multiplexer
leg. Against 200 for a word of ordinary RAM. Measured: **8,141 gates against
7,078 for the ten-instruction machine, a ratio of 1.15 rather than 6.7.**

The mechanism survives, the magnitude does not. Writable storage still costs
about 220 gates a word against 4.3 for read-only.

What does not survive is the idea that a machine rewriting its own code must pay
for writable *program memory*. It pays for the words it actually writes, and
there are five of them.

Let us decompose it so that one variable is compared rather than three. The
index group costs 198 gates of core, removes five writable words at about 220
each and about 35 words of program at 4.3 each. A net saving of 1,052 gates
against a measured difference of 1,063.

So the index register is worth about 15% of a 7,000-gate machine. Still the
largest single instruction-set effect measured here. But 15%, not 570%.

**The factor of 6.7 is the price of a coarse memory map. And a coarse memory map
is a designer's decision, not a law of nature.**

And one more thing the preceding chapters could not see. Every comparison above
counts *cycles*. But cycles measure time only if the clock period is the same.

It is not the same. The index register puts an adder in the address path, and
measured on an FPGA that costs **11.5% of the clock**: 93.8 MHz without it
against 83.1 with it. Placing the circuit comes out slightly differently each
time and the spread between runs is 6.5%, so a difference of 11.5% is well clear
of it and real.

Which means the index register buys a large reduction in area at the price of
time. That is the opposite of how index registers are usually sold.

*The factor of 46 is partly a property of the technology.* Real static memory
costs about six transistors a bit rather than six gates, and mask ROM about one.
With real memory blocks the gap narrows considerably, though it does not invert.

*The workload matters.* My benchmark sorts an array, so indexing is on the
critical path. A program that never touches an array would move the boundary or
erase it.

## 4. The best machine I designed

This is the machine I arrived at by hand. Chapter 6 describes a smaller one,
found by searching rather than designed.

### The instruction set

Ten instructions, 16-bit words: `LDA`, `STA`, `ADD`, `SUB`, `JZ`, `JN`, `JMP`,
`LDX`, `LDAX`, `STAX`.

Three registers: a 16-bit accumulator, an 8-bit index, an 8-bit program counter.
Together with the state machine that is 38 flip-flops.

One shared adder, a three-state machine, and the next instruction's fetch
overlapped onto the last cycle of the current one. So nothing costs more than
two cycles.

### The gate budget

```
######################################=============........:
└───────────── data RAM ──────────────┘└── core ───┘└ ROM ─┘

data RAM     4,597  65%
core         1,509  21%
ROM            912  13%
glue            60   1%
```

Where the 7,078 gates go. One character of the bar is about 118 gates.

### The cheapest version of it

This budget is what every comparison in the article was measured against. But
swap the data RAM for the latch file of chapter 1 and drop the register on its
output, and the same machine comes out cheaper:

```
measured as published                      7,078
combinational read instead of registered   6,982   -96
gated D latches instead of flip-flops      5,144   -1,838
```

**5,144 gates, 27% smaller, with no cycle cost.**

Nowhere in the article do I restate things in those terms. Every machine being
compared uses the same memory, the change scales them together, and the ranking
stays as it was.

This is the largest single reduction in the whole project. And it came from the
one component that had been treated as a fixed cost rather than a design.

### Ancestors

What came out looks a lot like a stripped-down PDP-8. Given that I designed it
by hand, that is exactly the problem chapter 6 is about.

Here is what is curious, though: nearly every conclusion in this article was
already load-bearing in machines built when gates were expensive for real.

The **6502** gives the first 256 bytes of memory a shortened addressing mode.
`LDA $12` is two bytes and three cycles where `LDA $0012` is three and four. The
same relationship as in chapter 1: shortening the program pays. Only here it is
paid for in address bits rather than gates.

With a single accumulator, the 6502's zero page is exactly where it keeps the
variables my machine keeps in its 23 words of RAM. And its `,X` and `(zp),Y`
modes do what `LDAX` and `STAX` do here.

The **Apollo Guidance Computer** confirms three conclusions at once.

Its program lived in 36,864 words of core-rope ROM against 2,048 words of
erasable memory. A ratio of 18:1 — the same shape as the 212 words of ROM
against 23 words of RAM here.

Rope memory stored twelve 16-bit words on a single core, while erasable memory
used one core per *bit*. A density ratio far beyond my measured 46x: in the
1960s writable storage was dearer still.

And the first seven addresses of its address space were not memory at all but
hardware registers: accumulator, program counter, return address, a
constant-zero register. Precisely the trick chapter 5 is about.

I arrived at none of this by reading about those machines. It is what falls out
of counting gates — and probably the most reassuring result here.

## 5. What "one instruction" actually costs

### The MOVE machine

I also built Jones's Ultimate RISC, a 1988 architecture whose only instruction is
`MOVE src,dst`, with the ALU and program counter mapped onto memory addresses.

It fell only 3.5% behind the ten-instruction machine. That looks like a victory
for minimalism — until you notice that its destination address field selects
among ten behaviours.

Functionally that is an opcode field. Not merely a memory-mapped register: it
chooses the operation itself, not just where the result goes.

And its core measured *larger*, not smaller. Removing the opcode relocates the
decoding rather than eliminating it.

### SUBLEQ with the same hardware

The fair comparison was to give SUBLEQ the same facilities: an index register and
an indirect port, wired to two addresses.

Still one instruction, now three operations. The machine went from 164,783 gates
to 8,848 — an improvement of 18.6x — and landed firmly in the cheap group.

So SUBLEQ's large area penalty was driven far more by addressing than by having
one opcode.

Its three-word instruction format did not change, and that is most of the 25%
still separating it from the winner. It also still loses on time: no amount of
wiring gives it a native comparison or addition.

But the area gap was never really about the number of instructions.

## 6. Was that a search, or a recollection?

Every machine compared above is one I chose. And the ones I chose are the
branches that actually existed.

A model that has read the whole history of computer architecture proposes
SUBLEQ, an accumulator machine and the Ultimate RISC, and then announces a
winner. That is not a search, it is a recollection. The objection is fair, and
the answer to it has to be code.

So I wrote a search. The list of candidate instructions is assembled
mechanically: every operation in every addressing mode, plus a branch for every
way of testing the result. That gives 31 candidates, and none of them got there
because a real machine had it.

The code is generated by search too, not by hand-written macros. The Verilog is
emitted from the instruction list and synthesised for real. The starting points
are random subsets, rejected until one can run the benchmark.

My first candidate list turned out to be less mechanical than I claimed. I wrote
"a branch for every way of testing the result" and included six of the seven.
The missing one was "branch if not positive" — SUBLEQ's own condition.

I had also filled the arithmetic slots with the operations real machines have.
Adding the missing branch and two primitives such machines did not have —
reverse subtract and NAND — changed the answer.

First, plain random sets of instructions with no improvement at all. About 8,800
draws, 129 working machines. They fall into the same two groups: 7,505–7,900
gates with an index register, 50,755–87,715 with self-modification. Nothing
between them.

Then a search that improves step by step: take a working machine, try adding or
removing one instruction, keep whichever comes out better. And it beat my
machine. The best one found has no ADD, no SUB and no JMP:

```
JN JZ LDX_D LD_D LD_X RSB_D RSB_X ST_D ST_X XOR_D XOR_X
```

Reverse subtract does the work of both. The compiler emits `a + b` as
`LD d; RSB Kz; RSB s; ST d`, and `a - b` in three instructions with no SUB in the
machine at all. An unconditional jump is `LD Kz; JZ`.

Compiled and synthesised through the same pipeline, it gives 6,959 gates against
7,161 for the ten-instruction machine: 2.8% smaller and 13% slower.

And one more search, in which the operations were not chosen but grown. Each
instruction became an expression tree over the accumulator and the operand, from
`{+ - & | ^ ~ shift}` and constants. Crossover swapped subtrees between machines.

Given no named operation at all, it converged on a machine with **no
subtractor**: load, load-complement, add. The compiler works out `d - s` itself,
through complement and addition.

On gates that ties the reverse-subtract machine: 6,738 against 6,747, inside the
model's error. So the honest claim is not that it won. It reached the same answer
from nothing, where the previous search needed me to put reverse subtract into
the list myself.

And when the clock was measured, it turned out to be the fastest machine here:
8.6% quicker in real time, because a shorter datapath clocks faster.

That is also where searching stopped paying. Eleven runs converged into a band
one and a half percent wide against a model that errs by three. And one check
makes that floor tangible: two of the grown slots compute the same value, so
deleting one ought to save gates — and it costs twelve.

What is left needs a better measurement, not a better search.

Then I put the skeleton of the machine into the search as well: the number of
data registers and the number of index registers also came up for variation. One
accumulator turned out to be the right choice.

Every architecture from one to three registers lands in the same band of
6,772–7,319 gates, which is inside the error. A second accumulator costs
flip-flops and decoding that no shortening of code repays.

And the factor of 8 appears for a third time independently: the machines that can
index land in that same band, the ones that cannot land between 50,640 and
56,749.

What remains mine after all of this is less than it was at the start of the
chapter: one memory port, one word per instruction, 16-bit data, and an
instruction executed in three cycles. Each one a stated assumption with a reason,
rather than an unexamined habit.

## Part 2

Everything above was measured on five textbook kernels. Two of its conclusions
turn out to be facts about that set of tests rather than about instruction sets.

[Part 2](ARTICLE-2.md) gives the same machines a workload shaped like real
firmware: a checksum, a subroutine, a result formatted for a serial line. And it
asks what any of it means on silicon, where memory is made of SRAM and flash
rather than gates.

---

*Every gate and cycle count is measured. The Verilog descriptions, the benchmark
suite, the synthesis scripts and a Makefile that reproduces every number are in
this repository, and `make verify` recomputes the published figures and compares
them against a recorded baseline, so a reader can check them rather than trust
them.*

*Two words about the measurement itself, since several comparisons here are
narrower than two percent. The same circuit rewritten seven logically neutral
ways gives the same gate count every time, so there is no spelling noise to hide
behind. And all sixteen opcode values have been run against both the circuit and
the reference model, so the compiler, the assembler and the processor understand
each one the same way.*

*The transistors-per-bit comparisons are not measurements. The winning machine is
described in [DESIGN.md](DESIGN.md), the full method in
[project.md](project.md).*
