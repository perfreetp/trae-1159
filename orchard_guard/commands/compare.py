import click
from collections import defaultdict
from ..core.models import DiseaseType, RiskEvent, RiskStatus
from ..core.detector import get_treatment
from ..core.store import (
    resolve_sessions,
    filter_images_by_plot,
    load_session,
    load_config,
    compute_priority_watch,
    generate_risk_events,
)


@click.command("compare")
@click.option("--plot", "-p", default="", help="地块编号")
@click.option("--from", "from_date", default="", help="起始巡园日期 (YYYY-MM-DD)")
@click.option("--to", "to_date", default="", help="结束巡园日期 (YYYY-MM-DD)")
@click.option("--session1", "-s1", default="", help="第一个会话ID")
@click.option("--session2", "-s2", default="", help="第二个会话ID")
@click.option("--disease", "-d", default="", help="指定病害查看复盘趋势")
@click.option("--store-dir", default="", help="数据存储目录")
def compare_command(plot, from_date, to_date, session1, session2, disease, store_dir):
    """比较不同日期的病害扩散情况"""

    if session1 and session2:
        _compare_two_sessions(session1, session2, plot, store_dir)
        return

    sessions, ok = resolve_sessions(
        plot=plot, from_date=from_date, to_date=to_date, store_dir=store_dir or None
    )
    if not ok or not sessions:
        if plot and from_date and to_date:
            click.echo(f"❌ 地块 {plot} 在 {from_date}~{to_date} 无巡园记录")
        elif plot:
            click.echo(f"❌ 地块 {plot} 无巡园记录")
        elif from_date and to_date:
            click.echo(f"❌ {from_date}~{to_date} 无巡园记录")
        else:
            click.echo("📭 暂无扫描会话")
        return

    if len(sessions) < 2:
        click.echo("⚠️  至少需要2次巡园记录才能对比")
        _list_available(sessions)
        return

    if disease:
        _compare_disease_review(sessions, disease, plot, store_dir)
    else:
        _compare_trend(sessions, plot, store_dir)


def _compare_two_sessions(s1_id, s2_id, plot, store_dir):
    sess1 = load_session(s1_id, store_dir or None)
    sess2 = load_session(s2_id, store_dir or None)
    if not sess1:
        click.echo(f"❌ 未找到会话: {s1_id}")
        return
    if not sess2:
        click.echo(f"❌ 未找到会话: {s2_id}")
        return
    sess1.recalculate_counts()
    sess2.recalculate_counts()

    if plot:
        f1 = filter_images_by_plot([sess1], plot)
        f2 = filter_images_by_plot([sess2], plot)
        if not f1:
            click.echo(f"❌ 会话 {s1_id} 中没有地块 {plot} 的图片")
            return
        if not f2:
            click.echo(f"❌ 会话 {s2_id} 中没有地块 {plot} 的图片")
            return
        sess1, sess2 = f1[0], f2[0]

    click.echo("\n📊 会话对比:")
    click.echo("=" * 70)
    click.echo(f"  会话A: {sess1.id}  巡园日期={sess1.scan_date or sess1.created_at[:10]}")
    click.echo(f"  会话B: {sess2.id}  巡园日期={sess2.scan_date or sess2.created_at[:10]}")
    click.echo("-" * 70)

    stats1 = _compute_disease_stats(sess1)
    stats2 = _compute_disease_stats(sess2)
    all_diseases = sorted(set(list(stats1.keys()) + list(stats2.keys())))

    click.echo(f"\n  {'指标':<14} {'会话A':>8} {'会话B':>8} {'变化':>8}")
    click.echo("  " + "-" * 42)
    for label, v1, v2 in [
        ("总图片", sess1.total_images, sess2.total_images),
        ("病害图片", sess1.disease_count, sess2.disease_count),
        ("健康图片", sess1.healthy_count, sess2.healthy_count),
        ("模糊图片", sess1.blurry_count, sess2.blurry_count),
    ]:
        click.echo(f"  {label:<14} {v1:>8} {v2:>8} {v2-v1:>+8}")

    if all_diseases:
        click.echo(f"\n  🦠 各病害 (含0值):")
        click.echo(f"  {'病害':<10} {'会话A':>6} {'会话B':>6} {'变化':>6}")
        click.echo("  " + "-" * 34)
        for dname in all_diseases:
            c1, c2 = stats1.get(dname, 0), stats2.get(dname, 0)
            delta = c2 - c1
            arrow = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
            click.echo(f"  {dname:<10} {c1:>6} {c2:>6} {delta:>+6} {arrow}")

    rate1 = sess1.disease_count / max(1, sess1.total_images) * 100
    rate2 = sess2.disease_count / max(1, sess2.total_images) * 100
    risk = _assess_risk(rate1, rate2)
    click.echo(f"\n  发病率: {rate1:.1f}% → {rate2:.1f}%  变化={rate2-rate1:+.1f}%  风险等级: {risk}")


