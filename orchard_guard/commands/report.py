import click
from ..core.models import DiseaseType
from ..core.detector import get_treatment
from ..core.store import (
    resolve_sessions, compute_statistics, compute_priority_watch, load_config,
)


@click.command("report")
@click.option("--session", "-s", "session_id", default="", help="会话ID")
@click.option("--plot", "-p", default="", help="按地块编号生成报告")
@click.option("--store-dir", default="", help="数据存储目录")
def report_command(session_id, plot, store_dir):
    """统计发病株数和面积，生成防治建议清单"""

    sessions, ok = resolve_sessions(
        session_id=session_id, plot=plot, store_dir=store_dir or None
    )
    if not ok or not sessions:
        if session_id:
            click.echo(f"❌ 未找到会话: {session_id}")
        elif plot:
            click.echo(f"❌ 未找到地块 {plot} 的扫描记录")
        else:
            click.echo("📭 暂无扫描会话")
        return

    stats = compute_statistics(sessions)
    config = load_config(store_dir or None)
    watch = compute_priority_watch(sessions, config)

    click.echo("\n" + "=" * 70)
    click.echo("📋 果园病害诊断报告")
    click.echo("=" * 70)

    click.echo(f"\n📅 巡园日期: {', '.join(stats['scan_dates'])}")
    click.echo(f"   扫描会话数: {len(sessions)}")
    click.echo(f"   总图片数: {stats['total_images']}")
    click.echo(f"   疑似病害: {stats['total_disease']} ({stats['total_disease'] / max(1, stats['total_images']) * 100:.1f}%)")
    click.echo(f"   健康图片: {stats['total_healthy']}")
    click.echo(f"   模糊照片: {stats['total_blurry']}")

    _print_detail_summary(stats)
    _print_disease_summary(stats)
    _print_plot_summary(stats)
    _print_variety_summary(stats)
    _print_priority_watch(watch, config)
    _print_treatment_list(stats)

    click.echo("=" * 70)
    click.echo("报告生成完毕")


def _print_detail_summary(stats):
    detail = stats.get("detail_summary", [])
    if not detail:
        return

    click.echo("\n" + "-" * 70)
    click.echo("📋 巡园台账明细 (日期×地块×品种×病害):")
    click.echo(f"   {'巡园日期':<12} {'地块':<8} {'品种':<10} {'病害':<8} {'检出数':>6} {'病斑面积':>12} {'面积占比':>8}")
    click.echo("   " + "-" * 70)
    for row in detail:
        la_str = f"{row['lesion_area']:,}" if row['lesion_area'] > 0 else "-"
        click.echo(
            f"   {row['scan_date']:<12} {row['plot_id']:<8} {row['variety']:<10} "
            f"{row['disease']:<8} {row['count']:>6} {la_str:>12} {row['area_pct']:>7.2f}%"
        )


def _print_disease_summary(stats):
    all_disease_stats = stats["all_disease_stats"]
    if not all_disease_stats:
        return

    click.echo("\n" + "-" * 70)
    click.echo("🦠 病害汇总:")
    click.echo(f"   {'病害名称':<10} {'检出数':>6} {'占比':>7} {'平均置信度':>10} {'病斑面积(px²)':>14} {'面积占比':>8}")
    click.echo("   " + "-" * 60)
    total_det = sum(all_disease_stats.values())
    for dname, count in sorted(all_disease_stats.items(), key=lambda x: -x[1]):
        confs = stats["all_confidence"].get(dname, [])
        avg_conf = sum(confs) / len(confs) if confs else 0
        la = stats["disease_lesion_area"].get(dname, 0)
        ia = stats["disease_image_area"].get(dname, 0)
        ratio = count / max(1, total_det) * 100
        area_pct = la / max(1, ia) * 100 if ia > 0 else 0
        area_str = f"{la:,}" if la > 0 else "-"
        pct_str = f"{area_pct:.2f}%" if la > 0 else "-"
        click.echo(f"   {dname:<10} {count:>6} {ratio:>6.1f}% {avg_conf:>9.1%} {area_str:>14} {pct_str:>8}")


