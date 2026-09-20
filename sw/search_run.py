import sys, json, os, random, time; sys.path.insert(0,'sw')
import autosearch as A
dyn = json.load(open('build/dynprofile.json'))
seed = int(sys.argv[1])
rng = random.Random(seed)
t = time.time()
start = A.random_feasible(rng)
if start is None:
    print('seed %d: no feasible start' % seed); sys.exit()
s, r, used = A.hill_climb(dyn, start, rng, 120)
rec = dict(seed=seed, total=r['total'], n=len(s), cycles=r['cycles'],
           scheme=r['scheme'], core=r['core'], words=r['words'], iset=sorted(s),
           secs=round(time.time()-t))
with open('build/search_runs.jsonl','a') as f:
    f.write(json.dumps(rec)+'\n')
print('seed %2d: %6d gates  %2d instrs  %5d cyc  %-5s  %.0fs' %
      (seed, rec['total'], rec['n'], rec['cycles'], rec['scheme'], rec['secs']))
print('   ', ' '.join(rec['iset']))