def _compare_trend(sessions, plot_filter, store_dir):
    config = load_config(store_dir or None)

    click.echo("\n📊 病害趋势分析")
    click.echo("=" * 70)
    if plot_filter:
        click.echo(f"  地块: {plot_filter}")
    click.echo(f"  巡园次数: {len(sessions)}")
    click.echo()

    all_dates = [s.scan_date or s.created_at[:10] for s in sessions]

    click.echo("  📈 发病率趋势:")
    click.echo(f"  {'巡园日期':<12} {'总图片':>6} {'病害':>6} {'健康':>6} {'发病率':>7}  趋势")
    click.echo("  " + "-" * 60)

    prev_rate = None
    for sess in sessions:
        rate = sess.disease_count / max(1, sess.total_images) * 100
        d = sess.scan_date or sess.created_at[:10]
        bar_len = max(1, int(rate / 2))
        bar = "█" * bar_len

        if prev_rate is not None:
            diff = rate - prev_rate
            arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
            delta_str = f" {arrow}{abs(diff):.1f}%"
        else:
            delta_str = ""

        click.echo(f"  {d:<12} {sess.total_images:>6} {sess.disease_count:>6} {sess.healthy_count:>6} {rate:>6.1f}%  {bar}{delta_str}")
        prev_rate = rate

    first_rate = sessions[0].disease_count / max(1, sessions[0].total_images) * 100
    last_rate = sessions[-1].disease_count / max(1, sessions[-1].total_images) * 100

    raw_disease_trend = defaultdict(dict)
    all_disease_names = set()
    for sess in sessions:
        stats = _compute_disease_stats(sess)
        d = sess.scan_date or sess.created_at[:10]
        for dname, count in stats.items():
            raw_disease_trend[dname][d] = count
            all_disease_names.add(dname)

    for dname in all_disease_names:
        for d in all_dates:
            if d not in raw_disease_trend[dname]:
                raw_disease_trend[dname][d] = 0

    click.echo(f"\n  🦠 各病害变化趋势 (补齐0值):")
    new_diseases = []
    regular_growth = []
    for dname in sorted(all_disease_names):
        points = raw_disease_trend[dname]
        ordered = [points[d] for d in all_dates]
        first_c, last_c = ordered[0], ordered[-1]
        is_new = first_c == 0 and last_c > 0
        if first_c > 0:
            growth = (last_c - first_c) / first_c * 100
        elif last_c > 0:
            growth = float("inf")
        else:
            growth = 0
        trend = "📈上升" if last_c > first_c else ("📉下降" if last_c < first_c else "➡️持平")
        if is_new:
            trend = "🆕从0新增"
        dates_str = " → ".join(f"{d}({points[d]})" for d in all_dates)
        click.echo(f"  • {dname}: {dates_str}  {trend}")
        if is_new:
            new_diseases.append((dname, growth))
        else:
            regular_growth.append((dname, growth))

    fastest_disease = None
    fastest_growth_str = ""
    if new_diseases:
        fastest_disease = new_diseases[0][0]
        fastest_growth_str = "从0新增"
    elif regular_growth:
        best = max(regular_growth, key=lambda x: x[1])
        if best[1] > 0:
            fastest_disease = best[0]
            fastest_growth_str = f"+{best[1]:.0f}%"

    if not plot_filter and len(sessions) >= 2:
        click.echo(f"\n  🗺️ 各地块发病率变化:")
        plot_trend = defaultdict(dict)
        all_plot_ids = set()
        for sess in sessions:
            plot_disease_count = defaultdict(int)
            plot_total = defaultdict(int)
            d = sess.scan_date or sess.created_at[:10]
            for img in sess.images:
                pid = img.plot_id or sess.plot_id or "未知地块"
                plot_total[pid] += 1
                if img.has_disease():
                    plot_disease_count[pid] += 1
                all_plot_ids.add(pid)
            for pid in all_plot_ids:
                total = plot_total.get(pid, 0)
                dis = plot_disease_count.get(pid, 0)
                if total > 0:
                    plot_trend[pid][d] = dis / total * 100
                elif d not in plot_trend[pid]:
                    plot_trend[pid][d] = 0

        for pid in sorted(plot_trend.keys()):
            for d in all_dates:
                if d not in plot_trend[pid]:
                    plot_trend[pid][d] = 0

        fastest_plot = None
        fastest_plot_rate = -999
        for pid in sorted(plot_trend.keys()):
            points = plot_trend[pid]
            rates = [points.get(d, 0) for d in all_dates]
            first_r, last_r = rates[0], rates[-1]
            delta = last_r - first_r
            trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
            dates_str = " → ".join(f"{d}({points.get(d, 0):.0f}%)" for d in all_dates)
            click.echo(f"  • 地块 {pid}: {dates_str}  {trend}")
            if delta > fastest_plot_rate:
                fastest_plot_rate = delta
                fastest_plot = pid

        if fastest_plot:
            click.echo(f"\n  ⚡ 增长最快地块: {fastest_plot} (发病率增加 {fastest_plot_rate:+.1f}%)")

    if fastest_disease:
        click.echo(f"  ⚡ 增长最快病害: {fastest_disease} ({fastest_growth_str})")

    overall_risk = _assess_risk(first_rate, last_rate)
    click.echo(f"\n  🚨 总体风险等级: {overall_risk}")
    if "明显扩散" in overall_risk:
        click.echo("  建议: 立即启动集中防治，重点喷药并清除病源")
    elif "加重" in overall_risk:
        click.echo("  建议: 加强巡查频率，针对高发病地块重点防治")
    elif "轻微" in overall_risk:
        click.echo("  建议: 继续监测，保持常规防治措施")
    else:
        click.echo("  建议: 维持现有防治方案")

    watch = compute_priority_watch(sessions, config)
    risk_events = generate_risk_events(sessions, config, store_dir or None)

    triggered = [w for w in watch if w["triggers"]]
    if triggered:
        click.echo(f"\n  🚨 重点巡查地块 (阈值: 发病率≥{config.alert_incidence_rate}%  面积占比≥{config.alert_area_ratio}%  增长≥{config.alert_growth_rate}%):")
        for w in triggered:
            growth_str = "从0新增" if w.get("is_new_disease") else f"{w['growth']:+.1f}%"
            click.echo(f"  📍 地块 {w['plot_id']}  主要病害={w['primary_disease']}  发病率={w['incidence_rate']}%  增长={growth_str}")
            click.echo(f"     触发: {'; '.join(w['triggers'])}  防治: {w['treatment']}")
            if w["recheck_date"]:
                click.echo(f"     建议复查: {w['recheck_date']}")

    active_risks = [e for e in risk_events if e.status != "已关闭"]
    if active_risks:
        click.echo(f"\n  🚨 风险事件:")
        for ev in sorted(active_risks, key=lambda e: (RiskEvent.status_sort_key(e.status), -e.risk_score)):
            status_icon = {"未处理": "🔴", "已确认": "🟠", "已复查": "🟡"}.get(ev.status, "⚪")
            click.echo(f"  {status_icon} [{ev.id}] 地块 {ev.plot_id} {ev.disease}  状态={ev.status}  触发{ev.trigger_count}次")


