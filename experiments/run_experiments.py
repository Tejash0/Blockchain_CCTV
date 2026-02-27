#!/usr/bin/env python3
"""
K2A Tamper-Detection Experiment Script
Samples 10 videos per category, computes K2A + pHash + dHash + SHA-256,
creates 4 tampered versions, records Hamming distances to results.csv.

Usage:
  /home/moksh/Mini_Project/blockchain-cctv/ai-service/.venv/bin/python \
    experiments/run_experiments.py
"""

import sys, os, csv, time, hashlib, shutil, subprocess, tempfile
import cv2
import numpy as np
import imagehash
from PIL import Image

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'ai-service'))

from app.utils.k2a_hash import compute_video_k2a_hash, k2a_hamming_distance

# ── constants ─────────────────────────────────────────────────────────────────
FFMPEG = '/usr/sbin/ffmpeg'
TEST_VIDEOS = os.path.join(REPO_ROOT, 'test_videos')
RESULTS_CSV = os.path.join(REPO_ROOT, 'experiments', 'results.csv')
SAMPLES_PER_CATEGORY = 10
TAMPER_TMP = '/tmp/tamper_tmp'

CATEGORIES = {
    'Normal':     os.path.join(TEST_VIDEOS, 'Normal_Videos_for_Event_Recognition'),
    'Robbery':    os.path.join(TEST_VIDEOS, 'Robbery'),
    'RoadAccidents': os.path.join(TEST_VIDEOS, 'RoadAccidents'),
    'Shoplifting':os.path.join(TEST_VIDEOS, 'Anomaly-Videos-Part-4', 'Shoplifting'),
    'Stealing':   os.path.join(TEST_VIDEOS, 'Anomaly-Videos-Part-4', 'Stealing'),
    'Vandalism':  os.path.join(TEST_VIDEOS, 'Anomaly-Videos-Part-4', 'Vandalism'),
}

CSV_FIELDS = [
    'category', 'filename', 'file_size_mb', 'k2a_time_ms', 'sha256_original',
    'k2a_original',
    'hamming_reencode', 'hamming_frame_delete', 'hamming_brightness', 'hamming_overlay',
    'phash_hamming_reencode', 'dhash_hamming_reencode',
]


# ── helper: SHA-256 ───────────────────────────────────────────────────────────
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return '0x' + h.hexdigest()


# ── helper: middle-frame pHash / dHash ────────────────────────────────────────
def phash_middle(path: str) -> imagehash.ImageHash | None:
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 1:
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return imagehash.phash(pil)


def dhash_middle(path: str) -> imagehash.ImageHash | None:
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 1:
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return imagehash.dhash(pil)


# ── tamper factories ──────────────────────────────────────────────────────────
def tamper_reencode(src: str, dst: str) -> bool:
    """Re-encode with CRF 28 (lossy, same content)."""
    r = subprocess.run(
        [FFMPEG, '-y', '-i', src, '-c:v', 'libx264', '-crf', '28',
         '-preset', 'fast', '-an', dst],
        capture_output=True, timeout=60
    )
    return r.returncode == 0 and os.path.exists(dst)


def tamper_frame_delete(src: str, dst: str) -> bool:
    """Delete frame at ~40% by writing all other frames with cv2."""
    cap = cv2.VideoCapture(src)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    skip = int(total * 0.40)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(dst, fourcc, fps, (w, h))
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx != skip:
            out.write(frame)
        idx += 1
    cap.release()
    out.release()
    return os.path.exists(dst) and os.path.getsize(dst) > 0


def tamper_brightness(src: str, dst: str) -> bool:
    """Increase brightness with ffmpeg eq filter."""
    r = subprocess.run(
        [FFMPEG, '-y', '-i', src,
         '-vf', 'eq=brightness=0.3',
         '-c:v', 'libx264', '-crf', '23', '-preset', 'fast', '-an', dst],
        capture_output=True, timeout=60
    )
    return r.returncode == 0 and os.path.exists(dst)


def tamper_overlay_text(src: str, dst: str) -> bool:
    """Draw 'TAMPERED' text overlay."""
    r = subprocess.run(
        [FFMPEG, '-y', '-i', src,
         '-vf', "drawtext=text='TAMPERED':fontcolor=red:fontsize=24:x=10:y=10",
         '-c:v', 'libx264', '-crf', '23', '-preset', 'fast', '-an', dst],
        capture_output=True, timeout=60
    )
    return r.returncode == 0 and os.path.exists(dst)


TAMPERS = [
    ('reencode',      tamper_reencode),
    ('frame_delete',  tamper_frame_delete),
    ('brightness',    tamper_brightness),
    ('overlay',       tamper_overlay_text),
]


