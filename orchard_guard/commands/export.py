import os
import csv
import click
from collections import defaultdict
from ..core.models import DiseaseType
from ..core.store import (
    load_session,
    list_sessions,
    get_sessions_by_plot,
    filter_images_by_plot,
    load_config,
)


@click.command("export")
@click.option("--session", "-s", "session_id", default="", help="会话ID")
@click.option("--plot", "-p", default="", help="按地块编号导出")
@click.option("--output", "-o", default="", help="输出文件路径")
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["xlsx", "csv"]),
    default=None,
    help="导出格式",
)
@click.option("--store-dir", default="", help="数据存储目录")
def export_command(session_id, plot, output, fmt, store_dir):
    """按地块导出表格"""

    config = load_config(store_dir or None)
    export_fmt = fmt or config.export_format

    sessions = _resolve_sessions(session_id, plot, store_dir)
    if not sessions:
        return

    if not output:
        if plot:
            output = f"果园病害_{plot}.{export_fmt}"
        elif session_id:
            output = f"果园病害_{session_id}.{export_fmt}"
        else:
            output = f"果园病害_全部.{export_fmt}"

    rows = _collect_rows(sessions)

    if export_fmt == "xlsx":
        _export_xlsx(rows, output)
    else:
        _export_csv(rows, output)

    click.echo(f"✅ 已导出 {len(rows)-1} 条记录到: {os.path.abspath(output)}")


def _resolve_sessions(session_id, plot, store_dir):
    if session_id:
        sess = load_session(session_id, store_dir or None)
        if not sess:
            click.echo(f"❌ 未找到会话: {session_id}")
            return []
        sess.recalculate_counts()
        if plot:
            filtered = filter_images_by_plot([sess], plot)
            return filtered if filtered else [sess]
        return [sess]

    if plot:
        sessions = get_sessions_by_plot(plot, store_dir or None)
        for s in sessions:
            s.recalculate_counts()
        sessions = filter_images_by_plot(sessions, plot)
        if not sessions:
            click.echo(f"❌ 未找到地块 {plot} 的记录")
            return []
        return sessions

    sessions_meta = list_sessions(store_dir or None)
    if not sessions_meta:
        click.echo("📭 暂无扫描会话")
        return []
    sessions = []
    for meta in sessions_meta:
        s = load_session(meta["id"], store_dir or None)
        if s:
            s.recalculate_counts()
            sessions.append(s)
    return sessions


def _collect_rows(sessions):
    headers = [
        "会话ID", "巡园日期", "品种", "地块编号", "文件名", "文件路径",
        "图片尺寸", "是否模糊", "模糊度", "病害类型", "置信度", "病斑区域",
        "病斑面积(px²)", "面积占比(%)",
        "是否修正", "原始病害",
    ]
    rows = [headers]

    for sess in sessions:
        for img in sess.images:
            img_area = img.image_area()
            size_str = f"{img.image_width}×{img.image_height}" if img_area > 0 else "-"
            if not img.detections:
                rows.append([
                    sess.id, img.scan_date, img.variety, img.plot_id,
                    img.file_name, img.file_path,
                    size_str,
                    "是" if img.is_blurry else "否", f"{img.blur_score:.1f}",
                    "", "", "", "", "", "", "",
                ])
            for det in img.detections:
                bbox_str = ""
                bbox_area = 0
                area_pct = ""
                if det.bbox:
                    bbox_str = f"({det.bbox.x1},{det.bbox.y1})-({det.bbox.x2},{det.bbox.y2})"
                    bbox_area = det.bbox.area()
                    if img_area > 0:
                        area_pct = f"{bbox_area / img_area * 100:.2f}"
                area_str = str(bbox_area) if bbox_area > 0 else ""
                rows.append([
                    sess.id, img.scan_date, img.variety, img.plot_id,
                    img.file_name, img.file_path,
                    size_str,
                    "是" if img.is_blurry else "否", f"{img.blur_score:.1f}",
                    det.disease.value, f"{det.confidence:.1%}",
                    bbox_str,
                    area_str, area_pct,
                    "是" if det.corrected else "否",
                    det.original_disease.value if det.original_disease else "",
                ])
    return rows


def _export_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)


def _export_xlsx(rows, output_path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    except ImportError:
        click.echo("⚠️  未安装 openpyxl，改用 CSV 格式导出")
        csv_path = output_path.rsplit(".", 1)[0] + ".csv"
        _export_csv(rows, csv_path)
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "病害检测"

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for row_idx, row in enumerate(rows, 1):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")
            if row_idx == 1:
                cell.font = header_font_white
                cell.fill = header_fill

    disease_col = 10
    for row_idx in range(2, len(rows) + 1):
        cell = ws.cell(row=row_idx, column=disease_col)
        val = cell.value
        if val and val not in ("健康", ""):
            cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_length + 4, 40)

    wb.save(output_path)
