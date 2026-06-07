import os
from typing import Tuple, Optional
from pathlib import Path


def compute_blur_score(image_path: str) -> float:
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return 0.0

    try:
        img = Image.open(image_path).convert("L")
        arr = np.array(img, dtype=np.float64)
        if arr.size == 0:
            return 0.0
        laplacian_kernel = np.array(
            [[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64
        )
        from scipy.ndimage import convolve

        laplacian = convolve(arr, laplacian_kernel)
        return float(np.var(laplacian))
    except Exception:
        return 0.0


def is_image_file(path: str) -> bool:
    ext = Path(path).suffix.lower()
    return ext in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def collect_images(directory: str) -> list:
    images = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return images
    for root, _dirs, files in os.walk(directory):
        for f in sorted(files):
            full = os.path.join(root, f)
            if is_image_file(full):
                images.append(full)
    return images


def parse_path_info(file_path: str) -> Tuple[str, str]:
    parts = Path(file_path).parts
    variety = ""
    plot_id = ""
    for part in parts:
        if part.startswith("V_") or part.startswith("品种_"):
            variety = part.split("_", 1)[-1] if "_" in part else part[2:]
        if part.startswith("P_") or part.startswith("地块_"):
            plot_id = part.split("_", 1)[-1] if "_" in part else part[2:]
    return variety, plot_id


def extract_date_from_path(file_path: str) -> Optional[str]:
    import re

    path_str = str(file_path)
    m = re.search(r"(\d{4})[/-](\d{2})[/-](\d{2})", path_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{8})", path_str)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return None
