#!/usr/bin/env python3
"""
Figure Generation Script for K2A Experiments
Reads experiments/results.csv and saves 4 publication-quality PNG figures
to docs/res/.

Usage:
  /home/moksh/Mini_Project/blockchain-cctv/ai-service/.venv/bin/python \
    experiments/generate_figures.py
"""

import os, csv, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_CSV = os.path.join(REPO_ROOT, 'experiments', 'results.csv')
OUT_DIR = os.path.join(REPO_ROOT, 'docs', 'res')
os.makedirs(OUT_DIR, exist_ok=True)

# Publication style
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 150,
    'savefig.dpi': 200,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05,
})


# ── load CSV ──────────────────────────────────────────────────────────────────
def load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def safe_int(v):
    try:
        return int(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def safe_float(v):
    try:
        return float(v) if v not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


# ── Figure 1: Hamming distribution histogram ─────────────────────────────────
def fig1_hamming_dist(rows):
    genuine = [safe_int(r['hamming_reencode']) for r in rows]
    genuine = [x for x in genuine if x is not None]

    tampered = []
    for r in rows:
        fd = safe_int(r['hamming_frame_delete'])
        ov = safe_int(r['hamming_overlay'])
        if fd is not None:
            tampered.append(fd)
        if ov is not None:
            tampered.append(ov)

    fig, ax = plt.subplots(figsize=(6, 4))

    bins = range(0, max(max(genuine, default=0), max(tampered, default=0)) + 3)

    ax.hist(genuine, bins=bins, alpha=0.7, color='steelblue', label='Genuine (re-encode)',
            edgecolor='white', linewidth=0.5)
    ax.hist(tampered, bins=bins, alpha=0.7, color='firebrick',
            label='Tampered (frame-del + overlay)', edgecolor='white', linewidth=0.5)

    ax.axvline(x=8, color='black', linestyle='--', linewidth=1.5,
               label='Threshold = 8 bits')

    ax.set_xlabel('Hamming Distance (bits)')
    ax.set_ylabel('Count')
    ax.set_title('K2A Hamming Distance Distribution:\nGenuine vs. Tampered Clips')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    out = os.path.join(OUT_DIR, 'fig_hamming_dist.png')
    fig.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")


# ── Figure 2: Grouped bar — K2A vs pHash vs dHash ────────────────────────────
def fig2_hash_comparison(rows):
    tamper_types = ['reencode', 'frame_delete', 'brightness', 'overlay']
    labels = ['Re-encode', 'Frame Delete', 'Brightness', 'Text Overlay']

    k2a_means, phash_means, dhash_means = [], [], []
    for t in tamper_types:
        k2a_vals = [safe_int(r[f'hamming_{t}']) for r in rows]
        k2a_vals = [x for x in k2a_vals if x is not None]
        k2a_means.append(np.mean(k2a_vals) if k2a_vals else 0)

        if t == 'reencode':
            ph = [safe_int(r['phash_hamming_reencode']) for r in rows]
            ph = [x for x in ph if x is not None]
            phash_means.append(np.mean(ph) if ph else 0)
            dh = [safe_int(r['dhash_hamming_reencode']) for r in rows]
            dh = [x for x in dh if x is not None]
            dhash_means.append(np.mean(dh) if dh else 0)
        else:
            # pHash/dHash not computed for non-reencode tampers; show N/A as 0
            phash_means.append(0)
            dhash_means.append(0)

    x = np.arange(len(labels))
    width = 0.26

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars1 = ax.bar(x - width, k2a_means, width, label='K2A-Hash', color='steelblue',
                   edgecolor='white')
    bars2 = ax.bar(x, phash_means, width, label='pHash (re-encode only)',
                   color='darkorange', edgecolor='white')
    bars3 = ax.bar(x + width, dhash_means, width, label='dHash (re-encode only)',
                   color='seagreen', edgecolor='white')

    ax.axhline(y=8, color='black', linestyle='--', linewidth=1.2, label='Threshold = 8')

    ax.set_xlabel('Tamper Type')
    ax.set_ylabel('Mean Hamming Distance (bits)')
    ax.set_title('Mean Hamming Distance by Tamper Type:\nK2A vs. pHash vs. dHash')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # Value labels on K2A bars
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax.annotate(f'{h:.1f}', xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 2), textcoords='offset points',
                        ha='center', va='bottom', fontsize=8)

    out = os.path.join(OUT_DIR, 'fig_hash_comparison.png')
    fig.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")