def _compare_disease_review(sessions, disease_name, plot_filter, store_dir):
    config = load_config(store_dir or None)

    click.echo(f"\n📊 病害复盘: {disease_name}")
    click.echo("=" * 70)
    if plot_filter:
        click.echo(f"  地块: {plot_filter}")
    click.echo()

    all_dates = [s.scan_date or s.created_at[:10] for s in sessions]

    plot_disease_trend = defaultdict(dict)
    variety_disease_trend = defaultdict(dict)
    all_plot_ids = set()
    all_varieties = set()

    for sess in sessions:
        d = sess.scan_date or sess.created_at[:10]
        plot_counts = defaultdict(int)
        variety_counts = defaultdict(int)

        for img in sess.images:
            pid = img.plot_id or sess.plot_id or "未知地块"
            var = img.variety or sess.variety or "未知品种"
            all_plot_ids.add(pid)
            all_varieties.add(var)

            for det in img.detections:
                if det.disease.value == disease_name:
                    plot_counts[pid] += 1
                    variety_counts[var] += 1

        for pid in all_plot_ids:
            plot_disease_trend[pid][d] = plot_counts.get(pid, 0)
        for var in all_varieties:
            variety_disease_trend[var][d] = variety_counts.get(var, 0)

    for pid in all_plot_ids:
        for d in all_dates:
            if d not in plot_disease_trend[pid]:
                plot_disease_trend[pid][d] = 0
    for var in all_varieties:
        for d in all_dates:
            if d not in variety_disease_trend[var]:
                variety_disease_trend[var][d] = 0

    click.echo("  🗺️ 各地块趋势:")
    click.echo(f"  {'地块':<10} {'趋势':<50} {'结论'}")
    click.echo("  " + "-" * 80)

    for pid in sorted(all_plot_ids):
        points = plot_disease_trend[pid]
        ordered = [points[d] for d in all_dates]
        conclusion = _disease_conclusion(ordered)
        dates_str = " → ".join(f"{d}({points[d]})" for d in all_dates)
        click.echo(f"  {pid:<10} {dates_str:<50} {conclusion}")

    click.echo(f"\n  🌳 各品种趋势:")
    click.echo(f"  {'品种':<10} {'趋势':<50} {'结论'}")
    click.echo("  " + "-" * 80)

    for var in sorted(all_varieties):
        points = variety_disease_trend[var]
        ordered = [points[d] for d in all_dates]
        conclusion = _disease_conclusion(ordered)
        dates_str = " → ".join(f"{d}({points[d]})" for d in all_dates)
        click.echo(f"  {var:<10} {dates_str:<50} {conclusion}")

    treatment = get_treatment(disease_name)
    click.echo(f"\n  💊 {disease_name} 防治方案: {treatment}")

    watch = compute_priority_watch(sessions, config)
    relevant = [w for w in watch if w["primary_disease"] == disease_name and w["triggers"]]
    if relevant:
        click.echo(f"\n  🚨 {disease_name} 相关预警:")
        for w in relevant:
            click.echo(f"     地块 {w['plot_id']}  发病率={w['incidence_rate']}%  增长={w['growth']:+.1f}%  触发: {'; '.join(w['triggers'])}")


