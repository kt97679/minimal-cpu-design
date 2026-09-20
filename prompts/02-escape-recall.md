# 02 — Escape recall: search the space, don't recite it

**Use it** whenever a task is "find the best X", "what is the optimal Y", or
"compare approaches to Z", and you intend to take the answer seriously.

**Why this exists.** In this project I compared SUBLEQ, an accumulator machine,
a PDP-8-alike and Jones's MOVE machine, and reported which won. A reader
pointed out that those are the branches that historically existed, so a model
with the history of computer architecture in its weights was not searching but
recalling. He was right. When I built a mechanical search instead, it found a
better design built on reverse subtract, with no add, no subtract and no
unconditional jump — a machine resembling nothing in the historical record.

Two further things surfaced that are likely to recur. First, my "mechanically
enumerated" pool was not: I claimed it contained a branch for every way of
testing the sign of a result, and it contained six of the seven — the missing
one being the condition used by the very architecture the project was about.
Second, the primitives that made the winning design work were the two I had
added *deliberately because no real machine used them*. Without those two, the
search would have confirmed my original answer and I would have believed it.

---

```
Before you propose candidates for this problem, stop and do the following.
Show your work for each step; do not skip to the answer.

1. NAME THE RECALL. List the solutions you are about to propose. For each,
   say whether it is well known, and if so, from where. If every candidate on
   your list is an existing, named thing, you are recalling, not searching,
   and the rest of these steps are mandatory.

2. ENUMERATE THE SPACE MECHANICALLY. Do not list solutions. Identify the
   independent axes the solution space actually has, and generate candidates
   as combinations of points on those axes. Write the axes down explicitly.

3. AUDIT THE ENUMERATION FOR COMPLETENESS. For each axis, state how many
   possible values it has and how many you included. If those numbers differ,
   justify every omission or fix it. Pay particular attention to values that
   are unusual, asymmetric, or that no familiar system uses — those are the
   ones a recall-driven enumeration silently drops.

4. ADD DELIBERATE STRANGERS. Include at least three candidates chosen
   specifically because no well-known system uses them, and say for each why
   it was excluded from practice: is it genuinely worse, or merely
   unfashionable, historically contingent, or bad for constraints that no
   longer apply? Keep the ones where you cannot answer.

5. SAMPLE BEFORE YOU OPTIMISE. Evaluate a uniform random sample of the space
   before running any local or greedy search. Report the distribution, not
   just the best. Local search from a hand-picked starting point inherits the
   bias of that starting point; uniform sampling shows you the shape of the
   space and tells you whether your optimum is a peak or a plateau.

6. STATE WHAT IS STILL FIXED. Everything you did not vary is an assumption:
   the framework, the representation, the interfaces, the metric. List them.
   For each, say what would change if it were varied. This list is the honest
   scope of your result, and it belongs in the write-up, not in your head.

7. REPORT THE FAILED CANDIDATES. Say which mechanically generated candidates
   could not work and why. A search that only reports its winner is
   indistinguishable from a recommendation.
```

---

## Notes

**The cheapest useful version.** If the full treatment is too expensive, step 4
alone is worth running. Adding candidates chosen *because* nobody uses them
costs one paragraph and is what produced the result here.

**Watch for "mechanically enumerated" as a claim.** It is easy to write and
hard to verify. Step 3 exists because I made exactly that claim and it was
false, and the omission was not random — it was the option that did not fit the
pattern I had in mind.

**Sampling is not optimisation.** Step 5's uniform sample will usually be worse
than local search. That is fine. Its purpose is to characterise the space and
to catch the case where local search is stuck in the neighbourhood of the
answer you started with.

**This prompt is not free.** Mechanical enumeration produces many unusable
candidates — in this project about 98.5% of uniformly drawn ones — so you need
a cheap feasibility filter before the expensive evaluation. Budget for that.
