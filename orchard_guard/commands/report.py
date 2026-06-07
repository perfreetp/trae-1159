import click
from collections import defaultdict
from ..core.models import DiseaseType, DISEASE_NAMES_CN
from ..core.detector import get_treatment
from ..core.store import load_session, list_sessions, get_sessions_by_plot


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
        sessions = [sess]
    elif plot:
        sessions = get_sessions_by_plot(plot, store_dir or None)
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
    treatment_list = []

    for sess in sessions:
        click.echo(f"\n📅 会话: {sess.id}  日期: {sess.scan_date or sess.created_at[:10]}")
        click.echo(f"   品种: {sess.variety or '-'}  地块: {sess.plot_id or '-'}")
        click.echo(f"   图片: {sess.total_images}  病害: {sess.disease_count}  "
                    f"健康: {sess.healthy_count}  模糊: {sess.blurry_count}")

        total_images += sess.total_images
        total_disease += sess.disease_count
        total_healthy += sess.healthy_count
        total_blurry += sess.blurry_count

        for img in sess.images:
            for det in img.detections:
                if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN):
                    dname = det.disease.value
                    all_disease_stats[dname] += 1
                    all_confidence[dname].append(det.confidence)
                    pid = img.plot_id or sess.plot_id or "未知地块"
                    plot_stats[pid][dname] += 1
                    var = img.variety or sess.variety or "未知品种"
                    variety_stats[var][dname] += 1

    click.echo("\n" + "-" * 70)
    click.echo("📊 总体统计:")
    click.echo(f"   扫描会话数: {len(sessions)}")
    click.echo(f"   总图片数: {total_images}")
    click.echo(f"   疑似病害: {total_disease} ({total_disease / max(1, total_images) * 100:.1f}%)")
    click.echo(f"   健康图片: {total_healthy}")
    click.echo(f"   模糊照片: {total_blurry}")

    if all_disease_stats:
        click.echo("\n🦠 病害检出统计:")
        click.echo(f"   {'病害名称':<12} {'检出数':>8} {'占比':>8} {'平均置信度':>12} {'最高置信度':>12}")
        click.echo("   " + "-" * 56)
        total_det = sum(all_disease_stats.values())
        for dname, count in sorted(all_disease_stats.items(), key=lambda x: -x[1]):
            avg_conf = sum(all_confidence[dname]) / len(all_confidence[dname])
            max_conf = max(all_confidence[dname])
            ratio = count / max(1, total_det) * 100
            click.echo(
                f"   {dname:<12} {count:>8} {ratio:>7.1f}% {avg_conf:>11.1%} {max_conf:>11.1%}"
            )

    if plot_stats:
        click.echo("\n🗺️ 按地块统计:")
        for pid in sorted(plot_stats.keys()):
            click.echo(f"   地块 {pid}:")
            for dname, count in sorted(plot_stats[pid].items(), key=lambda x: -x[1]):
                click.echo(f"     • {dname}: {count} 处")

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
            click.echo(f"   【{dname}】检出 {count} 处")
            if affected_plots:
                click.echo(f"     涉及地块: {', '.join(sorted(affected_plots))}")
            click.echo(f"     防治方案: {treatment}")
            click.echo()

    click.echo("=" * 70)
    click.echo("报告生成完毕")
