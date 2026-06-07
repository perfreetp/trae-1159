import click
from collections import defaultdict
from ..core.models import DiseaseType, DISEASE_NAMES_CN
from ..core.detector import get_treatment
from ..core.store import (
    load_session,
    list_sessions,
    get_sessions_by_plot,
    filter_images_by_plot,
)


@click.command("report")
@click.option("--session", "-s", "session_id", default="", help="会话ID")
@click.option("--plot", "-p", default="", help="按地块编号生成报告")
@click.option("--store-dir", default="", help="数据存储目录")
def report_command(session_id, plot, store_dir):
    """统计发病株数和面积，生成防治建议清单"""

    if session_id:
        sess = load_session(session_id, store_dir or None)
        if not sess:
            click.echo(f"❌ 未找到会话: {session_id}")
            return
        sess.recalculate_counts()
        sessions = [sess]
    elif plot:
        sessions = get_sessions_by_plot(plot, store_dir or None)
        for s in sessions:
            s.recalculate_counts()
        sessions = filter_images_by_plot(sessions, plot)
        if not sessions:
            click.echo(f"❌ 未找到地块 {plot} 的扫描记录")
            return
    else:
        sessions_meta = list_sessions(store_dir or None)
        if not sessions_meta:
            click.echo("📭 暂无扫描会话")
            return
        sessions = []
        for meta in sessions_meta:
            s = load_session(meta["id"], store_dir or None)
            if s:
                s.recalculate_counts()
                sessions.append(s)

    click.echo("\n" + "=" * 70)
    click.echo("📋 果园病害诊断报告")
    click.echo("=" * 70)

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

    for sess in sessions:
        click.echo(f"\n📅 会话: {sess.id}  巡园日期: {sess.scan_date or sess.created_at[:10]}")
        click.echo(f"   品种: {sess.variety or '-'}  地块: {sess.plot_id or '-'}")
        click.echo(f"   图片: {sess.total_images}  病害: {sess.disease_count}  "
                    f"健康: {sess.healthy_count}  模糊: {sess.blurry_count}")

        total_images += sess.total_images
        total_disease += sess.disease_count
        total_healthy += sess.healthy_count
        total_blurry += sess.blurry_count

        for img in sess.images:
            pid = img.plot_id or sess.plot_id or "未知地块"
            var = img.variety or sess.variety or "未知品种"
            img_area = img.image_area()

            if img_area > 0:
                plot_image_area[pid] += img_area

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

    click.echo("\n" + "-" * 70)
    click.echo("📊 总体统计:")
    click.echo(f"   扫描会话数: {len(sessions)}")
    click.echo(f"   总图片数: {total_images}")
    click.echo(f"   疑似病害: {total_disease} ({total_disease / max(1, total_images) * 100:.1f}%)")
    click.echo(f"   健康图片: {total_healthy}")
    click.echo(f"   模糊照片: {total_blurry}")

    if all_disease_stats:
        click.echo("\n🦠 病害检出统计:")
        click.echo(f"   {'病害名称':<12} {'检出数':>8} {'占比':>8} {'平均置信度':>12} {'最高置信度':>12} {'病斑面积':>12} {'面积占比':>10}")
        click.echo("   " + "-" * 80)
        total_det = sum(all_disease_stats.values())
        for dname, count in sorted(all_disease_stats.items(), key=lambda x: -x[1]):
            avg_conf = sum(all_confidence[dname]) / len(all_confidence[dname])
            max_conf = max(all_confidence[dname])
            ratio = count / max(1, total_det) * 100
            la = disease_lesion_area.get(dname, 0)
            ia = disease_image_area.get(dname, 0)
            area_pct = la / max(1, ia) * 100 if ia > 0 else 0
            area_str = f"{la:,} px²" if la > 0 else "-"
            pct_str = f"{area_pct:.2f}%" if la > 0 else "-"
            click.echo(
                f"   {dname:<12} {count:>8} {ratio:>7.1f}% {avg_conf:>11.1%} {max_conf:>11.1%} {area_str:>12} {pct_str:>10}"
            )

    if plot_stats:
        click.echo("\n🗺️ 按地块统计:")
        for pid in sorted(plot_stats.keys()):
            click.echo(f"   地块 {pid}:")
            total_plot_lesion = sum(plot_lesion_area[pid].values())
            total_plot_img_area = plot_image_area.get(pid, 0)
            overall_pct = total_plot_lesion / max(1, total_plot_img_area) * 100 if total_plot_img_area > 0 else 0
            for dname, count in sorted(plot_stats[pid].items(), key=lambda x: -x[1]):
                la = plot_lesion_area[pid].get(dname, 0)
                la_pct = la / max(1, total_plot_img_area) * 100 if total_plot_img_area > 0 else 0
                la_str = f"{la:,} px²" if la > 0 else "-"
                click.echo(f"     • {dname}: {count} 处  病斑面积={la_str}  占图片面积={la_pct:.2f}%")
            click.echo(f"     合计病斑面积: {total_plot_lesion:,} px²  占图片面积={overall_pct:.2f}%")

    if variety_stats:
        click.echo("\n🌳 按品种统计:")
        for var in sorted(variety_stats.keys()):
            click.echo(f"   {var}:")
            for dname, count in sorted(variety_stats[var].items(), key=lambda x: -x[1]):
                click.echo(f"     • {dname}: {count} 处")

    if all_disease_stats:
        click.echo("\n" + "-" * 70)
        click.echo("💊 防治建议清单:")
        click.echo()
        for dname in sorted(all_disease_stats.keys()):
            treatment = get_treatment(dname)
            count = all_disease_stats[dname]
            affected_plots = [
                pid for pid in plot_stats if dname in plot_stats[pid]
            ]
            la = disease_lesion_area.get(dname, 0)
            ia = disease_image_area.get(dname, 0)
            click.echo(f"   【{dname}】检出 {count} 处")
            if affected_plots:
                click.echo(f"     涉及地块: {', '.join(sorted(affected_plots))}")
            if la > 0 and ia > 0:
                click.echo(f"     总病斑面积: {la:,} px²  占比: {la / max(1, ia) * 100:.2f}%")
            click.echo(f"     防治方案: {treatment}")
            click.echo()

    click.echo("=" * 70)
    click.echo("报告生成完毕")