# ── Figure 3: Detection heatmap ───────────────────────────────────────────────
def fig3_detection_matrix(rows):
    THRESHOLD = 8

    tamper_types = ['reencode', 'frame_delete', 'brightness', 'overlay']
    labels = ['Re-encode\n(CRF 28)', 'Frame\nDelete', 'Brightness\n+0.3', 'Text\nOverlay']

    # SHA-256: always detects any tamper (byte-level change)
    sha256_det = [1, 1, 1, 1]  # all detected (re-encode changes bytes)

    # K2A: detected if mean Hamming > threshold
    k2a_det = []
    for t in tamper_types:
        vals = [safe_int(r[f'hamming_{t}']) for r in rows]
        vals = [x for x in vals if x is not None]
        if vals:
            mean_d = np.mean(vals)
            k2a_det.append(1 if mean_d > THRESHOLD else 0)
        else:
            k2a_det.append(0)

    # Matrix: rows=tampers, cols=[SHA-256 detected, K2A detected]
    matrix = np.array([[s, k] for s, k in zip(sha256_det, k2a_det)], dtype=float)

    fig, ax = plt.subplots(figsize=(5, 4))

    cmap = ListedColormap(['#d73027', '#1a9850'])
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect='auto')

    ax.set_xticks([0, 1])
    ax.set_xticklabels(['SHA-256\nDetected', 'K2A-Hash\nDetected'], fontsize=10)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=10)

    for i in range(len(tamper_types)):
        for j in range(2):
            val = matrix[i, j]
            text = 'YES' if val == 1 else 'NO'
            color = 'white'
            ax.text(j, i, text, ha='center', va='center',
                    fontsize=11, fontweight='bold', color=color)

    green_patch = mpatches.Patch(color='#1a9850', label='Detected')
    red_patch = mpatches.Patch(color='#d73027', label='Not detected')
    ax.legend(handles=[green_patch, red_patch], loc='upper right',
              bbox_to_anchor=(1.45, 1.02))

    ax.set_title('Dual-Hash Detection Matrix\n(SHA-256 vs. K2A-Hash)', fontsize=12)
    ax.set_xlabel('Hash Method')
    ax.set_ylabel('Tamper Type')

    out = os.path.join(OUT_DIR, 'fig_detection_matrix.png')
    fig.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")


# ── Figure 4: Compute time scatter ───────────────────────────────────────────
def fig4_compute_time(rows):
    sizes = [safe_float(r['file_size_mb']) for r in rows]
    times = [safe_float(r['k2a_time_ms']) for r in rows]
    pairs = [(s, t) for s, t in zip(sizes, times) if s is not None and t is not None]
    if not pairs:
        print("  WARNING: No data for fig4")
        return
    xs, ys = zip(*pairs)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(xs, ys, color='steelblue', alpha=0.7, s=40, edgecolors='white',
               linewidths=0.5)

    # Linear trend line
    if len(xs) > 2:
        z = np.polyfit(xs, ys, 1)
        p = np.poly1d(z)
        xline = np.linspace(min(xs), max(xs), 100)
        ax.plot(xline, p(xline), 'r--', linewidth=1.5, label=f'Trend (slope={z[0]:.1f} ms/MB)')
        ax.legend()

    ax.axhline(y=500, color='orange', linestyle=':', linewidth=1.2,
               label='500 ms target')

    ax.set_xlabel('File Size (MB)')
    ax.set_ylabel('K2A Compute Time (ms)')
    ax.set_title('K2A-Hash Compute Time vs. File Size')
    ax.grid(alpha=0.3)

    out = os.path.join(OUT_DIR, 'fig_compute_time.png')
    fig.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(RESULTS_CSV):
        print(f"ERROR: {RESULTS_CSV} not found. Run run_experiments.py first.")
        sys.exit(1)

    rows = load_csv(RESULTS_CSV)
    print(f"Loaded {len(rows)} rows from {RESULTS_CSV}")

    print("\nGenerating figures...")
    fig1_hamming_dist(rows)
    fig2_hash_comparison(rows)
    fig3_detection_matrix(rows)
    fig4_compute_time(rows)

    print(f"\n✓ All 4 figures saved to {OUT_DIR}")

    # Print summary stats for paper
    import statistics
    re_dists = [safe_int(r['hamming_reencode']) for r in rows]
    re_dists = [x for x in re_dists if x is not None]
    fd_dists = [safe_int(r['hamming_frame_delete']) for r in rows]
    fd_dists = [x for x in fd_dists if x is not None]
    br_dists = [safe_int(r['hamming_brightness']) for r in rows]
    br_dists = [x for x in br_dists if x is not None]
    ov_dists = [safe_int(r['hamming_overlay']) for r in rows]
    ov_dists = [x for x in ov_dists if x is not None]
    times = [safe_float(r['k2a_time_ms']) for r in rows]
    times = [x for x in times if x is not None]

    print("\n── Stats for paper ──────────────────────────────────────────────")
    if re_dists:
        print(f"  Re-encode   : mean={statistics.mean(re_dists):.2f}  "
              f"stdev={statistics.stdev(re_dists) if len(re_dists)>1 else 0:.2f}  "
              f"max={max(re_dists)}")
    if fd_dists:
        print(f"  Frame-del   : mean={statistics.mean(fd_dists):.2f}  "
              f"stdev={statistics.stdev(fd_dists) if len(fd_dists)>1 else 0:.2f}  "
              f"min={min(fd_dists)}")
    if br_dists:
        print(f"  Brightness  : mean={statistics.mean(br_dists):.2f}  "
              f"stdev={statistics.stdev(br_dists) if len(br_dists)>1 else 0:.2f}")
    if ov_dists:
        print(f"  Overlay     : mean={statistics.mean(ov_dists):.2f}  "
              f"stdev={statistics.stdev(ov_dists) if len(ov_dists)>1 else 0:.2f}  "
              f"min={min(ov_dists)}")
    if times:
        print(f"  K2A time    : mean={statistics.mean(times):.1f} ms  "
              f"min={min(times):.1f}  max={max(times):.1f}")


if __name__ == '__main__':
    main()
