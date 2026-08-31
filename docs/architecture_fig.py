"""Paper-style architecture figure for the seven-stage pipeline (PNG + PDF).

Usage:  python docs/architecture_fig.py
Output: docs/architecture.png (300 dpi), docs/architecture.pdf
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "text.color": "#111111",
})

INK = "#111111"
MUTED = "#555555"
ACCENT = "#1f4e9c"
FILL = "#f7f7f7"
ACCENT_FILL = "#eef2fa"

STAGES = [
    ("1 · Parsing", ["template →", "fuzzy fallback"]),
    ("2 · Dialogue state", ["typed constraints", "override handling"]),
    ("3 · Retrieval", ["category + BM25", "never-evict", "cascade filter"]),
    ("4 · Belief scoring", ["replay customer", "reply policy", "per candidate"]),
    ("5 · Ranking", ["belief-aware", "linear scorer", "gated quality prior"]),
    ("6 · Guidance", ["EIG question pick", "confidence-aware", "reply style"]),
    ("7 · Exposure", ["top-1 by default", "top-10 fallback"]),
]

BOX_W, BOX_H, GAP = 1.66, 1.12, 0.22
Y0 = 1.10
X0 = 1.48

fig, ax = plt.subplots(figsize=(14.9, 3.8))
ax.set_xlim(0, 16.5)
ax.set_ylim(-0.74, 2.95)
ax.axis("off")


def box(x, y, w, h, fc=FILL, ec=INK, lw=0.9, style="round,pad=0.035,rounding_size=0.06"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style,
                                facecolor=fc, edgecolor=ec, linewidth=lw))


def arrow(p, q, color=INK, lw=1.0, style="-", mut=9):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=mut,
                                 linewidth=lw, color=color, linestyle=style,
                                 zorder=5, shrinkA=2, shrinkB=2))


# ---- pipeline stages -------------------------------------------------------
centers = []
for i, (title, lines) in enumerate(STAGES):
    x = X0 + i * (BOX_W + GAP)
    box(x, Y0, BOX_W, BOX_H)
    ax.text(x + BOX_W / 2, Y0 + BOX_H - 0.19, title, ha="center", va="center",
            fontsize=8.0, fontweight="bold")
    for j, line in enumerate(lines):
        ax.text(x + BOX_W / 2, Y0 + BOX_H - 0.44 - j * 0.195, line,
                ha="center", va="center", fontsize=6.7, color=MUTED)
    centers.append((x, x + BOX_W))

for i in range(len(STAGES) - 1):
    arrow((centers[i][1] + 0.012, Y0 + BOX_H / 2), (centers[i + 1][0] - 0.012, Y0 + BOX_H / 2))

# per-turn bracket
bx0, bx1 = X0 - 0.14, centers[-1][1] + 0.14
ax.plot([bx0, bx0, bx1, bx1], [Y0 + BOX_H + 0.13, Y0 + BOX_H + 0.24,
                               Y0 + BOX_H + 0.24, Y0 + BOX_H + 0.13],
        color=MUTED, linewidth=0.8)
ax.text((bx0 + bx1) / 2, Y0 + BOX_H + 0.40,
        "every turn  (deterministic · 100–200 ms · 0 tokens · no network)",
        ha="center", va="center", fontsize=8.0, color=MUTED, style="italic")

# ---- input / output --------------------------------------------------------
io_w, io_h = 1.04, 0.62
iy = Y0 + BOX_H / 2 - io_h / 2
box(0.18, iy, io_w, io_h, fc="white", style="round,pad=0.035,rounding_size=0.30")
ax.text(0.18 + io_w / 2, iy + io_h / 2, "customer\nmessage", ha="center", va="center", fontsize=7.6)
arrow((0.18 + io_w + 0.02, Y0 + BOX_H / 2), (X0 - 0.02, Y0 + BOX_H / 2))

ox = centers[-1][1] + 0.38
box(ox, iy, 1.34, io_h, fc=ACCENT_FILL, ec=ACCENT, style="round,pad=0.035,rounding_size=0.30")
ax.text(ox + 0.67, iy + io_h / 2, "response +\nrecommendations", ha="center", va="center",
        fontsize=7.0, color=ACCENT)
arrow((centers[-1][1] + 0.012, Y0 + BOX_H / 2), (ox - 0.02, Y0 + BOX_H / 2), color=ACCENT)

# ---- offline index (feeds stages 3, 4, 5) ----------------------------------
off_w, off_h = 5.75, 0.56
mid = (centers[2][0] + centers[4][1]) / 2
off_x, off_y = mid - off_w / 2, -0.08
box(off_x, off_y, off_w, off_h, fc="white", ec=MUTED, lw=0.8)
ax.text(off_x + off_w / 2, off_y + off_h / 2,
        "L0 · offline index  (50 k products: metadata, intent cards, SQLite FTS5, priors)",
        ha="center", va="center", fontsize=7.2, color=MUTED)
for target in (2, 3, 4):
    tx = X0 + target * (BOX_W + GAP) + BOX_W / 2
    arrow((tx, off_y + off_h + 0.02), (tx, Y0 - 0.02), color=MUTED, lw=0.8,
          style=(0, (3, 2)), mut=7)

# ---- feedback loop ---------------------------------------------------------
fy = -0.56
ax.plot([ox + 0.67, ox + 0.67], [iy - 0.02, fy], color=ACCENT, linewidth=0.9, linestyle=(0, (4, 2)))
ax.plot([ox + 0.67, 0.18 + io_w / 2], [fy, fy], color=ACCENT, linewidth=0.9, linestyle=(0, (4, 2)))
arrow((0.18 + io_w / 2, fy), (0.18 + io_w / 2, iy - 0.04), color=ACCENT, lw=0.9,
      style=(0, (4, 2)), mut=8)
ax.text(1.7, fy - 0.16,
        "continuing session  =  implicit rejection of the shown item",
        ha="left", va="center", fontsize=7.6, color=ACCENT, style="italic")

fig.savefig(OUT / "architecture.png", dpi=300, bbox_inches="tight", facecolor="white")
fig.savefig(OUT / "architecture.pdf", bbox_inches="tight", facecolor="white")
print("written:", OUT / "architecture.png")
