# Part 2: what changes when you make it practical

[Part 1](ARTICLE.md) built minimal CPUs out of logic gates and counted them,
memory included. It found that a 16-bit word of gate-built RAM costs about 196
NAND-equivalents, so the machine is mostly memory; that the decisive property of
an instruction set is whether it lets the program be read-only; that instruction
count is the wrong axis; and that ten instructions won, until a mechanical
search beat them with a machine built on reverse subtract.

All of that was measured against five textbook kernels. This part asks two
questions the first could not. What survives a workload that looks like actual
firmware? And what does any of it mean on silicon, where memory is SRAM and
flash rather than flip-flops?

## 1. A workload with a checksum and a subroutine

Sixteen samples in a buffer. Scan them for sum, minimum and maximum; compute a
CRC-16 with polynomial 0x1021, most significant bit first; print all four
results as five decimal digits each, through **one subroutine called four
times**. Twenty output values, checked against a directly computed model.

Three things about that shape matter, and the old suite had none of them: it
manipulates bits, it repeats itself, and it is code-heavy rather than
data-heavy.

## 2. The logic instructions were not dead weight

Part 1 reports that the fourteen-instruction variant carried `AND`, `OR`, `XOR`
and a shift that the benchmark never executed, and calls them 202 gates of
decode for nothing.

A CRC needs XOR, and the ten-instruction winner has no logic operation at all.

XOR is not unreachable on a machine with only add, subtract and branches — it
can be synthesised one bit at a time. But the checksum needs about 384 of them,
each becoming roughly 128 operations, so it costs about fifty times what it
should. My compiler rejects the machine outright because it cannot express XOR
in straight-line code; the accurate statement is not that it cannot run the
workload but that it cannot run it at a price anyone would pay.

"Dead weight" was a fact about the benchmark.

## 3. CALL and RETURN pay for themselves

No machine in part 1 had a subroutine instruction. The decimal formatter here is
called four times, so a machine without one must inline fifty-five operations at
every site.

| | code words | core gates | total | cycles |
|---|---:|---:|---:|---:|
| calls inlined | 326 | 1,226 | 8,058 | 30,092 |
| with CALL and RETURN | **160** | 1,405 | **7,523** | 30,100 |

A link register, one level deep: **−166 words, +179 gates of core, −535 gates
net**, cycles unchanged.

This is the first instruction group in the whole project to clear the break-even
bar once the program is in ROM, and the reason is worth stating precisely. Part
1's rule is that an instruction earns its place by removing a word of program
per 196 gates it costs — and once a word costs four gates instead of 196,
nothing clears it. Every instruction tested up to this point removed *one word
per call site*. This one removes a whole body, three times over. The rule was
right; the range of instruction sizes I had tested was too narrow to show what
it permitted.

## 4. The stack machine still loses

Forth's code density is the standing argument against accumulator machines, so I
built a stack machine too: mechanically enumerated pool, a compiler that
searches over stack states rather than using hand-written postfix rules, Verilog
generated and synthesised like everything else.

One thing it gets for free. `push base; push i; add; fetch` is how a stack
machine indexes, so it never needs an index register or self-modifying code. By
construction it lands on the cheap side of part 1's central divide.

| machine | gates | code words | cycles | core |
|---|---:|---:|---:|---:|
| accumulator + XOR + CALL/RET | **7,523** | 160 | 30,100 | 1,405 |
| stack + XOR + CALL/RET | 8,355 | 179 | 30,204 | 2,155 |

It loses by 11% here and by 12% on the original suite. I had predicted the gap
would close on a code-heavy workload with subroutines, since factoring is where
Forth's density actually lives. It did not, and the reason is structural:
`LOAD`, `LIT`, `STORE` and every branch carry an operand field whatever the
machine, so only the ALU operations are genuinely zero-address. Factoring helps
both machines equally. It does not pay for three 16-bit stack registers where
the other machine has one accumulator and an 8-bit index.

## 5. The machine that survives

About twelve instructions:

```
LD  ST            load and store, direct
LDX LDAX STAX     index register, indexed load and store
RSB               reverse subtract  (does the work of add and subtract)
XOR               for checksums
JZ  JN  JMP       branch on zero, on sign, always
CALL RET          subroutine, one level, via a link register
```

