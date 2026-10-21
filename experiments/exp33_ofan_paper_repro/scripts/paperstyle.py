"""Shared matplotlib style replicating the figures of arXiv 2610.07230 (Ofan). Import with: from paperstyle import *"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.labelsize": 6.5, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
                     "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2, "ytick.major.size": 2,
                     "axes.labelpad": 1.5, "savefig.dpi": 220, "grid.color": "#d9d9d9", "grid.linewidth": 0.5, "legend.fontsize": 8})
# name -> (label, fill colour, marker); colours sampled from the paper figures
LB = {"reps": ("REPS", "#6fb0b0", "v"), "ar": ("AR", "#8fb86c", "s"), "ofan": ("Ofan", "#b394e0", "D")}
EDGE = {"reps": "#3f8a8a", "ar": "#5f8f3f", "ofan": "#7d5cc4"}
def legend_row(fig, lbs, y=1.0, x=0.5):
    h = [Line2D([0], [0], color=EDGE[k], marker=LB[k][2], mfc=LB[k][1], mec=EDGE[k], ms=4.5, lw=1, label=LB[k][0]) for k in lbs]
    fig.legend(handles=h, loc="upper center", bbox_to_anchor=(x, y), ncol=len(h), frameon=False, handlelength=2.2, columnspacing=1.2, handletextpad=0.4)
def caption(ax, text, dy=-0.30):
    ax.text(0.5, dy, text, transform=ax.transAxes, ha="center", va="top", fontsize=8.5, fontweight="bold", family="DejaVu Serif")
