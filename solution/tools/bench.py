"""Clean feasibility numbers - no tracemalloc during build (it inflates build time ~5x)."""
import json, os, sys, time
sys.path.insert(0, ".")
from starter.agent import Agent, MODE, GATE, FLOOR, PRIOR

CAT = r"F:/Code/Claude/CompetitionAI/techjam-conversational-search/data/catalog.jsonl"
PUB = r"F:/Code/Claude/CompetitionAI/techjam-conversational-search/data/public_set.jsonl"

t0 = time.perf_counter()
ag = Agent(CAT)
build = time.perf_counter() - t0

rss = None
try:
    import ctypes, ctypes.wintypes as wt
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                             ctypes.byref(c), c.cb)
    rss = (c.WorkingSetSize / 1e6, c.PeakWorkingSetSize / 1e6)
except Exception as e:
    pass

print(f"config           : MODE={MODE} GATE={GATE} FLOOR={FLOOR} PRIOR={PRIOR}")
print(f"index build      : {build:6.2f} s   (clean, no tracemalloc)")
if rss:
    print(f"process RSS      : {rss[0]:7.1f} MB   peak {rss[1]:7.1f} MB")
print(f"catalog on disk  : {os.path.getsize(CAT)/1e6:7.1f} MB")
print(f"coarse categories: {len(ag.cat_index)}")
print(f"span index keys  : {len(ag.cs_inv)}")

samples = [json.loads(l) for l in open(PUB, encoding="utf-8")]
msgs = ["I'm looking for Jewelry Necklaces. A key requirement is: Material:alloy.",
        "For that, what matters is: Triple Moon Pentagram Symbol; Imported.",
        "I'm looking for Shirts T-Shirts, but I'm still exploring.",
        "Actually, ignore my earlier preference. What I need is: leather."]
lat = []
for i, s in enumerate(samples[:100]):
    sid = f"bench_{i}"
    ag.reset(sid, s["user_profile"])
    for t, m in enumerate(msgs, 1):
        t0 = time.perf_counter()
        ag.respond(sid, m, t, 10)
        lat.append((time.perf_counter() - t0) * 1000)
lat.sort()
n = len(lat)
print(f"turn latency     : p50 {lat[n//2]:6.1f}  p95 {lat[int(n*.95)]:6.1f}  p99 {lat[int(n*.99)]:6.1f}"
      f"  max {lat[-1]:6.1f} ms  (n={n})")
print(f"LLM tokens       : 0 prompt / 0 completion")