7,523 gates on the firmware workload, of which 5,400 is the workload's own data.
Which is to say: a PDP-8 with a checksum instruction and a link register.

## 6. What real microcontrollers say

Everything above prices memory as flip-flops, because the premise was a computer
built entirely from gates. Real silicon does not work that way, and the
difference decides how much of this transfers.

### Cores

ARM quotes the Cortex-M0 at about 12,000 gates in minimum configuration; one
vendor source puts it near 25,000 in NAND2-equivalents, which is the unit used
throughout this project. The M0+ is around 15,000, the M3 around 43,000, the M4
around 150,000.

Against that, the machine above is 1,405 gates: roughly nine to eighteen times
smaller, depending on whose unit you take — and the unit ambiguity is real, so
treat the ratio as a range rather than a figure.

That gap is not waste. An M0 is 32-bit where this is 16-bit, pipelined where
this is a three-state sequencer, and has sixteen registers, interrupts, a
single-cycle multiplier and debug hardware, none of which this has. The
comparison says what a decade of features costs, not that ARM was careless.

### Memory, which is the real story

| storage | gate-equivalents per bit |
|---|---:|
| flip-flop RAM, as built in part 1 | 12.5 |
| 6T SRAM cell | 1.5 |
| 1T flash or mask ROM | 0.25 |
| the synthesised ROM in part 1 | 0.27 |

Two things fall out of that table.

**Part 1's ROM was already realistic.** At 0.27 gate-equivalents per bit, the
synthesised ROM is within 10% of a flash cell. That half of the model needed no
correction.

**The writable-to-read-only ratio collapses from 47x to 6x.** Part 1's central
claim — that an index register is not an optimisation but a permission to put
the program in cheap memory — survives in direction and loses most of its
magnitude. On real silicon it is worth about 6x, not 47x.

### And then it inverts, twice

Rebuild the same twelve-instruction machine with real memory instead of
flip-flops:

| | memory, gate-equivalents | core share |
|---|---:|---:|
| as built in part 1 (gate RAM) | 5,400 | 19% |
| same machine, 6T SRAM | 648 | **52%** |
| with 4 KB of SRAM | 49,152 | 2.7% |
| with 128 KB of SRAM | 1,572,864 | 0.09% |

At this size, real SRAM inverts part 1's headline finding: the core becomes half
the machine and the instruction set matters again, more than anything part 1
concluded.

And then a real microcontroller inverts it back, much harder. Give the same core
4 KB of RAM — modest by any modern standard — and it is 2.7% of the silicon.
Give it 128 KB and it is a rounding error at 0.09%.

But this is a different kind of domination from part 1's. There, memory was
large because the *instruction set* made the program large, and a better
instruction set shrank it. Here, memory is large because the *application* needs
it, and no instruction set touches that at all.

So the honest summary for anyone choosing a real microcontroller: the thing part
1 measured so carefully decides one to three percent of the die, and the
remaining ninety-seven is set by how much RAM your application needs. The
interesting question stops being which instructions the machine has and becomes
what the memory is for.

## 7. What survives

Three things transfer out of both parts.

**Count the whole machine, not the interesting part.** The processor was 3% of
part 1's first design and is 0.09% of a microcontroller with 128 KB of RAM. Any
argument about instruction sets that does not price the memory is an argument
about the small end of the budget.

**Whether a program must be writable is a real architectural property**, worth
6x on silicon and 47x in gates, and exactly one instruction group decides it.
That is the finding that survived every change of benchmark and cost model.

**And the benchmark was the limiting factor twice.** Once in part 1, where the
task was so small that a hardwired state machine beat every computer; and again
here, where a workload with no bit manipulation and no repeated structure could
not see two of the things an instruction set is for. Optimising against a
benchmark optimises against its blind spots as well, and those are far harder to
notice than an arithmetic error.

---

*All gate and cycle counts are measured: the RTL, both benchmark suites, the
search machinery and a Makefile that reproduces every number are in this
repository. The per-bit figures for SRAM and flash are standard cell structures,
not outputs of this flow, and the microcontroller gate counts are vendor figures
whose units differ from each other. See [project.md](project.md) for the full
method and [part 1](ARTICLE.md) for where this started.*
