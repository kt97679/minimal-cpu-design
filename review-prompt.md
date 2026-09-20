# Review prompt for ARTICLE.md

*(This is the project-specific instance. The generalised, reusable version is
[prompts/04-expert-review.md](prompts/04-expert-review.md), along with five
other prompts extracted from this project's postmortem — see
[prompts/README.md](prompts/README.md).)*

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

- The project began as a two-way comparison, SUBLEQ against a four-instruction
  accumulator machine (load, store, subtract, branch-if-zero), and widened into
  a search for the instruction set that costs the fewest gates. Several CPU
  designs were written in Verilog, simulated with Icarus Verilog,
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
- Known caveats the author is aware of: the expensive cluster assumes a
  monolithic writable program store, and a hybrid store with a few individually
  decoded writable words is sketched but not built; the benchmark is small; comparison is
  done by subtract-and-test-sign, so test values are kept under 2^14 to avoid
  overflow; and the 16-word array is a large fraction of the final design's
  memory.

THE LOAD-BEARING CLAIMS — attack each one specifically
These are paraphrases for your convenience. Where a paraphrase and the article
disagree, the article governs: quote the article, not this list.

1. Under a gate-built memory model, a 16-bit word of writable RAM costs ~196
   NAND-equivalents, which makes the processor a small fraction of the machine
   (3% of the first design, 21% of the last).
2. While the program must live in writable RAM, an instruction pays for itself
   if it removes at least one word of program per 196 gates it costs — and this
   rule stops applying once the program can live in ROM.
3. The minimum moves with the regime: with the program in writable RAM the
   cheapest set measured is twelve instructions (45,927 gates); with it in ROM
   the cheapest is ten (7,078), and past that the ROM column varies by only
   3.5%.
4. The measured designs fall into two groups. The cheapest design that cannot
   index without self-modifying code is 6.7x larger than the cheapest design
   that can; inside the cheap group everything is within 25%, and the spread
   there does not track instruction count.
5. The same ten-instruction machine running the same program costs 47,295 gates
   with its code in RAM and 9,344 with it in ROM. The ~200 gates of index
   register do not save those 37,951 gates; they make them saveable. (Moving
   read-only constants to ROM as well gives the headline 7,078, but that is a
   memory-map decision available to any design.)
6. SUBLEQ's area penalty in this experiment is driven far more by addressing
   than by instruction count: given two memory-mapped ports it drops from
   164,783 gates to 8,848.

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

---

## Note on keeping this prompt current

The claims list above is a paraphrase of the article, and it has drifted once
already: a reviewer given a stale version spent three of its findings attacking
wording that had been fixed two commits earlier, and proposing fixes the article
had already adopted. That is the prompt's fault, not the reviewer's.

If `ARTICLE.md` changes materially, update the claims list in the same commit,
and keep the line telling the reviewer that the article governs where the two
disagree.
