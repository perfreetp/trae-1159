import os
import json
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from .models import ScanSession, ImageRecord, AppConfig, DiseaseType

_DEFAULT_STORE = os.path.join(os.path.expanduser("~"), ".orchard_guard")
_SESSIONS_FILE = "sessions.json"
_CONFIG_FILE = "config.json"


def _ensure_store(store_dir: Optional[str] = None) -> str:
    d = store_dir or _DEFAULT_STORE
    os.makedirs(d, exist_ok=True)
    return d


def save_session(session: ScanSession, store_dir: Optional[str] = None) -> str:
    d = _ensure_store(store_dir)
    path = os.path.join(d, f"session_{session.id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
    _update_sessions_index(session, d)
    return path


def _update_sessions_index(session: ScanSession, store_dir: str):
    idx_path = os.path.join(store_dir, _SESSIONS_FILE)
    index = {}
    if os.path.exists(idx_path):
        with open(idx_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    plots_in_session = set()
    for img in session.images:
        if img.plot_id:
            plots_in_session.add(img.plot_id)
    if session.plot_id:
        plots_in_session.add(session.plot_id)
    index[session.id] = {
        "id": session.id,
        "created_at": session.created_at,
        "source_dir": session.source_dir,
        "variety": session.variety,
        "plot_id": session.plot_id,
        "scan_date": session.scan_date,
        "total_images": session.total_images,
        "disease_count": session.disease_count,
        "healthy_count": session.healthy_count,
        "blurry_count": session.blurry_count,
        "image_plots": sorted(plots_in_session),
    }
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def load_session(session_id: str, store_dir: Optional[str] = None) -> Optional[ScanSession]:
    d = _ensure_store(store_dir)
    path = os.path.join(d, f"session_{session_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ScanSession.from_dict(data)


def list_sessions(store_dir: Optional[str] = None) -> List[dict]:
    d = _ensure_store(store_dir)
    idx_path = os.path.join(d, _SESSIONS_FILE)
    if not os.path.exists(idx_path):
        return []
    with open(idx_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    return sorted(index.values(), key=lambda x: x.get("created_at", ""), reverse=True)


def load_config(store_dir: Optional[str] = None) -> AppConfig:
    d = _ensure_store(store_dir)
    cfg_path = os.path.join(d, _CONFIG_FILE)
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    return AppConfig(store_dir=d)


def save_config(config: AppConfig, store_dir: Optional[str] = None) -> str:
    d = _ensure_store(store_dir or config.store_dir)
    config.store_dir = d
    cfg_path = os.path.join(d, _CONFIG_FILE)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
    return cfg_path


def update_session(session: ScanSession, store_dir: Optional[str] = None) -> str:
    session.recalculate_counts()
    return save_session(session, store_dir)


def get_sessions_by_plot(
    plot_id: str, store_dir: Optional[str] = None
) -> List[ScanSession]:
    sessions = []
    for meta in list_sessions(store_dir):
        if meta.get("plot_id") == plot_id or plot_id in meta.get("image_plots", []):
            s = load_session(meta["id"], store_dir)
            if s:
                sessions.append(s)
    return sessions


def get_sessions_by_date_range(
    start_date: str, end_date: str, store_dir: Optional[str] = None
) -> List[ScanSession]:
    sessions = []
    for meta in list_sessions(store_dir):
        sd = meta.get("scan_date", "") or meta.get("created_at", "")[:10]
        if start_date <= sd <= end_date:
            s = load_session(meta["id"], store_dir)
            if s:
                sessions.append(s)
    return sessions


def filter_images_by_plot(
    sessions: List[ScanSession], plot_id: str
) -> List[ScanSession]:
    filtered = []
    for sess in sessions:
        matched = [img for img in sess.images if img.plot_id == plot_id]
        if matched:
            from .models import ScanSession as _S
            fs = _S(
                id=sess.id,
                created_at=sess.created_at,
                source_dir=sess.source_dir,
                variety=sess.variety,
                plot_id=plot_id,
                scan_date=sess.scan_date,
                images=matched,
            )
            fs.recalculate_counts()
            filtered.append(fs)
    return filtered


def resolve_sessions(
    session_id: str = "",
    plot: str = "",
    from_date: str = "",
    to_date: str = "",
    store_dir: Optional[str] = None,
) -> Tuple[List[ScanSession], bool]:
    sessions = []
    ok = True

    if session_id:
        sess = load_session(session_id, store_dir)
        if not sess:
            return [], False
        sess.recalculate_counts()
        if plot:
            filtered = filter_images_by_plot([sess], plot)
            if not filtered:
                return [], False
            sessions = filtered
        else:
            sessions = [sess]
    elif plot and from_date and to_date:
        by_date = get_sessions_by_date_range(from_date, to_date, store_dir)
        for s in by_date:
            s.recalculate_counts()
        sessions = filter_images_by_plot(by_date, plot)
        if not sessions:
            return [], False
    elif plot:
        by_plot = get_sessions_by_plot(plot, store_dir)
        for s in by_plot:
            s.recalculate_counts()
        sessions = filter_images_by_plot(by_plot, plot)
        if not sessions:
            return [], False
    elif from_date and to_date:
        sessions = get_sessions_by_date_range(from_date, to_date, store_dir)
        for s in sessions:
            s.recalculate_counts()
    else:
        sessions_meta = list_sessions(store_dir)
        if not sessions_meta:
            return [], False
        for meta in sessions_meta:
            s = load_session(meta["id"], store_dir)
            if s:
                s.recalculate_counts()
                sessions.append(s)

    sessions.sort(key=lambda s: s.scan_date or s.created_at[:10])
    return sessions, True


def compute_statistics(sessions: List[ScanSession]) -> Dict:
    total_images = 0
    total_disease = 0
    total_healthy = 0
    total_blurry = 0
    all_disease_stats = defaultdict(int)
    all_confidence = defaultdict(list)
    plot_stats = defaultdict(lambda: defaultdict(int))
    variety_stats = defaultdict(lambda: defaultdict(int))
    plot_lesion_area = defaultdict(lambda: defaultdict(int))
    plot_image_area = defaultdict(int)
    disease_lesion_area = defaultdict(int)
    disease_image_area = defaultdict(int)
    plot_total_images = defaultdict(int)
    plot_disease_images = defaultdict(int)
    plot_healthy_images = defaultdict(int)
    scan_dates = set()

    for sess in sessions:
        sd = sess.scan_date or sess.created_at[:10]
        scan_dates.add(sd)
        total_images += sess.total_images
        total_disease += sess.disease_count
        total_healthy += sess.healthy_count
        total_blurry += sess.blurry_count

        for img in sess.images:
            pid = img.plot_id or sess.plot_id or "未知地块"
            var = img.variety or sess.variety or "未知品种"
            img_area = img.image_area()
            plot_total_images[pid] += 1
            if img_area > 0:
                plot_image_area[pid] += img_area
            if img.has_disease():
                plot_disease_images[pid] += 1
            if img.is_healthy():
                plot_healthy_images[pid] += 1

            for det in img.detections:
                if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN):
                    dname = det.disease.value
                    all_disease_stats[dname] += 1
                    all_confidence[dname].append(det.confidence)
                    plot_stats[pid][dname] += 1
                    variety_stats[var][dname] += 1
                    if det.bbox and img_area > 0:
                        bbox_area = det.bbox.area()
                        disease_lesion_area[dname] += bbox_area
                        disease_image_area[dname] += img_area
                        plot_lesion_area[pid][dname] += bbox_area

    return {
        "total_images": total_images,
        "total_disease": total_disease,
        "total_healthy": total_healthy,
        "total_blurry": total_blurry,
        "all_disease_stats": dict(all_disease_stats),
        "all_confidence": dict(all_confidence),
        "plot_stats": {k: dict(v) for k, v in plot_stats.items()},
        "variety_stats": {k: dict(v) for k, v in variety_stats.items()},
        "plot_lesion_area": {k: dict(v) for k, v in plot_lesion_area.items()},
        "plot_image_area": dict(plot_image_area),
        "disease_lesion_area": dict(disease_lesion_area),
        "disease_image_area": dict(disease_image_area),
        "plot_total_images": dict(plot_total_images),
        "plot_disease_images": dict(plot_disease_images),
        "plot_healthy_images": dict(plot_healthy_images),
        "scan_dates": sorted(scan_dates),
    }


def compute_summary(store_dir: Optional[str] = None) -> Dict:
    all_meta = list_sessions(store_dir)
    total_scans = len(all_meta)
    total_images = 0
    total_disease = 0
    total_healthy = 0
    total_blurry = 0
    plots = set()
    varieties = set()

    for meta in all_meta:
        s = load_session(meta["id"], store_dir)
        if not s:
            continue
        s.recalculate_counts()
        total_images += s.total_images
        total_disease += s.disease_count
        total_healthy += s.healthy_count
        total_blurry += s.blurry_count
        for img in s.images:
            if img.plot_id:
                plots.add(img.plot_id)
            if img.variety:
                varieties.add(img.variety)

    return {
        "total_scans": total_scans,
        "total_images": total_images,
        "total_disease": total_disease,
        "total_healthy": total_healthy,
        "total_blurry": total_blurry,
        "plots": sorted(plots),
        "varieties": sorted(varieties),
    }
