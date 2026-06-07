import click
from . import __version__
from .commands.scan import scan_command
from .commands.label import label_command
from .commands.compare import compare_command
from .commands.report import report_command
from .commands.export import export_command
from .commands.config import config_command


@click.group()
@click.version_option(version=__version__, prog_name="orchard-guard")
def cli():
    """🍎 orchard-guard — 果园病害识别命令行工具

    供农技站人员和合作社技术员批量处理巡园照片，
    识别叶斑、炭疽、腐烂、锈病等疑似病害。

    使用流程:
      1. config  — 配置阈值和默认参数
      2. scan    — 导入图片文件夹，识别病害
      3. label   — 人工修正识别结果
      4. compare — 比较不同日期病害扩散
      5. report  — 生成统计报告和防治建议
      6. export  — 按地块导出表格
    """


cli.add_command(scan_command, "scan")
cli.add_command(label_command, "label")
cli.add_command(compare_command, "compare")
cli.add_command(report_command, "report")
cli.add_command(export_command, "export")
cli.add_command(config_command, "config")


def main():
    cli()


if __name__ == "__main__":
    main()
