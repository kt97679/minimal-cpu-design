import sys, json, random, time; sys.path.insert(0,'sw')
import archsearch as A
dyn = json.load(open('build/dynprofile.json'))
R, X, seed0 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
rng = random.Random(seed0); random.seed(seed0)
pool = A.build_pool(R, X)
t = time.time(); best = None; bset = None
for k in range(2):
    s0 = A.seed(pool, rng, R=R)
    s, r = A.climb(pool, s0, R, X, dyn, budget=60)
    if r and (best is None or r['total'] < best['total']):
        best, bset = r, s
rec = dict(R=R, X=X, seed=seed0, total=best['total'] if best else None,
           core=best['core'] if best else None,
           cycles=best['cycles'] if best else None,
           scheme=best['scheme'] if best else None,
           n=len(bset) if bset else 0, iset=sorted(bset) if bset else [],
           secs=round(time.time()-t))
open('build/arch_runs.jsonl','a').write(json.dumps(rec)+'\n')
print('R=%d X=%d seed=%d -> %s gates, %s instrs, %s cyc, %s (%ds)' %
      (R, X, seed0, rec['total'], rec['n'], rec['cycles'], rec['scheme'], rec['secs']))
