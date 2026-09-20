# Review prompt for ARTICLE.md

A prompt for asking a different model (or a human reviewer) to critique
[ARTICLE.md](ARTICLE.md). It is written to draw out real objections rather than
praise: it front-loads the method so the reviewer can judge whether the
conclusions follow, names the six load-bearing claims so each gets attacked
individually, and puts "what it does well" last and conditional.

Two notes on using it:

* Run it against a model that has not seen the work being done, so it reacts to
  the article cold, the way a reader would.
* For a second, complementary pass, swap the framing sentence for something like
  *"act as a copy editor optimising for reader retention; ignore technical
  correctness."* The reviewer below will concentrate on the claims and skim the
  prose, so the two passes cover different failure modes.

Paste the full text of `ARTICLE.md` where the prompt says to.

---

```
You are reviewing a short technical article for publication. Act as a skeptical
reviewer with a background in computer architecture and digital design — the kind
who would catch an overclaim in a conference submission. Your job is to find what
is wrong, weak, or unsupported. Do not open with praise, do not pad, and do not
rewrite the article wholesale.

AUDIENCE AND VENUE
Working programmers and hardware-curious engineers reading a technical blog.
They know what a CPU and a logic gate are. They may not know what SUBLEQ, Yosys,
or a one-instruction set computer is. Target length is roughly what it is now;
it should not grow.

WHAT THE ARTICLE REPORTS, AND HOW THE NUMBERS WERE PRODUCED
This matters for judging whether the conclusions follow, so read it before the
article itself.

- Several CPU designs were written in Verilog, simulated with Icarus Verilog,
  and synthesised with Yosys mapped to 2-input NAND gates (`abc -g NAND`), with
  every flip-flop normalised to a plain D type and counted as 6 NANDs. All gate
  figures are measured, not estimated.
- All designs share one microarchitecture: 16-bit word, a single-port
  synchronous RAM with one cycle of read latency, and the next instruction's
  fetch overlapped onto the last cycle of the current one. The instruction set
  is the only variable.
- Memory is modelled as a gate-built flip-flop register file, because the
  premise is "build the whole computer out of primitive gates." ROM is a
  synthesised case statement. Real SRAM would be far cheaper per bit than the
  ~196 gates/word figure, which changes the absolute numbers though the author
  argues not the ranking.
- The benchmark is five programs — Fibonacci, insertion sort of 16 words,
  shift-and-add multiply, Euclid's GCD, binary-to-decimal — written once in a
  small virtual ISA and macro-expanded per target, so every machine provably
  runs the same algorithm on the same data. Every design was verified in RTL
  simulation against a golden model before any gate was counted.
- Known caveats the author is aware of: the benchmark is small; comparison is
  done by subtract-and-test-sign, so test values are kept under 2^14 to avoid
  overflow; and the 16-word array is a large fraction of the final design's
  memory.

THE LOAD-BEARING CLAIMS — attack each one specifically
1. A 16-bit word of gate-built RAM costs ~196 NAND-equivalents, making the CPU
   core ~3% of the machine.
2. Total gate count as a function of instruction-set size has a minimum at ten
   instructions and rises after it.
3. The break-even rule: an instruction pays for itself if it removes at least
   one word of program per 196 gates it costs.
4. The design space splits into two clusters separated by 7x, and the boundary
   is whether the machine can index an array without self-modifying code.
5. An index register costs 210 gates and buys a 42,399-gate saving — not by
   shortening code (12 words, ~50 gates) but by making the program read-only,
   where a word costs 4.3 gates instead of 196.
6. SUBLEQ's inefficiency is about addressing, not about having one instruction;
   given two memory-mapped ports it drops from 164,783 gates to 8,848.

For each: does the stated evidence actually support it? Is it stated more
strongly than the evidence allows? Would a hostile expert have an obvious
counterexample or an "it depends on X" that the article does not address? Is any
claim true only because of a modelling choice (flip-flop RAM, this particular
benchmark, this word width) that a reader would not notice?

ALSO REVIEW
- Structure and argument: does the piece earn its conclusion, or does it assert
  it? Is anything essential missing? Is anything present that could be cut?
- The opening and closing: does the first paragraph make a reader continue, and
  does the last line land?
- Clarity: mark any sentence that would stop a competent reader who does not
  already know this material. Flag jargon introduced without definition.
- Tone: flag anything that reads as smug, hedged into meaninglessness, or like
  marketing.

OUT OF SCOPE
Do not propose new experiments or redesigns of the CPU. Do not change the
numbers — they are measured, and if one looks wrong, say so rather than
correcting it. Do not reformat into a different genre (paper, listicle, thread).

OUTPUT
1. A verdict in two or three sentences: publishable as is, publishable after
   specific fixes, or not yet, and why.
2. The three most serious problems, most serious first. For each: quote the
   exact text, say what is wrong, and give a concrete fix.
3. A list of smaller issues, each as quote + problem + fix, in document order.
4. Anything you believe is factually wrong or internally inconsistent, including
   arithmetic that does not check out.
5. One short paragraph on what the article does well — last, and only if true.

If the article is genuinely sound, say so plainly rather than inventing problems
to fill the sections.

ARTICLE FOLLOWS
---
[paste the full text of ARTICLE.md here]
```
