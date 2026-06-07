import os
import json
from datetime import datetime
from typing import List, Optional, Dict
from .models import ScanSession, ImageRecord, AppConfig

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
    return save_session(session, store_dir)


def get_sessions_by_plot(
    plot_id: str, store_dir: Optional[str] = None
) -> List[ScanSession]:
    sessions = []
    for meta in list_sessions(store_dir):
        if meta.get("plot_id") == plot_id:
            s = load_session(meta["id"], store_dir)
            if s:
                sessions.append(s)
    return sessions


def get_sessions_by_date_range(
    start_date: str, end_date: str, store_dir: Optional[str] = None
) -> List[ScanSession]:
    sessions = []
    for meta in list_sessions(store_dir):
        created = meta.get("created_at", "")[:10]
        if start_date <= created <= end_date:
            s = load_session(meta["id"], store_dir)
            if s:
                sessions.append(s)
    return sessions


def compute_summary(store_dir: Optional[str] = None) -> Dict:
    all_sessions = list_sessions(store_dir)
    total_scans = len(all_sessions)
    total_images = sum(s.get("total_images", 0) for s in all_sessions)
    total_disease = sum(s.get("disease_count", 0) for s in all_sessions)
    total_healthy = sum(s.get("healthy_count", 0) for s in all_sessions)
    total_blurry = sum(s.get("blurry_count", 0) for s in all_sessions)
    plots = set(s.get("plot_id", "") for s in all_sessions if s.get("plot_id"))
    varieties = set(s.get("variety", "") for s in all_sessions if s.get("variety"))
    return {
        "total_scans": total_scans,
        "total_images": total_images,
        "total_disease": total_disease,
        "total_healthy": total_healthy,
        "total_blurry": total_blurry,
        "plots": sorted(plots),
        "varieties": sorted(varieties),
    }
