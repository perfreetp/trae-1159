import click
from collections import defaultdict
from ..core.models import DiseaseType
from ..core.store import (
    list_sessions,
    load_session,
    get_sessions_by_plot,
    get_sessions_by_date_range,
    filter_images_by_plot,
)


@click.command("compare")
@click.option("--plot", "-p", default="", help="地块编号")
@click.option("--from", "from_date", default="", help="起始巡园日期 (YYYY-MM-DD)")
@click.option("--to", "to_date", default="", help="结束巡园日期 (YYYY-MM-DD)")
@click.option("--session1", "-s1", default="", help="第一个会话ID")
@click.option("--session2", "-s2", default="", help="第二个会话ID")
@click.option("--store-dir", default="", help="数据存储目录")
def compare_command(plot, from_date, to_date, session1, session2, store_dir):
    """比较不同日期的病害扩散情况"""

    if session1 and session2:
        sess1 = load_session(session1, store_dir or None)
        sess2 = load_session(session2, store_dir or None)
        if not sess1:
            click.echo(f"❌ 未找到会话: {session1}")
            return
        if not sess2:
            click.echo(f"❌ 未找到会话: {session2}")
            return
        sess1.recalculate_counts()
        sess2.recalculate_counts()
        if plot:
            sess1 = filter_images_by_plot([sess1], plot)[0] if filter_images_by_plot([sess1], plot) else sess1
            sess2 = filter_images_by_plot([sess2], plot)[0] if filter_images_by_plot([sess2], plot) else sess2
        _compare_two_sessions(sess1, sess2)
        return

    if plot:
        sessions = get_sessions_by_plot(plot, store_dir or None)
        sessions = filter_images_by_plot(sessions, plot)
    elif from_date and to_date:
        sessions = get_sessions_by_date_range(from_date, to_date, store_dir or None)
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

    for s in sessions:
        s.recalculate_counts()

    if len(sessions) < 2:
        click.echo("⚠️  至少需要2次扫描会话才能比较，请先运行更多 scan")
        _list_available_sessions(sessions)
        return

    sessions.sort(key=lambda s: s.scan_date or s.created_at[:10])
    _compare_trend(sessions)


def _compare_two_sessions(sess1, sess2):
    click.echo("\n📊 会话对比:")
    click.echo("=" * 70)
    click.echo(f"  会话A: {sess1.id}  巡园日期={sess1.scan_date or sess1.created_at[:10]}  "
               f"品种={sess1.variety}  地块={sess1.plot_id}")
    click.echo(f"  会话B: {sess2.id}  巡园日期={sess2.scan_date or sess2.created_at[:10]}  "
               f"品种={sess2.variety}  地块={sess2.plot_id}")
    click.echo("-" * 70)

    stats1 = _compute_disease_stats(sess1)
    stats2 = _compute_disease_stats(sess2)

    click.echo(f"\n  {'指标':<16} {'会话A':>10} {'会话B':>10} {'变化':>10}")
    click.echo("  " + "-" * 50)

    click.echo(
        f"  {'总图片数':<14} {sess1.total_images:>10} {sess2.total_images:>10} "
        f"{sess2.total_images - sess1.total_images:>+10}"
    )
    click.echo(
        f"  {'病害图片':<14} {sess1.disease_count:>10} {sess2.disease_count:>10} "
        f"{sess2.disease_count - sess1.disease_count:>+10}"
    )
    click.echo(
        f"  {'健康图片':<14} {sess1.healthy_count:>10} {sess2.healthy_count:>10} "
        f"{sess2.healthy_count - sess1.healthy_count:>+10}"
    )
    click.echo(
        f"  {'模糊图片':<14} {sess1.blurry_count:>10} {sess2.blurry_count:>10} "
        f"{sess2.blurry_count - sess1.blurry_count:>+10}"
    )

    all_diseases = set(list(stats1.keys()) + list(stats2.keys()))
    if all_diseases:
        click.echo(f"\n  🦠 各病害检出数:")
        click.echo(f"  {'病害':<14} {'会话A':>10} {'会话B':>10} {'变化':>10}")
        click.echo("  " + "-" * 50)
        for dname in sorted(all_diseases):
            c1 = stats1.get(dname, 0)
            c2 = stats2.get(dname, 0)
            delta = c2 - c1
            arrow = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
            click.echo(f"  {dname:<14} {c1:>10} {c2:>10} {delta:>+10} {arrow}")

    rate1 = sess1.disease_count / max(1, sess1.total_images) * 100
    rate2 = sess2.disease_count / max(1, sess2.total_images) * 100
    click.echo(f"\n  发病率: 会话A={rate1:.1f}%  会话B={rate2:.1f}%  变化={rate2 - rate1:+.1f}%")

    if rate2 > rate1:
        click.echo("  ⚠️  病害呈扩散趋势，建议加强防治！")
    elif rate2 < rate1:
        click.echo("  ✅ 病害有所控制，防治措施有效。")


def _compare_trend(sessions):
    click.echo("\n📊 病害趋势分析:")
    click.echo("=" * 70)

    click.echo(f"\n  {'巡园日期':<12} {'总图片':>8} {'病害':>8} {'健康':>8} {'模糊':>8} {'发病率':>8}")
    click.echo("  " + "-" * 56)

    for sess in sessions:
        rate = sess.disease_count / max(1, sess.total_images) * 100
        d = sess.scan_date or sess.created_at[:10]
        bar = "█" * int(rate / 5)
        click.echo(
            f"  {d:<12} {sess.total_images:>8} {sess.disease_count:>8} "
            f"{sess.healthy_count:>8} {sess.blurry_count:>8} {rate:>7.1f}% {bar}"
        )

    disease_trend = defaultdict(list)
    for sess in sessions:
        stats = _compute_disease_stats(sess)
        d = sess.scan_date or sess.created_at[:10]
        for dname, count in stats.items():
            disease_trend[dname].append((d, count))

    if disease_trend:
        click.echo(f"\n  🦠 各病害变化趋势:")
        for dname in sorted(disease_trend.keys()):
            points = disease_trend[dname]
            counts = [c for _, c in points]
            trend = "📈上升" if counts[-1] > counts[0] else ("📉下降" if counts[-1] < counts[0] else "➡️持平")
            click.echo(f"  • {dname}: {counts[0]}→{counts[-1]} {trend}")


def _compute_disease_stats(sess) -> dict:
    stats = defaultdict(int)
    for img in sess.images:
        for det in img.detections:
            if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN):
                stats[det.disease.value] += 1
    return dict(stats)


def _list_available_sessions(sessions):
    click.echo("\n可用会话:")
    for i, s in enumerate(sessions):
        click.echo(
            f"  [{i}] ID={s.id}  巡园日期={s.scan_date or s.created_at[:10]}  "
            f"地块={s.plot_id}  图片={s.total_images}"
        )