def _disease_conclusion(ordered_counts):
    if all(c == 0 for c in ordered_counts):
        return "➡️ 未检出"

    nonzero = [c for c in ordered_counts if c > 0]
    if len(nonzero) == len(ordered_counts):
        if all(c == ordered_counts[0] for c in ordered_counts):
            return "🔴 持续高发"
        if ordered_counts[-1] > ordered_counts[0]:
            return "📈 加重"
        if ordered_counts[-1] < ordered_counts[0]:
            return "📉 持续消退"
        return "➡️ 持平"

    first_nz_idx = next(i for i, c in enumerate(ordered_counts) if c > 0)
    if first_nz_idx > 0:
        has_zero_after = any(c == 0 for c in ordered_counts[first_nz_idx:])
        if has_zero_after:
            return "🔄 复发"
        return "🆕 新增"

    if ordered_counts[-1] == 0:
        return "📉 消退"

    has_zero_between = any(c == 0 for c in ordered_counts[1:-1])
    if has_zero_between:
        return "🔄 复发"

    if ordered_counts[-1] > ordered_counts[0]:
        return "📈 加重"
    if ordered_counts[-1] < ordered_counts[0]:
        return "📉 消退"
    return "➡️ 持平"


def _compute_disease_stats(sess) -> dict:
    stats = defaultdict(int)
    for img in sess.images:
        for det in img.detections:
            if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN):
                stats[det.disease.value] += 1
    return dict(stats)


def _assess_risk(first_rate: float, last_rate: float) -> str:
    delta = last_rate - first_rate
    if delta >= 20:
        return "🔴 明显扩散"
    elif delta >= 10:
        return "🟠 加重"
    elif delta > 0:
        return "🟡 轻微"
    elif delta == 0:
        return "➡️ 持平"
    else:
        return "🟢 减轻"


def _list_available(sessions):
    click.echo("\n可用会话:")
    for i, s in enumerate(sessions):
        click.echo(
            f"  [{i}] ID={s.id}  巡园日期={s.scan_date or s.created_at[:10]}  "
            f"地块={s.plot_id}  图片={s.total_images}"
        )