# ── main ──────────────────────────────────────────────────────────────────────
def process_video(category: str, path: str) -> dict | None:
    filename = os.path.basename(path)
    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  [{category}] {filename} ({file_size_mb:.1f} MB)", end='', flush=True)

    # K2A hash + timing
    t0 = time.perf_counter()
    k2a_orig = compute_video_k2a_hash(path)
    k2a_time_ms = (time.perf_counter() - t0) * 1000

    sha256_orig = sha256_file(path)

    # pHash / dHash on middle frame (baseline comparison)
    ph_orig = phash_middle(path)
    dh_orig = dhash_middle(path)

    row = {
        'category': category,
        'filename': filename,
        'file_size_mb': round(file_size_mb, 3),
        'k2a_time_ms': round(k2a_time_ms, 1),
        'sha256_original': sha256_orig,
        'k2a_original': k2a_orig,
        'hamming_reencode': None,
        'hamming_frame_delete': None,
        'hamming_brightness': None,
        'hamming_overlay': None,
        'phash_hamming_reencode': None,
        'dhash_hamming_reencode': None,
    }

    # Tampered versions
    for tamper_name, tamper_fn in TAMPERS:
        dst = os.path.join(TAMPER_TMP, f"{os.path.splitext(filename)[0]}_{tamper_name}.mp4")
        try:
            ok = tamper_fn(path, dst)
            if ok:
                k2a_tampered = compute_video_k2a_hash(dst)
                hdist = int(k2a_hamming_distance(k2a_orig, k2a_tampered))
                row[f'hamming_{tamper_name}'] = hdist

                if tamper_name == 'reencode':
                    ph_t = phash_middle(dst)
                    dh_t = dhash_middle(dst)
                    if ph_orig and ph_t:
                        row['phash_hamming_reencode'] = int(ph_orig - ph_t)
                    if dh_orig and dh_t:
                        row['dhash_hamming_reencode'] = int(dh_orig - dh_t)
                # cleanup
                try:
                    os.remove(dst)
                except Exception:
                    pass
            else:
                print(f" [TAMPER FAIL: {tamper_name}]", end='', flush=True)
        except Exception as e:
            print(f" [ERR {tamper_name}: {e}]", end='', flush=True)

    print(f" ✓ K2A={k2a_time_ms:.0f}ms "
          f"re={row['hamming_reencode']} fd={row['hamming_frame_delete']} "
          f"br={row['hamming_brightness']} ov={row['hamming_overlay']}")
    return row


def main():
    os.makedirs(TAMPER_TMP, exist_ok=True)

    rows = []
    for category, folder in CATEGORIES.items():
        if not os.path.isdir(folder):
            print(f"WARNING: {folder} not found, skipping")
            continue
        videos = sorted([
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov'))
        ])
        sample = videos[:SAMPLES_PER_CATEGORY]
        print(f"\n=== {category}: {len(sample)} videos ===")
        for v in sample:
            row = process_video(category, v)
            if row:
                rows.append(row)

    # Write CSV
    with open(RESULTS_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✓ Results written to {RESULTS_CSV} ({len(rows)} rows)")

    # Summary stats
    import statistics
    re_dists = [r['hamming_reencode'] for r in rows if r['hamming_reencode'] is not None]
    fd_dists = [r['hamming_frame_delete'] for r in rows if r['hamming_frame_delete'] is not None]
    br_dists = [r['hamming_brightness'] for r in rows if r['hamming_brightness'] is not None]
    ov_dists = [r['hamming_overlay'] for r in rows if r['hamming_overlay'] is not None]
    times = [r['k2a_time_ms'] for r in rows]

    print("\n── Summary ──────────────────────────────────────────────────────")
    if re_dists:
        print(f"  Re-encode   Hamming: mean={statistics.mean(re_dists):.2f}  "
              f"min={min(re_dists)}  max={max(re_dists)}")
    if fd_dists:
        print(f"  Frame-del   Hamming: mean={statistics.mean(fd_dists):.2f}  "
              f"min={min(fd_dists)}  max={max(fd_dists)}")
    if br_dists:
        print(f"  Brightness  Hamming: mean={statistics.mean(br_dists):.2f}  "
              f"min={min(br_dists)}  max={max(br_dists)}")
    if ov_dists:
        print(f"  Overlay     Hamming: mean={statistics.mean(ov_dists):.2f}  "
              f"min={min(ov_dists)}  max={max(ov_dists)}")
    if times:
        print(f"  K2A time:   mean={statistics.mean(times):.1f} ms  "
              f"min={min(times):.1f}  max={max(times):.1f}")

    # Cleanup temp dir
    shutil.rmtree(TAMPER_TMP, ignore_errors=True)


if __name__ == '__main__':
    main()
