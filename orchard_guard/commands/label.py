import click
from ..core.models import DiseaseType, DISEASE_NAMES_CN
from ..core.store import load_session, update_session, list_sessions


@click.command("label")
@click.option("--session", "-s", "session_id", default="", help="会话ID")
@click.option("--image", "-i", "image_idx", type=int, default=None, help="图片序号 (从0开始)")
@click.option("--list-sessions", "list_only", is_flag=True, help="列出所有会话")
@click.option("--show-all", is_flag=True, help="显示所有图片检测结果")
@click.option("--store-dir", default="", help="数据存储目录")
def label_command(session_id, image_idx, list_only, show_all, store_dir):
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
                f"日期={s.get('created_at', '')[:10]}"
            )
        if not session_id:
            click.echo("\n使用 --session <ID> 指定会话进行标注")
            return

    sess = load_session(session_id, store_dir or None)
    if not sess:
        click.echo(f"❌ 未找到会话: {session_id}")
        return

    if show_all:
        _show_all_results(sess)
        return

    if image_idx is not None:
        _label_single(sess, image_idx, store_dir)
    else:
        _interactive_label(sess, store_dir)


def _show_all_results(sess):
    click.echo(f"\n📋 会话 {sess.id} 检测结果:")
    click.echo(f"   品种: {sess.variety or '-'}  地块: {sess.plot_id or '-'}")
    click.echo("-" * 80)
    for idx, img in enumerate(sess.images):
        status = "🔍" if not img.is_blurry else "🌫️ 模糊"
        disease_str = ", ".join(
            f"{d.disease.value}({d.confidence:.0%}{'✏️' if d.corrected else ''})"
            for d in img.detections
        ) or "无检测"
        click.echo(f"  [{idx}] {status} {img.file_name}")
        click.echo(f"       → {disease_str}")
        for det in img.detections:
            if det.bbox:
                click.echo(
                    f"       → 区域: ({det.bbox.x1},{det.bbox.y1})-({det.bbox.x2},{det.bbox.y2})"
                )


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

    available = [d for d in DiseaseType if d not in (DiseaseType.UNKNOWN,)]
    click.echo("选择正确病害类型:")
    for di, dt in enumerate(available):
        click.echo(f"  [{di}] {dt.value}")

    new_idx = click.prompt("病害类型序号", type=int)
    if new_idx < 0 or new_idx >= len(available):
        click.echo("❌ 序号无效")
        return

    det = img.detections[det_idx]
    if not det.corrected:
        det.original_disease = det.disease
    det.disease = available[new_idx]
    det.corrected = True

    new_conf = click.prompt("修正后置信度 (0-1)", type=float, default=det.confidence)
    det.confidence = max(0.0, min(1.0, new_conf))

    update_session(sess, store_dir or None)
    click.echo(f"✅ 已修正: {det.original_disease.value if det.original_disease else '?'} → {det.disease.value} ({det.confidence:.0%})")
