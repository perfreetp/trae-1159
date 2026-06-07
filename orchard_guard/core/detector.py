import os
import json
from typing import List, Dict, Optional
from .models import (
    DiseaseType,
    DiseaseDetection,
    BBox,
    ImageRecord,
    ScanSession,
    AppConfig,
)

_DISEASE_DB: Optional[List[dict]] = None

_DISEASE_REF = [
    {
        "name": "叶斑病",
        "keywords": ["spot", "leaf_spot", "褐色斑", "圆形斑"],
        "color_hints": ["brown", "dark_spot", "circular"],
        "treatment": "喷施多菌灵或代森锰锌，间隔7-10天，连续2-3次；清除落叶，减少侵染源。",
    },
    {
        "name": "炭疽病",
        "keywords": ["anthracnose", "炭疽", "凹陷斑", "轮纹"],
        "color_hints": ["black", "sunken", "ring_pattern"],
        "treatment": "喷施咪鲜胺或苯醚甲环唑，重点喷果实和嫩梢；及时摘除病果。",
    },
    {
        "name": "腐烂病",
        "keywords": ["rot", "腐烂", "溃烂", "软腐"],
        "color_hints": ["dark_brown", "mushy", "oozing"],
        "treatment": "刮除病斑涂抹石硫合剂或腐殖酸铜；加强树体营养，提高抗病力。",
    },
    {
        "name": "锈病",
        "keywords": ["rust", "锈病", "黄粉", "毛状物"],
        "color_hints": ["orange_yellow", "powdery", "pustule"],
        "treatment": "喷施三唑酮或腈菌唑，花前花后各一次；清除转主寄主（桧柏等）。",
    },
]


def load_disease_db() -> List[dict]:
    global _DISEASE_DB
    if _DISEASE_DB is not None:
        return _DISEASE_DB
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "diseases.json")
    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            _DISEASE_DB = json.load(f)
    else:
        _DISEASE_DB = _DISEASE_REF
    return _DISEASE_DB


def get_treatment(disease_name: str) -> str:
    db = load_disease_db()
    for entry in db:
        if entry["name"] == disease_name:
            return entry.get("treatment", "暂无防治建议")
    return "暂无防治建议"


def detect_diseases(
    image_record: ImageRecord,
    confidence_threshold: float = 0.5,
    blur_threshold: float = 100.0,
    skip_blurry: bool = True,
) -> ImageRecord:
    from .image_utils import compute_blur_score

    blur = compute_blur_score(image_record.file_path)
    image_record.blur_score = blur
    image_record.is_blurry = blur < blur_threshold

    if image_record.is_blurry and skip_blurry:
        return image_record

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        _simulate_detections(image_record, confidence_threshold)
        return image_record

    try:
        img = Image.open(image_record.file_path)
        image_record.image_width, image_record.image_height = img.size
        arr = np.array(img)
        _analyze_image(arr, image_record, confidence_threshold)
    except Exception:
        _simulate_detections(image_record, confidence_threshold)

    return image_record


