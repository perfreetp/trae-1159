import click
from ..core.models import DiseaseType, DISEASE_NAMES_CN, AuditLogEntry, AuditChange
from ..core.store import (
    load_session, update_session, list_sessions,
    save_audit_log, load_audit_log, undo_last_audit,
)


@click.command("label")
@click.option("--session", "-s", "session_id", default="", help="会话ID")
@click.option("--image", "-i", "image_idx", type=int, default=None, help="图片序号 (从0开始)")
@click.option("--list-sessions", "list_only", is_flag=True, help="列出所有会话")
@click.option("--show-all", is_flag=True, help="显示所有图片检测结果")
@click.option("--range", "img_range", default="", help="批量修正图片序号范围 (如 0-10)")
@click.option("--filter-disease", "filter_disease", default="", help="筛选病害类型 (如 健康、叶斑病)")
@click.option("--filter-confidence", "filter_conf", default="", help="筛选置信度区间 (如 0-0.4)")
@click.option("--set-disease", "set_disease", default="", help="批量设置病害类型 (如 锈病、未知)")
@click.option("--set-confidence", "set_confidence", type=float, default=None, help="批量设置置信度")
@click.option("--history", is_flag=True, help="查看修改记录")
@click.option("--undo", is_flag=True, help="撤回最近一次批量修正")
@click.option("--store-dir", default="", help="数据存储目录")
def label_command(
    session_id, image_idx, list_only, show_all, img_range,
    filter_disease, filter_conf, set_disease, set_confidence,
    history, undo, store_dir
):
    """查看和修正病害识别结果"""

    if list_only or not session_id:
        sessions = list_sessions(store_dir or None)
        if not sessions:
            click.echo("📭 暂无扫描会话，请先运行 scan 命令")
            return
        click.echo("📋 扫描会话列表:")
        for i, s in enumerate(sessions):
            click.echo(
                f"  [{i}] ID={s['id']}  "
                f"品种={s.get('variety', '-')}  地块={s.get('plot_id', '-')}  "
                f"图片={s.get('total_images', 0)}  "
                f"病害={s.get('disease_count', 0)}  "
                f"巡园日期={s.get('scan_date', '-')}"
            )
        if not session_id:
            click.echo("\n使用 --session <ID> 指定会话进行标注")
            return

    sess = load_session(session_id, store_dir or None)
    if not sess:
        click.echo(f"❌ 未找到会话: {session_id}")
        return

    if history:
        _show_history(session_id, store_dir)
        return

    if undo:
        _do_undo(session_id, store_dir)
        return

    if show_all:
        _show_all_results(sess)
        return

    batch_mode = img_range or filter_disease or filter_conf
    modify_mode = set_disease or set_confidence is not None

    if batch_mode:
        if modify_mode:
            _batch_modify(sess, img_range, filter_disease, filter_conf, set_disease, set_confidence, store_dir)
        else:
            _batch_preview(sess, img_range, filter_disease, filter_conf)
        return

    if image_idx is not None:
        _label_single(sess, image_idx, store_dir)
    else:
        _interactive_label(sess, store_dir)


def _show_history(session_id, store_dir):
    log = load_audit_log(store_dir or None)
    session_log = [e for e in log if e.session_id == session_id]
    if not session_log:
        click.echo(f"📭 会话 {session_id} 暂无修改记录")
        return
    click.echo(f"\n📝 会话 {session_id} 修改记录:")
    click.echo("-" * 70)
    for entry in reversed(session_log):
        click.echo(f"  [{entry.id}] {entry.timestamp}")
        for c in entry.changes:
            conf_change = f" 置信度={c.old_confidence:.1%}→{c.new_confidence:.1%}" if c.old_confidence != c.new_confidence else ""
            click.echo(f"    图片[{c.image_idx}] {c.image_name}: {c.old_disease}→{c.new_disease}{conf_change}")
        click.echo()


def _do_undo(session_id, store_dir):
    entry = undo_last_audit(session_id, store_dir or None)
    if not entry:
        click.echo(f"❌ 会话 {session_id} 没有可撤回的修改记录")
        return
    click.echo(f"✅ 已撤回修改 [{entry.id}] {entry.timestamp}")
    for c in entry.changes:
        click.echo(f"   图片[{c.image_idx}] {c.image_name}: {c.new_disease}→{c.old_disease}")

    sess = load_session(session_id, store_dir or None)
    if sess:
        sess.recalculate_counts()
        click.echo(f"   当前统计: 病害={sess.disease_count}  健康={sess.healthy_count}  总图片={sess.total_images}")


