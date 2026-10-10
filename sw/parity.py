#!/usr/bin/env python3
"""
Check that the English and Russian articles still say the same thing.

Written after rebuilding this check by hand eight times in one session, and
after it twice gave a false alarm -- once because `x` and `×` are different
characters, once because a code span had wrapped across a line. Both are
handled here so the next person does not re-diagnose them.

Three comparisons:

  structure  the sequence of block types -- heading, paragraph, table, code --
             must be identical. This catches a paragraph added to one language
             and not the other, which is the failure that actually happens.
  figures    every number must appear the same number of times in both, after
             normalising thousands separators, decimal commas and the x/×
             multiplier sign.
  tables     every table must be contiguous and have a separator row.

Numbers spelled out in words in one language are the one legitimate exception,
so they are listed explicitly rather than silently ignored.

Run: python3 sw/parity.py      (also `make parity`)
"""
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = [('ARTICLE.md', 'ARTICLE.ru.md'), ('ARTICLE-2.md', 'ARTICLE-2.ru.md')]

# numbers written as words in one language and as digits in the other
SPELLED_OUT = {'5000'}          # "a 5,000-gate machine" / "пятитысячевентильной"


def blocks(path):
    out, cur, code = [], [], False
    for line in open(path, encoding='utf-8').read().split('\n'):
        if line.startswith('```'):
            code = not code; cur.append(line); continue
        if code:
            cur.append(line); continue
        if not line.strip():
            if cur:
                out.append('\n'.join(cur)); cur = []
        else:
            cur.append(line)
    if cur:
        out.append('\n'.join(cur))
    return out


def kind(b):
    for prefix, k in (('### ', 'H3'), ('## ', 'H2'), ('# ', 'H1'),
                      ('```', 'CODE'), ('---', 'RULE')):
        if b.startswith(prefix):
            return k
    return 'TABLE' if b.lstrip().startswith('|') else 'para'


def figures(text, russian):
    """Every number, normalised across the two languages' conventions."""
    t = text.replace('\u00a0', '')          # non-breaking thousands separator
    # digits inside unit names are not figures: English writes NAND2 where
    # Russian writes "двухвходовой И-НЕ", and 6T/1T1C are cell names
    t = re.sub(r'NAND2|6T|1T1C|4T|3T|2N\d+|74HC\d+', ' ', t)
    t = t.replace('×', 'x').replace('x', ' ')   # multiplier sign is not a digit
    t = re.sub(r'(?<=\d),(?=\d)', '.' if russian else '', t)
    return Counter(re.findall(r'\d+(?:\.\d+)?', t))


def tables_well_formed(path):
    runs, cur = [], []
    for line in open(path, encoding='utf-8').read().split('\n'):
        if line.lstrip().startswith('|'):
            cur.append(line)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    return all(len(r) >= 3 and set(r[1].replace('|', '').replace(' ', '')) <= set('-:')
               for r in runs), len(runs)


def main():
    bad = 0
    for en, ru in PAIRS:
        pe, pr = os.path.join(ROOT, en), os.path.join(ROOT, ru)
        be, br = blocks(pe), blocks(pr)
        ke, kr = [kind(b) for b in be], [kind(b) for b in br]
        print('%s / %s' % (en, ru))
        if ke == kr:
            print('   structure  %d blocks, identical' % len(be))
        else:
            bad += 1
            print('   structure  %d vs %d blocks, DIFFERENT' % (len(be), len(br)))
            import difflib
            for line in list(difflib.unified_diff(ke, kr, 'EN', 'RU',
                                                  lineterm='', n=1))[:14]:
                print('     ', line)
        fe = figures(open(pe, encoding='utf-8').read(), False)
        fr = figures(open(pr, encoding='utf-8').read(), True)
        diff = {k: (fe[k], fr[k]) for k in set(fe) | set(fr)
                if fe[k] != fr[k] and k not in SPELLED_OUT}
        if diff:
            bad += 1
            print('   figures    %d disagree:' % len(diff))
            for k, (a, b) in sorted(diff.items()):
                print('      %-12s EN %d, RU %d' % (k, a, b))
        else:
            print('   figures    %d distinct, all matching' % len(fe))
        for p in (pe, pr):
            ok, n = tables_well_formed(p)
            if not ok:
                bad += 1
                print('   tables     %s: malformed' % os.path.basename(p))
        print('   tables     well formed in both')
    print()
    if bad:
        print('%d problem(s)' % bad)
        sys.exit(1)
    print('the two languages agree')


if __name__ == '__main__':
    main()
