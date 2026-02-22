"""
Perceptual Hashing for Video Files — backed by K2A-Hash.

K2A-Hash replaces imagehash.phash() as the perceptual hash stored on-chain.
Algorithm: uniform 8×8 block grid + literal pixel diagonal extraction +
directional bit compression (L→R vs R→L) + complement verification +
temporal extension across sampled video frames.
"""
from .k2a_hash import compute_video_k2a_hash


def compute_video_phash(video_path: str) -> str:
    """
    Compute K2A-Hash for video evidence integrity.

    Samples 4 frames from the video and builds a 256-bit temporal hash
    where the diagonal traversal crosses both spatial blocks and time.

    Returns:
        0x-prefixed 64-char hex string (bytes32 compatible).
    """
    return compute_video_k2a_hash(video_path)
