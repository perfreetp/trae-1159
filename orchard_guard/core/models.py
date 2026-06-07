from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import List, Optional, Dict, Tuple
from enum import Enum
import json, uuid, copy


class DiseaseType(Enum):
    LEAF_SPOT = "叶斑病"
    ANTHRACNOSE = "炭疽病"
    ROT = "腐烂病"
    RUST = "锈病"
    HEALTHY = "健康"
    UNKNOWN = "未知"


DISEASE_NAMES_CN = {d.value: d for d in DiseaseType}


@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def to_dict(self) -> dict:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @staticmethod
    def from_dict(d: dict) -> "BBox":
        return BBox(d["x1"], d["y1"], d["x2"], d["y2"])


@dataclass
class DiseaseDetection:
    disease: DiseaseType
    confidence: float
    bbox: Optional[BBox] = None
    corrected: bool = False
    original_disease: Optional[DiseaseType] = None

    def to_dict(self) -> dict:
        d = {
            "disease": self.disease.value,
            "confidence": round(self.confidence, 4),
            "corrected": self.corrected,
        }
        if self.bbox:
            d["bbox"] = self.bbox.to_dict()
        if self.original_disease:
            d["original_disease"] = self.original_disease.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "DiseaseDetection":
        det = DiseaseDetection(
            disease=DISEASE_NAMES_CN.get(d["disease"], DiseaseType.UNKNOWN),
            confidence=d["confidence"],
            corrected=d.get("corrected", False),
        )
        if "bbox" in d and d["bbox"]:
            det.bbox = BBox.from_dict(d["bbox"])
        if "original_disease" in d and d["original_disease"]:
            det.original_disease = DISEASE_NAMES_CN.get(
                d["original_disease"], DiseaseType.UNKNOWN
            )
        return det


@dataclass
class ImageRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    file_path: str = ""
    file_name: str = ""
    variety: str = ""
    plot_id: str = ""
    scan_date: str = field(default_factory=lambda: date.today().isoformat())
    image_width: int = 0
    image_height: int = 0
    is_blurry: bool = False
    blur_score: float = 0.0
    detections: List[DiseaseDetection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "variety": self.variety,
            "plot_id": self.plot_id,
            "scan_date": self.scan_date,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "is_blurry": self.is_blurry,
            "blur_score": round(self.blur_score, 4),
            "detections": [det.to_dict() for det in self.detections],
        }

    @staticmethod
    def from_dict(d: dict) -> "ImageRecord":
        rec = ImageRecord(
            id=d.get("id", uuid.uuid4().hex[:12]),
            file_path=d.get("file_path", ""),
            file_name=d.get("file_name", ""),
            variety=d.get("variety", ""),
            plot_id=d.get("plot_id", ""),
            scan_date=d.get("scan_date", date.today().isoformat()),
            image_width=d.get("image_width", 0),
            image_height=d.get("image_height", 0),
            is_blurry=d.get("is_blurry", False),
            blur_score=d.get("blur_score", 0.0),
        )
        rec.detections = [
            DiseaseDetection.from_dict(dd) for dd in d.get("detections", [])
        ]
        return rec

    def primary_disease(self) -> Optional[DiseaseType]:
        if not self.detections:
            return None
        best = max(self.detections, key=lambda d: d.confidence)
        return best.disease

    def max_confidence(self) -> float:
        if not self.detections:
            return 0.0
        return max(d.confidence for d in self.detections)

    def image_area(self) -> int:
        return self.image_width * self.image_height

    def has_disease(self) -> bool:
        return any(
            det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN)
            for det in self.detections
        )

    def is_healthy(self) -> bool:
        if not self.detections:
            return False
        return all(
            det.disease == DiseaseType.HEALTHY
            for det in self.detections
        )

    def total_lesion_area(self) -> int:
        area = 0
        for det in self.detections:
            if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN) and det.bbox:
                area += det.bbox.area()
        return area


