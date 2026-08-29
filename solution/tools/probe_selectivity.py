"""Measure selectivity of each observable signal, to size the ranking headroom."""
import json, math, statistics, collections, sys
sys.path.insert(0, ".")
from starter.agent import intent_card, coarse_category, norm, searchable_text

CAT = r"F:/Code/Claude/CompetitionAI/techjam-conversational-search/data/catalog.jsonl"
PUB = r"F:/Code/Claude/CompetitionAI/techjam-conversational-search/data/public_set.jsonl"

prod, card, cat, corpus = {}, {}, {}, {}
for line in open(CAT, encoding="utf-8"):
    p = json.loads(line)
    a = p["parent_asin"]
    prod[a] = p
    card[a] = [norm(c) for c in intent_card(p)["all"]]
    cat[a] = norm(coarse_category([str(v) for v in (p.get("categories") or [])]))
    corpus[a] = norm(searchable_text(p))

buckets = collections.defaultdict(list)
for a, c in cat.items():
    buckets[c].append(a)

sessions = [json.loads(l) for l in open(PUB, encoding="utf-8")]

PRIORS = {
    "logRN*AR":  lambda p: math.log1p(p.get("rating_number") or 0) * (p.get("average_rating") or 0) / 5,
    "logRN":     lambda p: math.log1p(p.get("rating_number") or 0),
    "RN":        lambda p: float(p.get("rating_number") or 0),
    "logRN+AR":  lambda p: math.log1p(p.get("rating_number") or 0) + 0.5 * (p.get("average_rating") or 0),
    "logRN*AR+price": lambda p: math.log1p(p.get("rating_number") or 0) * (p.get("average_rating") or 0) / 5
                                + (0.7 if p.get("price") not in (None, "") else 0),
    "const":     lambda p: 0.0,
}


def eval_pool(pools, prior):
    """pools: sample_id -> list of candidate asins; returns hit@10, MRR over targets."""
    hits, rr, sizes = 0, [], []
    for s in sessions:
        t = s["ground_truth"]["parent_asin"]
        pool = pools[s["sample_id"]]
        sizes.append(len(pool))
        ranked = sorted(pool, key=lambda a: (-prior(prod[a]), a))
        if t in ranked[:10]:
            hits += 1
            rr.append(1.0 / (ranked.index(t) + 1))
        else:
            rr.append(0.0)
    return hits / len(sessions), statistics.fmean(rr), statistics.median(sizes)


print("=== A. Turn-1 BROWSING pool = exact coarse-category bucket ===")
pools = {s["sample_id"]: buckets[cat[s["ground_truth"]["parent_asin"]]] for s in sessions}
for name, f in PRIORS.items():
    h, m, sz = eval_pool(pools, f)
    print(f"  {name:18s} hit@10={h:.3f}  MRR={m:.3f}  median|pool|={sz:.0f}")

print()
print("=== B. Turn-1 BUYING pool = bucket AND card.all[0] == disclosed constraint ===")
slot_pools, loose_pools, sizes0 = {}, {}, []
for s in sessions:
    t = s["ground_truth"]["parent_asin"]
    c0 = card[t][0]
    b = buckets[cat[t]]
    slot_pools[s["sample_id"]] = [a for a in b if card[a] and card[a][0] == c0] or b
    loose_pools[s["sample_id"]] = [a for a in b if c0 in card[a]] or b
for label, pl in (("slot[0]==c", slot_pools), ("c in card", loose_pools)):
    for name in ("logRN*AR", "logRN"):
        h, m, sz = eval_pool(pl, PRIORS[name])
        print(f"  {label:12s} {name:10s} hit@10={h:.3f}  MRR={m:.3f}  median|pool|={sz:.0f}")

print()
print("=== C. Turn-2 pool = bucket AND first TWO card slots known ===")
p2 = {}
for s in sessions:
    t = s["ground_truth"]["parent_asin"]
    b = buckets[cat[t]]
    c0, c1 = (card[t] + ["", ""])[:2]
    p2[s["sample_id"]] = [a for a in b if len(card[a]) > 1 and card[a][0] == c0 and card[a][1] == c1] or b
for name in ("logRN*AR", "logRN"):
    h, m, sz = eval_pool(p2, PRIORS[name])
    print(f"  slots0,1     {name:10s} hit@10={h:.3f}  MRR={m:.3f}  median|pool|={sz:.0f}")

print()
print("=== D. Turn-2/3 pool = bucket AND ALL FOUR card slots known ===")
p4 = {}
for s in sessions:
    t = s["ground_truth"]["parent_asin"]
    b = buckets[cat[t]]
    ct = card[t]
    p4[s["sample_id"]] = [a for a in b if card[a] == ct] or b
for name in ("logRN*AR",):
    h, m, sz = eval_pool(p4, PRIORS[name])
    print(f"  slots0..3    {name:10s} hit@10={h:.3f}  MRR={m:.3f}  median|pool|={sz:.0f}")
n_unique = sum(1 for s in sessions if len(p4[s["sample_id"]]) == 1)
print(f"  sessions where full card is UNIQUE in bucket: {n_unique}/{len(sessions)}")
sz4 = sorted(len(p4[s["sample_id"]]) for s in sessions)
print("  |pool| after 4 slots: p50=%d p75=%d p90=%d max=%d" % (
    sz4[len(sz4)//2], sz4[3*len(sz4)//4], sz4[int(len(sz4)*.9)], sz4[-1]))

print()
print("=== E. Does the exact coarse-category string ever miss the target's bucket? ===")
bad = [s["sample_id"] for s in sessions if s["ground_truth"]["parent_asin"] not in buckets[cat[s["ground_truth"]["parent_asin"]]]]
print("  targets outside own bucket:", len(bad))
bsz = sorted(len(buckets[cat[s["ground_truth"]["parent_asin"]]]) for s in sessions)
print("  |bucket| p10=%d p25=%d p50=%d p75=%d p90=%d max=%d" % (
    bsz[int(len(bsz)*.1)], bsz[len(bsz)//4], bsz[len(bsz)//2], bsz[3*len(bsz)//4], bsz[int(len(bsz)*.9)], bsz[-1]))

print()
print("=== F. Global uniqueness of the full 4-slot card across the WHOLE catalog ===")
gidx = collections.Counter(tuple(v) for v in card.values())
u = sum(1 for s in sessions if gidx[tuple(card[s["ground_truth"]["parent_asin"]])] == 1)
print(f"  targets whose full card is globally unique: {u}/{len(sessions)}")
dup = sorted((gidx[tuple(card[s['ground_truth']['parent_asin']])] for s in sessions), reverse=True)[:12]
print("  worst global collision counts:", dup)
