import os
import click
from datetime import date
from ..core.models import ScanSession, ImageRecord, DiseaseType
from ..core.image_utils import collect_images, parse_path_info, extract_date_from_path
from ..core.detector import detect_diseases
from ..core.store import save_session, load_config


@click.command("scan")
@click.argument("directory", type=click.Path(exists=True))
@click.option("--variety", "-v", default="", help="果树品种 (如: 红富士、嘎啦)")
@click.option("--plot", "-p", default="", help="地块编号 (如: A1、B3)")
@click.option("--date", "-d", "scan_date", default="", help="巡园日期 (YYYY-MM-DD)")
@click.option(
    "--confidence",
    "-c",
    type=float,
    default=None,
    help="置信度阈值 (0-1)",
)
@click.option(
    "--blur-threshold",
    type=float,
    default=None,
    help="模糊度阈值 (低于此值视为模糊照片)",
)
@click.option(
    "--skip-blurry/--include-blurry",
    default=True,
    help="是否跳过模糊照片的病害检测",
)
@click.option("--store-dir", default="", help="数据存储目录")
def scan_command(
    directory, variety, plot, scan_date, confidence, blur_threshold, skip_blurry, store_dir
):
    """导入图片文件夹，识别病害并归类"""
    config = load_config(store_dir or None)
    conf_thresh = confidence if confidence is not None else config.confidence_threshold
    blur_thresh = blur_threshold if blur_threshold is not None else config.blur_threshold
    effective_variety = variety or config.default_variety
    effective_plot = plot or config.default_plot

    click.echo(f"📂 扫描目录: {directory}")
    image_paths = collect_images(directory)
    if not image_paths:
        click.echo("⚠️  未找到任何图片文件")
        return

    click.echo(f"🖼️  发现 {len(image_paths)} 张图片")

    session = ScanSession(
        source_dir=os.path.abspath(directory),
        variety=effective_variety,
        plot_id=effective_plot,
        scan_date=scan_date or date.today().isoformat(),
        total_images=len(image_paths),
    )

    processed = 0
    blurry_count = 0
    disease_count = 0
    healthy_count = 0

    with click.progressbar(image_paths, label="🔍 识别中") as paths:
        for img_path in paths:
            path_variety, path_plot = parse_path_info(img_path)
            record = ImageRecord(
                file_path=os.path.abspath(img_path),
                file_name=os.path.basename(img_path),
                variety=effective_variety or path_variety,
                plot_id=effective_plot or path_plot,
                scan_date=session.scan_date,
            )

            detected_date = extract_date_from_path(img_path)
            if detected_date and not scan_date:
                record.scan_date = detected_date

            detect_diseases(record, conf_thresh, blur_thresh, skip_blurry)

            if record.is_blurry:
                blurry_count += 1
                if skip_blurry:
                    click.echo(
                        f"\n  ⚠️  模糊照片已跳过: {record.file_name} (模糊度={record.blur_score:.1f})"
                    )

            has_disease = any(
                det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN)
                for det in record.detections
            )
            if has_disease:
                disease_count += 1
            elif record.detections:
                healthy_count += 1

            session.images.append(record)
            processed += 1

    session.blurry_count = blurry_count
    session.disease_count = disease_count
    session.healthy_count = healthy_count

    saved_path = save_session(session, store_dir or None)

    click.echo(f"\n✅ 扫描完成！会话ID: {session.id}")
    click.echo(f"   总计: {session.total_images} 张")
    click.echo(f"   疑似病害: {disease_count} 张")
    click.echo(f"   健康: {healthy_count} 张")
    click.echo(f"   模糊: {blurry_count} 张")
    click.echo(f"   数据已保存: {saved_path}")

    if disease_count > 0:
        click.echo("\n🦠 检测到的病害:")
        disease_summary = {}
        for img in session.images:
            for det in img.detections:
                if det.disease not in (DiseaseType.HEALTHY, DiseaseType.UNKNOWN):
                    name = det.disease.value
                    if name not in disease_summary:
                        disease_summary[name] = {"count": 0, "max_conf": 0.0}
                    disease_summary[name]["count"] += 1
                    disease_summary[name]["max_conf"] = max(
                        disease_summary[name]["max_conf"], det.confidence
                    )
        for dname, info in sorted(disease_summary.items(), key=lambda x: -x[1]["count"]):
            click.echo(f"   • {dname}: {info['count']} 处 (最高置信度={info['max_conf']:.1%})")
