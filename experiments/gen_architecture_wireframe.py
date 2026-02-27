#!/usr/bin/env python3
"""Generate wireframe architecture diagram → docs/res/fig_architecture.png"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO_ROOT, 'docs', 'res', 'fig_architecture.png')

fig, ax = plt.subplots(figsize=(13, 8))
ax.set_xlim(0, 13)
ax.set_ylim(0, 8)
ax.axis('off')
fig.patch.set_facecolor('white')
ax.set_facecolor('white')

# ── helpers ───────────────────────────────────────────────────────────────────
def region(ax, x, y, w, h, label):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle='round,pad=0.1',
                          facecolor='#f4f4f4', edgecolor='#333',
                          linewidth=1.2, linestyle='--', zorder=1)
    ax.add_patch(rect)
    ax.text(x + 0.15, y + h - 0.22, label,
            fontsize=8, color='#333', fontstyle='italic', zorder=2)

def box(ax, x, y, w, h, title, sub=''):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle='round,pad=0.06',
                          facecolor='white', edgecolor='#222',
                          linewidth=1.5, zorder=3)
    ax.add_patch(rect)
    ty = y + h/2 + (0.15 if sub else 0)
    ax.text(x + w/2, ty, title,
            ha='center', va='center', fontsize=9.5,
            fontweight='bold', color='#111', zorder=4)
    if sub:
        ax.text(x + w/2, y + h/2 - 0.18, sub,
                ha='center', va='center', fontsize=7.5,
                color='#444', zorder=4)

def arrow(ax, x1, y1, x2, y2, label='', lw=1.4,
          rad=0.0, double=False):
    style = '<->' if double else '->'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color='#222',
                                lw=lw,
                                connectionstyle=f'arc3,rad={rad}'),
                zorder=5)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx, my + 0.13, label,
                ha='center', va='bottom', fontsize=7,
                color='#333', zorder=6,
                bbox=dict(boxstyle='round,pad=0.12',
                          fc='white', ec='none', alpha=0.9))

# ── regions ───────────────────────────────────────────────────────────────────
region(ax, 0.4,  5.5, 5.8, 2.0, 'Edge / Capture Layer')
region(ax, 0.4,  2.8, 9.2, 2.4, 'Application Layer')
region(ax, 5.8,  0.3, 6.0, 2.2, 'Data & Trust Layer')

# ── boxes ─────────────────────────────────────────────────────────────────────
BW, BH = 2.5, 1.0

# Camera
box(ax, 0.7,  5.8, BW, BH, 'CCTV / Camera', 'Simulator')

# AI Service
box(ax, 3.5,  5.8, BW+0.5, BH, 'AI Service',
    'K2A-Hash · SHA-256 · Crime Det.')

# Frontend
box(ax, 0.7,  3.1, BW, BH, 'Frontend',
    'Dashboard · Verifier')

# Backend
box(ax, 3.8,  3.1, BW+0.3, BH, 'Backend API',
    '/record · /verify · /logs')

# SQLite
box(ax, 7.5,  3.1, BW, BH, 'SQLite Cache',
    'evidence_log')

# Blockchain
box(ax, 6.2,  0.55, BW+0.8, BH, 'Blockchain Anchor',
    'EvidenceLog.sol  (bytes32 × 2)')

# ── arrows ────────────────────────────────────────────────────────────────────
# Camera → AI Service
arrow(ax, 0.7+BW, 6.3,  3.5, 6.3,  'video clip')

# AI Service → Backend (diagonal)
arrow(ax, 3.5+BW+0.5, 6.0,  3.8+(BW+0.3), 4.1,
      'videoHash + k2aHash', rad=-0.3)

# Frontend ↔ Backend
arrow(ax, 0.7+BW,    3.5,  3.8,        3.55, 'POST /verify',  rad=0.12)
arrow(ax, 3.8,       3.25, 0.7+BW,     3.25, 'verdict + Hamming', rad=0.12)

# Backend → SQLite
arrow(ax, 3.8+BW+0.3, 3.6,  7.5, 3.6,  'INSERT / UPDATE')

# Backend → Blockchain
bx = 3.8 + (BW+0.3)/2
arrow(ax, bx, 3.1,  6.2+(BW+0.8)/2, 0.55+BH,  'logEvidence()')

# SQLite ↔ Blockchain (dashed)
ax.annotate('', xy=(8.6, 0.55+BH), xytext=(8.6, 3.1),
            arrowprops=dict(arrowstyle='<->', color='#555',
                            lw=1.2, linestyle='dashed'), zorder=4)
ax.text(8.78, 1.9, 'Level 1\nvs\nLevel 2',
        ha='left', va='center', fontsize=6.8, color='#444',
        bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.9))

# ── legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(facecolor='white', edgecolor='#222', label='Camera / Capture'),
    mpatches.Patch(facecolor='white', edgecolor='#222', label='AI Service'),
    mpatches.Patch(facecolor='white', edgecolor='#222', label='Frontend'),
    mpatches.Patch(facecolor='white', edgecolor='#222', label='Backend API'),
    mpatches.Patch(facecolor='white', edgecolor='#222', label='SQLite Cache'),
    mpatches.Patch(facecolor='white', edgecolor='#222', label='Blockchain Anchor'),
]
ax.legend(handles=legend_items, loc='lower left',
          fontsize=7.5, framealpha=0.9,
          ncol=3, columnspacing=0.8, handlelength=1.0)

ax.set_title(
    'Blockchain-Based CCTV Evidence Verification — System Architecture',
    fontsize=11, fontweight='bold', pad=10, color='#111')

plt.tight_layout()
plt.savefig(OUT, dpi=200, bbox_inches='tight', facecolor='white')
plt.close()
print(f'✓ Saved: {OUT}')
