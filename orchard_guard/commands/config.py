import click
from ..core.models import AppConfig
from ..core.store import load_config, save_config, compute_summary, list_sessions


@click.command("config")
@click.option("--confidence", "-c", type=float, default=None, help="设置置信度阈值 (0-1)")
@click.option("--blur-threshold", type=float, default=None, help="设置模糊度阈值")
@click.option("--default-variety", type=str, default=None, help="设置默认果树品种")
@click.option("--default-plot", type=str, default=None, help="设置默认地块编号")
@click.option("--export-format", type=click.Choice(["xlsx", "csv"]), default=None, help="设置默认导出格式")
@click.option("--alert-incidence", type=float, default=None, help="预警: 发病率阈值(%)")
@click.option("--alert-area", type=float, default=None, help="预警: 面积占比阈值(%)")
@click.option("--alert-growth", type=float, default=None, help="预警: 增长幅度阈值(%)")
@click.option("--store-dir", default="", help="数据存储目录")
@click.option("--show", is_flag=True, help="显示当前配置")
@click.option("--summary", is_flag=True, help="打印处理摘要")
@click.option("--reset", is_flag=True, help="恢复默认配置")
def config_command(
    confidence, blur_threshold, default_variety, default_plot,
    export_format, alert_incidence, alert_area, alert_growth,
    store_dir, show, summary, reset
):
    """保存常用阈值，查看配置，打印处理摘要"""

    config = load_config(store_dir or None)

    if reset:
        config = AppConfig(store_dir=config.store_dir)
        save_config(config, store_dir or None)
        click.echo("✅ 已恢复默认配置")
        _show_config(config)
        return

    changed = False
    if confidence is not None:
        config.confidence_threshold = max(0.0, min(1.0, confidence))
        changed = True
        click.echo(f"✅ 置信度阈值已设置为: {config.confidence_threshold}")
    if blur_threshold is not None:
        config.blur_threshold = blur_threshold
        changed = True
        click.echo(f"✅ 模糊度阈值已设置为: {config.blur_threshold}")
    if default_variety is not None:
        config.default_variety = default_variety
        changed = True
        click.echo(f"✅ 默认品种已设置为: {config.default_variety}")
    if default_plot is not None:
        config.default_plot = default_plot
        changed = True
        click.echo(f"✅ 默认地块已设置为: {config.default_plot}")
    if export_format is not None:
        config.export_format = export_format
        changed = True
        click.echo(f"✅ 默认导出格式已设置为: {config.export_format}")
    if alert_incidence is not None:
        config.alert_incidence_rate = alert_incidence
        changed = True
        click.echo(f"✅ 预警发病率阈值已设置为: {config.alert_incidence_rate}%")
    if alert_area is not None:
        config.alert_area_ratio = alert_area
        changed = True
        click.echo(f"✅ 预警面积占比阈值已设置为: {config.alert_area_ratio}%")
    if alert_growth is not None:
        config.alert_growth_rate = alert_growth
        changed = True
        click.echo(f"✅ 预警增长幅度阈值已设置为: {config.alert_growth_rate}%")

    if changed:
        save_config(config, store_dir or None)

    if summary:
        _print_summary(store_dir)

    if show or (not changed and not summary):
        _show_config(config)


def _show_config(config):
    click.echo("\n⚙️  当前配置:")
    click.echo(f"   置信度阈值: {config.confidence_threshold}")
    click.echo(f"   模糊度阈值: {config.blur_threshold}")
    click.echo(f"   默认品种: {config.default_variety or '(未设置)'}")
    click.echo(f"   默认地块: {config.default_plot or '(未设置)'}")
    click.echo(f"   导出格式: {config.export_format}")
    click.echo(f"   数据目录: {config.store_dir}")
    click.echo(f"   预警阈值:")
    click.echo(f"     发病率≥{config.alert_incidence_rate}%")
    click.echo(f"     面积占比≥{config.alert_area_ratio}%")
    click.echo(f"     增长幅度≥{config.alert_growth_rate}%")


def _print_summary(store_dir):
    s = compute_summary(store_dir or None)
    click.echo("\n📊 处理摘要:")
    click.echo(f"   扫描会话总数: {s['total_scans']}")
    click.echo(f"   处理图片总数: {s['total_images']}")
    click.echo(f"   疑似病害图片: {s['total_disease']}")
    click.echo(f"   健康图片: {s['total_healthy']}")
    click.echo(f"   模糊照片: {s['total_blurry']}")
    if s["plots"]:
        click.echo(f"   涉及地块: {', '.join(s['plots'])}")
    if s["varieties"]:
        click.echo(f"   涉及品种: {', '.join(s['varieties'])}")

    if s["total_images"] > 0:
        disease_rate = s["total_disease"] / s["total_images"] * 100
        click.echo(f"   总体发病率: {disease_rate:.1f}%")

    recent = list_sessions(store_dir or None)[:5]
    if recent:
        click.echo("\n   最近扫描:")
        for r in recent:
            click.echo(
                f"     • {r['id']}  {r.get('scan_date', r.get('created_at', '')[:10])}  "
                f"品种={r.get('variety', '-')}  地块={r.get('plot_id', '-')}  "
                f"图片={r.get('total_images', 0)}"
            )