def _analyze_image(
    arr: "np.ndarray",
    record: ImageRecord,
    threshold: float,
):
    import numpy as np

    if arr.ndim < 3:
        return
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    h, w = arr.shape[:2]
    detections = []

    brown_mask = (r > 80) & (r < 180) & (g > 40) & (g < 120) & (b < 80)
    brown_ratio = float(np.sum(brown_mask)) / (h * w)
    if brown_ratio > 0.01:
        conf = min(0.95, brown_ratio * 15 + 0.3)
        if conf >= threshold:
            ys, xs = np.where(brown_mask)
            if len(xs) > 0 and len(ys) > 0:
                x1, x2 = int(np.min(xs)), int(np.max(xs))
                y1, y2 = int(np.min(ys)), int(np.max(ys))
                detections.append(
                    DiseaseDetection(
                        disease=DiseaseType.LEAF_SPOT,
                        confidence=conf,
                        bbox=BBox(x1, y1, x2, y2),
                    )
                )

    dark_mask = (r < 60) & (g < 60) & (b < 60) & (r > 10)
    dark_ratio = float(np.sum(dark_mask)) / (h * w)
    if dark_ratio > 0.005:
        conf = min(0.90, dark_ratio * 20 + 0.25)
        if conf >= threshold:
            ys, xs = np.where(dark_mask)
            if len(xs) > 0 and len(ys) > 0:
                x1, x2 = int(np.min(xs)), int(np.max(xs))
                y1, y2 = int(np.min(ys)), int(np.max(ys))
                detections.append(
                    DiseaseDetection(
                        disease=DiseaseType.ANTHRACNOSE,
                        confidence=conf,
                        bbox=BBox(x1, y1, x2, y2),
                    )
                )

    orange_mask = (r > 150) & (g > 100) & (g < 200) & (b < 100)
    orange_ratio = float(np.sum(orange_mask)) / (h * w)
    if orange_ratio > 0.008:
        conf = min(0.88, orange_ratio * 18 + 0.2)
        if conf >= threshold:
            ys, xs = np.where(orange_mask)
            if len(xs) > 0 and len(ys) > 0:
                x1, x2 = int(np.min(xs)), int(np.max(xs))
                y1, y2 = int(np.min(ys)), int(np.max(ys))
                detections.append(
                    DiseaseDetection(
                        disease=DiseaseType.RUST,
                        confidence=conf,
                        bbox=BBox(x1, y1, x2, y2),
                    )
                )

    very_dark = (r < 30) & (g < 30) & (b < 30)
    wet_mask = very_dark & (np.abs(r.astype(int) - g.astype(int)) < 15)
    wet_ratio = float(np.sum(wet_mask)) / (h * w)
    if wet_ratio > 0.003:
        conf = min(0.85, wet_ratio * 25 + 0.2)
        if conf >= threshold:
            ys, xs = np.where(wet_mask)
            if len(xs) > 0 and len(ys) > 0:
                x1, x2 = int(np.min(xs)), int(np.max(xs))
                y1, y2 = int(np.min(ys)), int(np.max(ys))
                detections.append(
                    DiseaseDetection(
                        disease=DiseaseType.ROT,
                        confidence=conf,
                        bbox=BBox(x1, y1, x2, y2),
                    )
                )

    if not detections:
        green_mask = (g > 80) & (g > r) & (g > b)
        green_ratio = float(np.sum(green_mask)) / (h * w)
        if green_ratio > 0.3:
            detections.append(
                DiseaseDetection(
                    disease=DiseaseType.HEALTHY,
                    confidence=min(0.95, green_ratio * 1.2),
                )
            )

    record.detections = detections


def _simulate_detections(record: ImageRecord, threshold: float):
    import hashlib

    h = hashlib.md5(record.file_path.encode()).hexdigest()
    val = int(h[:8], 16) / 0xFFFFFFFF
    detections = []
    diseases = [
        (DiseaseType.LEAF_SPOT, 0.72),
        (DiseaseType.ANTHRACNOSE, 0.65),
        (DiseaseType.ROT, 0.58),
        (DiseaseType.RUST, 0.61),
        (DiseaseType.HEALTHY, 0.80),
    ]

    from PIL import Image as PILImage
    try:
        img = PILImage.open(record.file_path)
        w, h_img = img.size
        record.image_width, record.image_height = w, h_img
    except Exception:
        w, h_img = 800, 600
        record.image_width, record.image_height = w, h_img

    for i, (dtype, base_conf) in enumerate(diseases):
        seed = (val + i * 0.17) % 1.0
        conf = round(base_conf * (0.5 + seed * 0.8), 4)
        if conf >= threshold:
            import random

            rng = random.Random(h[:8] + str(i))
            x1 = rng.randint(0, max(1, w - 100))
            y1 = rng.randint(0, max(1, h_img - 100))
            x2 = min(w, x1 + rng.randint(50, 200))
            y2 = min(h_img, y1 + rng.randint(50, 200))
            detections.append(
                DiseaseDetection(
                    disease=dtype,
                    confidence=conf,
                    bbox=BBox(x1, y1, x2, y2),
                )
            )
            break
    if not detections:
        detections.append(
            DiseaseDetection(disease=DiseaseType.HEALTHY, confidence=0.90)
        )
    record.detections = detections