def _print_plot_summary(stats):
    plot_stats = stats["plot_stats"]
    if not plot_stats:
        return

    click.echo("\n" + "-" * 70)
    click.echo("🗺️ 地块台账汇总:")
    click.echo(f"   {'地块':<8} {'总图片':>6} {'病害':>6} {'健康':>6} {'发病率':>7} {'病斑面积(px²)':>14} {'面积占比':>8} {'主要病害':<10} {'防治建议摘要':<20}")
    click.echo("   " + "-" * 100)

    for pid in sorted(plot_stats.keys()):
        total_img = stats["plot_total_images"].get(pid, 0)
        disease_img = stats["plot_disease_images"].get(pid, 0)
        healthy_img = stats["plot_healthy_images"].get(pid, 0)
        rate = disease_img / max(1, total_img) * 100
        total_lesion = sum(stats["plot_lesion_area"].get(pid, {}).values())
        total_img_area = stats["plot_image_area"].get(pid, 0)
        area_pct = total_lesion / max(1, total_img_area) * 100 if total_img_area > 0 else 0
        lesion_str = f"{total_lesion:,}" if total_lesion > 0 else "-"
        pct_str = f"{area_pct:.2f}%" if total_lesion > 0 else "-"

        diseases_in_plot = plot_stats[pid]
        if diseases_in_plot:
            primary = max(diseases_in_plot, key=diseases_in_plot.get)
            treatment = get_treatment(primary)
            treatment_brief = treatment[:18] + "…" if len(treatment) > 18 else treatment
        else:
            primary = "-"
            treatment_brief = "-"

        click.echo(
            f"   {pid:<8} {total_img:>6} {disease_img:>6} {healthy_img:>6} "
            f"{rate:>6.1f}% {lesion_str:>14} {pct_str:>8} {primary:<10} {treatment_brief:<20}"
        )

        if diseases_in_plot:
            for dname, count in sorted(diseases_in_plot.items(), key=lambda x: -x[1]):
                la = stats["plot_lesion_area"].get(pid, {}).get(dname, 0)
                la_pct = la / max(1, total_img_area) * 100 if total_img_area > 0 else 0
                la_str = f"{la:,}" if la > 0 else "-"
                click.echo(f"     → {dname}: {count}处  病斑面积={la_str}  占比={la_pct:.2f}%")


def _print_variety_summary(stats):
    variety_stats = stats["variety_stats"]
    if not variety_stats:
        return

    click.echo("\n" + "-" * 70)
    click.echo("🌳 按品种统计:")
    for var in sorted(variety_stats.keys()):
        click.echo(f"   {var}:")
        for dname, count in sorted(variety_stats[var].items(), key=lambda x: -x[1]):
            click.echo(f"     • {dname}: {count} 处")


def _print_priority_watch(watch, config):
    triggered = [w for w in watch if w["triggers"]]
    if not triggered:
        return

    click.echo("\n" + "-" * 70)
    click.echo("🚨 重点巡查地块:")
    click.echo(f"   (预警阈值: 发病率≥{config.alert_incidence_rate}%  面积占比≥{config.alert_area_ratio}%  增长≥{config.alert_growth_rate}%)")
    click.echo()
    for w in triggered:
        click.echo(f"   📍 地块 {w['plot_id']}  品种={w['variety']}")
        click.echo(f"      主要病害: {w['primary_disease']}  发病率={w['incidence_rate']}%  面积占比={w['area_pct']}%  增长={w['growth']:+.1f}%")
        click.echo(f"      触发原因: {'; '.join(w['triggers'])}")
        click.echo(f"      防治建议: {w['treatment']}")
        if w["recheck_date"]:
            click.echo(f"      建议复查日期: {w['recheck_date']}")
        click.echo()


def _print_treatment_list(stats):
    all_disease_stats = stats["all_disease_stats"]
    plot_stats = stats["plot_stats"]
    if not all_disease_stats:
        return

    click.echo("-" * 70)
    click.echo("💊 防治建议清单:")
    click.echo()
    for dname in sorted(all_disease_stats.keys()):
        treatment = get_treatment(dname)
        count = all_disease_stats[dname]
        affected_plots = [pid for pid in plot_stats if dname in plot_stats[pid]]
        la = stats["disease_lesion_area"].get(dname, 0)
        ia = stats["disease_image_area"].get(dname, 0)
        click.echo(f"   【{dname}】检出 {count} 处")
        if affected_plots:
            click.echo(f"     涉及地块: {', '.join(sorted(affected_plots))}")
        if la > 0 and ia > 0:
            click.echo(f"     总病斑面积: {la:,} px²  占比: {la / max(1, ia) * 100:.2f}%")
        click.echo(f"     防治方案: {treatment}")
        click.echo()
