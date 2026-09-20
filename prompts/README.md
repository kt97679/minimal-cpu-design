# Reusable prompts

Extracted from the postmortem of this project. Each one exists because of a
specific failure that actually happened here, named under "Why this exists" so
the prompt is not generic advice — you can check whether the failure mode
applies to your situation before spending a turn on it.

They are written to be pasted whole into a session. Nothing in them is about
CPUs.

| | use it | guards against |
|---|---|---|
| [01-problem-framing](01-problem-framing.md) | before starting a measurement project | optimising the wrong term; a benchmark with a degenerate answer |
| [02-escape-recall](02-escape-recall.md) | whenever the task is "find the best X" | a model proposing the options history already chose, and calling it a search |
| [03-audit-tooling](03-audit-tooling.md) | before reporting any measured result | measurement tools that quietly favour the answer you already have |
| [04-expert-review](04-expert-review.md) | when a technical write-up is nearly done | overclaiming; unstated modelling assumptions |
| [05-reader-review](05-reader-review.md) | after the expert review passes | unreadable structure, repetition, no problem statement |
| [06-handling-review](06-handling-review.md) | when review feedback arrives | accepting wrong criticism, rejecting right criticism, silent drift |

## The two that mattered most

Five rounds of expert review improved this project's write-up and caught three
real errors. Two interventions from outside that cycle changed the *work*:

* a reader asking for structure, a problem statement, and less repetition —
  which no expert reviewer had mentioned, because they were all reading for
  correctness rather than for whether anyone could follow it;
* a reader pointing out that all the candidates compared were the ones that
  historically existed, so a model with that history in its weights was
  recalling rather than searching. Acting on this produced a design that beats
  the hand-made one and resembles nothing in the historical record.

If you only take two, take `02` and `05`.