@dataclass
class ScanSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    source_dir: str = ""
    variety: str = ""
    plot_id: str = ""
    scan_date: str = field(default_factory=lambda: date.today().isoformat())
    images: List[ImageRecord] = field(default_factory=list)
    total_images: int = 0
    blurry_count: int = 0
    disease_count: int = 0
    healthy_count: int = 0

    def recalculate_counts(self):
        self.total_images = len(self.images)
        self.blurry_count = sum(1 for img in self.images if img.is_blurry)
        self.disease_count = sum(1 for img in self.images if img.has_disease())
        self.healthy_count = sum(1 for img in self.images if img.is_healthy())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "source_dir": self.source_dir,
            "variety": self.variety,
            "plot_id": self.plot_id,
            "scan_date": self.scan_date,
            "images": [img.to_dict() for img in self.images],
            "total_images": self.total_images,
            "blurry_count": self.blurry_count,
            "disease_count": self.disease_count,
            "healthy_count": self.healthy_count,
        }

    @staticmethod
    def from_dict(d: dict) -> "ScanSession":
        s = ScanSession(
            id=d.get("id", uuid.uuid4().hex[:8]),
            created_at=d.get("created_at", ""),
            source_dir=d.get("source_dir", ""),
            variety=d.get("variety", ""),
            plot_id=d.get("plot_id", ""),
            scan_date=d.get("scan_date", date.today().isoformat()),
            total_images=d.get("total_images", 0),
            blurry_count=d.get("blurry_count", 0),
            disease_count=d.get("disease_count", 0),
            healthy_count=d.get("healthy_count", 0),
        )
        s.images = [ImageRecord.from_dict(im) for im in d.get("images", [])]
        return s


@dataclass
class AppConfig:
    confidence_threshold: float = 0.5
    blur_threshold: float = 100.0
    default_variety: str = ""
    default_plot: str = ""
    export_format: str = "xlsx"
    store_dir: str = ""
    alert_incidence_rate: float = 30.0
    alert_area_ratio: float = 5.0
    alert_growth_rate: float = 15.0

    def to_dict(self) -> dict:
        return {
            "confidence_threshold": self.confidence_threshold,
            "blur_threshold": self.blur_threshold,
            "default_variety": self.default_variety,
            "default_plot": self.default_plot,
            "export_format": self.export_format,
            "store_dir": self.store_dir,
            "alert_incidence_rate": self.alert_incidence_rate,
            "alert_area_ratio": self.alert_area_ratio,
            "alert_growth_rate": self.alert_growth_rate,
        }

    @staticmethod
    def from_dict(d: dict) -> "AppConfig":
        return AppConfig(
            confidence_threshold=d.get("confidence_threshold", 0.5),
            blur_threshold=d.get("blur_threshold", 100.0),
            default_variety=d.get("default_variety", ""),
            default_plot=d.get("default_plot", ""),
            export_format=d.get("export_format", "xlsx"),
            store_dir=d.get("store_dir", ""),
            alert_incidence_rate=d.get("alert_incidence_rate", 30.0),
            alert_area_ratio=d.get("alert_area_ratio", 5.0),
            alert_growth_rate=d.get("alert_growth_rate", 15.0),
        )


@dataclass
class AuditChange:
    image_idx: int = 0
    image_name: str = ""
    det_idx: int = 0
    old_disease: str = ""
    new_disease: str = ""
    old_confidence: float = 0.0
    new_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "image_idx": self.image_idx,
            "image_name": self.image_name,
            "det_idx": self.det_idx,
            "old_disease": self.old_disease,
            "new_disease": self.new_disease,
            "old_confidence": round(self.old_confidence, 4),
            "new_confidence": round(self.new_confidence, 4),
        }

    @staticmethod
    def from_dict(d: dict) -> "AuditChange":
        return AuditChange(
            image_idx=d.get("image_idx", 0),
            image_name=d.get("image_name", ""),
            det_idx=d.get("det_idx", 0),
            old_disease=d.get("old_disease", ""),
            new_disease=d.get("new_disease", ""),
            old_confidence=d.get("old_confidence", 0.0),
            new_confidence=d.get("new_confidence", 0.0),
        )


@dataclass
class AuditLogEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    session_id: str = ""
    changes: List[AuditChange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "changes": [c.to_dict() for c in self.changes],
        }

    @staticmethod
    def from_dict(d: dict) -> "AuditLogEntry":
        return AuditLogEntry(
            id=d.get("id", uuid.uuid4().hex[:10]),
            timestamp=d.get("timestamp", ""),
            session_id=d.get("session_id", ""),
            changes=[AuditChange.from_dict(c) for c in d.get("changes", [])],
        )