def _show_all_results(sess):
    click.echo(f"\n📋 会话 {sess.id} 检测结果:")
    click.echo(f"   品种: {sess.variety or '-'}  地块: {sess.plot_id or '-'}")
    click.echo("-" * 80)
    for idx, img in enumerate(sess.images):
        status = "🔍" if not img.is_blurry else "🌫️模糊"
        disease_str = ", ".join(
            f"{d.disease.value}({d.confidence:.0%}{'✏️' if d.corrected else ''})"
            for d in img.detections
        ) or "无检测"
        click.echo(f"  [{idx}] {status} {img.file_name}  地块={img.plot_id or '-'}")
        click.echo(f"       → {disease_str}")


def _label_single(sess, idx, store_dir):
    if idx < 0 or idx >= len(sess.images):
        click.echo(f"❌ 图片序号超出范围 (0-{len(sess.images)-1})")
        return
    img = sess.images[idx]
    _print_image_detail(img, idx)
    _prompt_correction(sess, idx, store_dir)


def _interactive_label(sess, store_dir):
    click.echo(f"\n🏷️ 进入标注模式 - 会话 {sess.id}")
    click.echo(f"   图片总数: {len(sess.images)}")
    click.echo("   命令: n=下一张, p=上一张, q=退出, 序号=跳转, d=修改病害类型")
    click.echo()

    current = 0
    while True:
        if current >= len(sess.images):
            current = len(sess.images) - 1
        if current < 0:
            current = 0

        img = sess.images[current]
        _print_image_detail(img, current)

        cmd = click.prompt("\n操作", default="n", show_default=False).strip().lower()

        if cmd == "q":
            click.echo("退出标注模式")
            break
        elif cmd == "n":
            current += 1
            if current >= len(sess.images):
                click.echo("已到末尾")
                current = len(sess.images) - 1
        elif cmd == "p":
            current -= 1
        elif cmd == "d":
            _prompt_correction(sess, current, store_dir)
        elif cmd.isdigit():
            target = int(cmd)
            if 0 <= target < len(sess.images):
                current = target
            else:
                click.echo(f"❌ 序号超出范围 (0-{len(sess.images)-1})")
        else:
            click.echo("未知命令")


def _print_image_detail(img, idx):
    click.echo(f"\n📷 [{idx}] {img.file_name}")
    click.echo(f"   路径: {img.file_path}")
    click.echo(f"   品种: {img.variety or '-'}  地块: {img.plot_id or '-'}  日期: {img.scan_date}")
    if img.is_blurry:
        click.echo(f"   🌫️ 模糊照片 (模糊度={img.blur_score:.1f})")
    click.echo("   检测结果:")
    if not img.detections:
        click.echo("     (无)")
    for di, det in enumerate(img.detections):
        corrected_mark = " ✏️已修正" if det.corrected else ""
        bbox_str = ""
        if det.bbox:
            bbox_str = f" 区域=({det.bbox.x1},{det.bbox.y1})-({det.bbox.x2},{det.bbox.y2})"
        click.echo(
            f"     [{di}] {det.disease.value}  置信度={det.confidence:.1%}{corrected_mark}{bbox_str}"
        )


def _prompt_correction(sess, img_idx, store_dir):
    img = sess.images[img_idx]
    if not img.detections:
        click.echo("该图片无检测结果，无法修正")
        return

    click.echo("选择要修正的检测项:")
    for di, det in enumerate(img.detections):
        click.echo(f"  [{di}] {det.disease.value} (置信度={det.confidence:.1%})")

    det_idx = click.prompt("检测项序号", type=int, default=0)
    if det_idx < 0 or det_idx >= len(img.detections):
        click.echo("❌ 序号无效")
        return

    det = img.detections[det_idx]
    old_disease = det.disease.value
    old_conf = det.confidence
    _apply_disease_change(det)

    change = AuditChange(
        image_idx=img_idx,
        image_name=img.file_name,
        det_idx=det_idx,
        old_disease=old_disease,
        new_disease=det.disease.value,
        old_confidence=old_conf,
        new_confidence=det.confidence,
    )
    entry = AuditLogEntry(session_id=sess.id, changes=[change])
    save_audit_log(entry, store_dir or None)

    update_session(sess, store_dir or None)
    click.echo(f"✅ 已修正: {old_disease} → {det.disease.value} ({det.confidence:.0%})")


def _apply_disease_change(det):
    available = [d for d in DiseaseType if d not in (DiseaseType.UNKNOWN,)]
    click.echo("选择病害类型:")
    for di, dt in enumerate(available):
        click.echo(f"  [{di}] {dt.value}")

    new_idx = click.prompt("病害类型序号", type=int)
    if new_idx < 0 or new_idx >= len(available):
        click.echo("❌ 序号无效")
        return

    if not det.corrected:
        det.original_disease = det.disease
    det.disease = available[new_idx]
    det.corrected = True

    new_conf = click.prompt("修正后置信度 (0-1)", type=float, default=det.confidence)
    det.confidence = max(0.0, min(1.0, new_conf))


def _parse_range(range_str, max_val):
    if not range_str:
        return list(range(max_val))
    indices = []
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            segs = part.split("-", 1)
            start = int(segs[0])
            end = int(segs[1])
            indices.extend(range(max(0, start), min(end + 1, max_val)))
        else:
            idx = int(part)
            if 0 <= idx < max_val:
                indices.append(idx)
    return sorted(set(indices))


def _parse_conf_range(conf_str):
    if not conf_str:
        return None, None
    parts = conf_str.split("-", 1)
    if len(parts) == 2:
        return float(parts[0]), float(parts[1])
    v = float(parts[0])
    return v, v


def _match_filters(det, filter_disease, conf_low, conf_high):
    if filter_disease:
        if det.disease.value != filter_disease:
            return False
    if conf_low is not None:
        if det.confidence < conf_low or det.confidence > conf_high:
            return False
    return True


def _batch_preview(sess, img_range, filter_disease, filter_conf):
    indices = _parse_range(img_range, len(sess.images))
    conf_low, conf_high = _parse_conf_range(filter_conf)
    matched = 0

    click.echo(f"\n📋 筛选预览 (会话 {sess.id}):")
    if filter_disease:
        click.echo(f"   病害筛选: {filter_disease}")
    if filter_conf:
        click.echo(f"   置信度区间: {filter_conf}")

    for idx in indices:
        img = sess.images[idx]
        for det in img.detections:
            if _match_filters(det, filter_disease, conf_low, conf_high):
                matched += 1
                click.echo(
                    f"  [{idx}] {img.file_name}  {det.disease.value} ({det.confidence:.1%})"
                )

    click.echo(f"\n   共匹配 {matched} 条检测结果")
    click.echo("   使用 --set-disease 和 --set-confidence 进行批量修正")


def _batch_modify(sess, img_range, filter_disease, filter_conf, set_disease, set_confidence, store_dir):
    target_disease = DISEASE_NAMES_CN.get(set_disease) if set_disease else None
    if set_disease and not target_disease:
        click.echo(f"❌ 未知病害类型: {set_disease}")
        click.echo(f"   可选: {', '.join(d.value for d in DiseaseType)}")
        return

    indices = _parse_range(img_range, len(sess.images))
    conf_low, conf_high = _parse_conf_range(filter_conf)
    modified = 0
    changes = []

    for idx in indices:
        img = sess.images[idx]
        for det_idx, det in enumerate(img.detections):
            if _match_filters(det, filter_disease, conf_low, conf_high):
                old_disease = det.disease.value
                old_conf = det.confidence
                if target_disease:
                    if not det.corrected:
                        det.original_disease = det.disease
                    det.disease = target_disease
                    det.corrected = True
                if set_confidence is not None:
                    det.confidence = max(0.0, min(1.0, set_confidence))
                changes.append(AuditChange(
                    image_idx=idx,
                    image_name=img.file_name,
                    det_idx=det_idx,
                    old_disease=old_disease,
                    new_disease=det.disease.value,
                    old_confidence=old_conf,
                    new_confidence=det.confidence,
                ))
                modified += 1

    if modified == 0:
        click.echo("⚠️  没有匹配的检测结果")
        return

    entry = AuditLogEntry(session_id=sess.id, changes=changes)
    save_audit_log(entry, store_dir or None)

    update_session(sess, store_dir or None)
    click.echo(f"✅ 已批量修正 {modified} 条检测结果 (记录ID: {entry.id})")

    sess.recalculate_counts()
    click.echo(f"   当前统计: 病害={sess.disease_count}  健康={sess.healthy_count}  总图片={sess.total_images}")
    click.echo(f"   使用 --undo 可撤回此次修改")
