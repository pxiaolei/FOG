#!/usr/bin/env python3
"""
按运营主体/城市/品牌拆表工具

拆分逻辑：
- 按运营主体拆：逐 sheet 品牌+城市双条件，不静默回退
- 按城市拆：按城市匹配运营主体，输出运营主体文件
- 按品牌拆：按品牌匹配运营主体，输出运营主体文件
- 纯品牌拆：按品牌独立输出，不映射运营主体

依赖：
- lxx_share.excel_utils（列检测、对接人筛选）
- lx_shujuku（公司库 operator_brand 码表映射）
- openpyxl + pyyaml

使用方法：
  python split_by_zhuti.py                    # 默认只列输入，不查库、不写入
  python split_by_zhuti.py --config --confirmed  # 经授权后重新配置
  python split_by_zhuti.py -m 1 -p 雷维亮 --confirmed  # 经授权后生成、验收并条件归档
"""

import sys
import shutil
import zipfile
import argparse
import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from copy import copy

from openpyxl import load_workbook, Workbook

# 确保 lxx_share / lx_shujuku 可 import（向上查找 skills 目录）
def _find_skills_dir():
    from pathlib import Path
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir() and (p / "lx_shujuku").is_dir():
            return p
    return Path(__file__).resolve().parents[2]

_skills_dir = _find_skills_dir()
import sys
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))
_lx_shujuku_scripts_dir = _skills_dir / "lx_shujuku" / "scripts"
if str(_lx_shujuku_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_lx_shujuku_scripts_dir))

from lxx_share.excel_utils import (
    CITY_FIELDS,
    BRAND_FIELDS,
    PERSON_FIELDS,
    OPERATOR_FIELDS,
    find_column,
)
from lxx_share.fog_config import (
    find_project_root,
    load_fog_config,
    resolve_project_path,
    save_fog_config,
)
from lx_shujuku import create_client, build_mabiao_mapping


# ========================================
# 路径与默认值
# ========================================

SKILL_DIR = Path(__file__).parent.parent
DEFAULT_PERSONS = ["雷维亮"]


# ========================================
# CLI 参数
# ========================================

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="按运营主体/城市/品牌拆表工具")
    parser.add_argument("--mode", "-m", type=int, choices=[1, 2, 3, 4],
                        help="拆分维度: 1=运营主体, 2=城市, 3=品牌→运营主体, 4=纯品牌")
    parser.add_argument("--person", "-p", type=str,
                        help="对接人范围: 'all' 或逗号分隔的对接人列表")
    parser.add_argument("--keep-sheets", "-k", type=str,
                        help="保留的sheet名称，逗号分隔")
    parser.add_argument("--config", action="store_true",
                        help="重新配置")
    parser.add_argument("--confirmed", action="store_true",
                        help="确认生成拆分文件、压缩包、日志并移动原表")
    parser.add_argument("--dry-run", action="store_true",
                        help="只预览，不写文件、不移动原表、不连接公司库；默认行为")
    args = parser.parse_args(argv)
    if args.confirmed and args.dry_run:
        parser.error("--confirmed 和 --dry-run 不能同时使用")
    return args


# ========================================
# 配置管理
# ========================================

def interactive_setup():
    """交互式配置（首次运行）。"""
    print("\n" + "=" * 60)
    print("按运营主体/城市/品牌拆表工具 - 首次配置")
    print("=" * 60)

    print("\n【重要】码表将从公司 dataReporting 的 operator_brand 表读取")
    print("  请先在 config/fog_config.yaml 的 lx_shujuku.api 段填写 dataReporting 账号")
    print("-" * 60)

    print("\n检测到未配置，请提供以下信息：\n")

    # 1. 项目根目录
    current_dir = Path.cwd()
    print(f"1. 项目根目录")
    print(f"   当前目录: {current_dir}")
    user_input = input("   回车使用当前目录，或输入路径: ").strip()
    project_root = Path(user_input) if user_input else current_dir
    project_root = project_root.resolve()

    # 2. 默认对接人
    print(f"\n2. 默认对接人")
    print("   多个对接人用逗号分隔，如: 雷维亮,陈双")
    user_input = input(f"   输入默认对接人（默认: {','.join(DEFAULT_PERSONS)}）: ").strip()
    if user_input:
        default_persons = [p.strip() for p in user_input.split(",")]
    else:
        default_persons = DEFAULT_PERSONS

    # 3. 工作目录
    print(f"\n3. 工作目录")
    print("   目录下需包含: 输入/、输出/、原表存档/")
    user_input = input("   输入工作目录名称（默认: workspace/01主体拆表）: ").strip()
    work_dir_name = user_input if user_input else "workspace/01主体拆表"
    work_dir = project_root / work_dir_name

    # 确认
    print("\n" + "-" * 60)
    print("配置确认:")
    print(f"  项目根目录: {project_root}")
    print("  码表来源: lx_shujuku / operator_brand")
    print(f"  默认对接人: {default_persons}")
    print(f"  工作目录: {work_dir}")
    print("-" * 60)

    user_input = input("\n确认保存配置？(Y/n): ").strip().lower()
    if user_input == 'n':
        print("配置已取消")
        return None

    config = {
        "项目根目录": str(project_root),
        "码表来源": "lx_shujuku.operator_brand",
        "默认对接人": default_persons,
        "工作目录": str(work_dir),
        "默认": {
            "城市字段": CITY_FIELDS,
            "品牌字段": BRAND_FIELDS,
            "处理sheet": [],
        },
        "特定配置": [],
    }

    fog_config = load_fog_config(project_root)
    fog_config.setdefault("project", {})
    fog_config["project"]["root"] = str(project_root)
    fog_config["project"].setdefault("workspace_root", "workspace")
    fog_config.setdefault("lx_zhutichaibiao", {})
    fog_config["lx_zhutichaibiao"].update({
        "work_dir": work_dir_name,
        "default_persons": default_persons,
        "mabiao_source": "lx_shujuku.operator_brand",
        "default": {
            "city_fields": CITY_FIELDS,
            "brand_fields": BRAND_FIELDS,
            "process_sheets": [],
        },
        "special_configs": [],
    })
    config_path = save_fog_config(fog_config, project_root)

    print(f"\n✅ 配置已保存到: {config_path}")
    return build_config_from_fog(fog_config, project_root)


def load_config():
    """加载配置文件。"""
    project_root = find_project_root(Path(__file__))
    fog_config = load_fog_config(project_root)
    if isinstance(fog_config.get("lx_zhutichaibiao"), dict):
        return build_config_from_fog(fog_config, project_root)
    return None


def build_config_from_fog(fog_config, project_root):
    """把 fog_config.yaml 的 lx_zhutichaibiao 段转换为旧脚本内部结构。"""
    zhutichaibiao = fog_config.get("lx_zhutichaibiao", {})
    if not isinstance(zhutichaibiao, dict):
        zhutichaibiao = {}
    default = zhutichaibiao.get("default", {})
    if not isinstance(default, dict):
        default = {}

    work_dir = resolve_project_path(
        zhutichaibiao.get("work_dir"),
        project_root,
        default="workspace/01主体拆表",
    )
    return {
        "项目根目录": str(project_root),
        "码表来源": zhutichaibiao.get("mabiao_source", "lx_shujuku.operator_brand"),
        "默认对接人": zhutichaibiao.get("default_persons", []),
        "工作目录": str(work_dir),
        "默认": {
            "城市字段": default.get("city_fields") or default.get("城市字段") or CITY_FIELDS,
            "品牌字段": default.get("brand_fields") or default.get("品牌字段") or BRAND_FIELDS,
            "处理sheet": default.get("process_sheets") or default.get("处理sheet") or [],
            "表头行数": default.get("header_rows") or default.get("表头行数") or {},
        },
        "特定配置": zhutichaibiao.get("special_configs") or zhutichaibiao.get("特定配置") or [],
    }


def load_company_mabiao():
    """Use the existing audited reader; a limited response is not a full map."""
    client = create_client()
    columns = client.schema.columns('operator_brand')
    fields = ['operator_entity', 'brand_name', 'city_name', 'contact_person',
              'is_opening', 'open_city_date']
    available = {c['field'] for c in columns}
    keys = [c['field'] for c in columns if c.get('key') == 'PRI']
    if not keys or not set(fields).issubset(available):
        raise RuntimeError('码表缺必要字段或稳定主键，停止交付')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) for k in keys):
        raise RuntimeError('码表排序字段不合法')
    selected = list(dict.fromkeys(keys + fields))
    sql = f"SELECT {', '.join(selected)} FROM operator_brand ORDER BY {', '.join(keys)}"
    result = client.execute_full_audited(sql, page_size=min(500, client.max_limit))
    rows = result.get('rows', [])
    verification = result.get('verification', {})
    counts = [result.get('row_count'), result.get('returned_rows'), result.get('total_rows'),
              verification.get('count_before'), verification.get('count_after')]
    if (result.get('is_complete') is not True or result.get('possible_truncation') is not False
            or verification.get('passed') is not True or any(n != len(rows) for n in counts)):
        raise RuntimeError('码表完整性验证失败，停止交付')
    mapping = build_mabiao_mapping(rows)
    if len(mapping['operator_brand_rows']) != len(rows):
        raise RuntimeError('码表存在缺主体或城市的关系，停止交付')
    mapping['_query_audit'] = {'is_complete': True, 'possible_truncation': False,
                               'row_count': len(rows), 'result_sha256': result.get('result_sha256'),
                               'verification': verification, 'warnings': result.get('warnings', [])}
    return mapping


def get_file_config(config, filename):
    """根据文件名获取配置。"""
    default = config.get("默认", {
        "城市字段": CITY_FIELDS,
        "品牌字段": BRAND_FIELDS,
        "处理sheet": [],
        "表头行数": {},
    })

    for cfg in config.get("特定配置", []):
        if cfg.get("匹配") and cfg["匹配"] in filename:
            result = default.copy()
            result.update(cfg)
            return result

    return default


# ========================================
# 核心拆分逻辑
# ========================================

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_name(value):
    name = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', '_', str(value)).strip(' .')
    if not name:
        raise RuntimeError('文件或接收人名称为空')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'} | {
            f'{kind}{n}' for kind in ('COM', 'LPT') for n in range(1, 10)}:
        name = '_' + name
    return name


def cell_snapshot(cell):
    return {'value': cell.value, 'font': copy(cell.font), 'border': copy(cell.border),
            'fill': copy(cell.fill), 'alignment': copy(cell.alignment),
            'number_format': cell.number_format}


def resolve_persons(mapping, target_persons):
    rows = mapping.get('operator_brand_rows')
    proof = mapping.get('_query_audit', {})
    if (not rows or proof.get('is_complete') is not True
            or proof.get('possible_truncation') is not False or proof.get('row_count') != len(rows)):
        raise RuntimeError('缺完整精确码表及其审计证明，停止按人交付')
    available = {str(r.get('contact_person') or '').strip() for r in rows} - {''}
    if target_persons == '全部':
        persons = sorted(available)
    else:
        values = target_persons.split(',') if isinstance(target_persons, str) else target_persons
        persons = sorted({str(p).strip() for p in values if str(p).strip()})
    if not persons or set(persons) - available:
        raise RuntimeError('对接人为空或不在当前完整码表中')
    names = [safe_name(p).casefold() for p in persons]
    if len(names) != len(set(names)):
        raise RuntimeError('对接人名称转换后冲突')
    return persons


def process_file_optimized(file_path, mapping, file_config, split_mode, col_info=None,
                           person_list=None):
    """Parse once; retain source identities and contact-level output relations."""
    file_path = Path(file_path)
    if file_path.is_symlink():
        raise RuntimeError('源表不能是符号链接')
    persons = resolve_persons(mapping, person_list or '全部')
    rows = mapping['operator_brand_rows']
    # Identical mapping rows must not duplicate the same source-target relation.
    relations = {tuple(str(r.get(k) or '').strip() for k in
                       ('operator', 'brand', 'city', 'contact_person')) for r in rows}
    source_hash = file_hash(file_path)
    plan = {'source': file_path, 'source_sha256': source_hash, 'mode': split_mode,
            'sheets': {}, 'groups': defaultdict(lambda: defaultdict(list)),
            'classifications': [], 'excluded_sheets': [], 'excluded_rows': [],
            'unmatched': defaultdict(list),
            'counts': {'source': 0, 'target': 0, 'filtered': 0, 'unmatched': 0,
                       'expected_relations': 0, 'actual_relations': 0}}
    wb = load_workbook(file_path, data_only=False, keep_links=False)
    try:
        selected = file_config.get('处理sheet', [])
        keep = set(file_config.get('保留 sheet', []))
        unknown = (keep | set(selected)) - set(wb.sheetnames)
        if unknown:
            raise RuntimeError('指定的 sheet 不存在: ' + ', '.join(sorted(unknown)))
        for ws in wb:
            reason = ('保留sheet仅本地' if ws.title in keep else
                      '隐藏sheet' if ws.sheet_state != 'visible' else
                      '非选择sheet' if selected and ws.title not in selected else None)
            if reason:
                plan['excluded_sheets'].append({'sheet': ws.title, 'reason': reason})
                continue
            header_rows = file_config.get('表头行数', {}).get(ws.title)
            city_fields = file_config.get('城市字段', CITY_FIELDS)
            brand_fields = file_config.get('品牌字段', BRAND_FIELDS)
            if header_rows is None:
                header_rows = max([1] + [c.row for row in ws.iter_rows(
                    max_row=min(5, ws.max_row)) for c in row
                    if str(c.value or '').strip() in set(city_fields) | set(brand_fields)])
            if not isinstance(header_rows, int) or header_rows < 1 or header_rows > ws.max_row:
                raise RuntimeError(f'{ws.title}: 表头行数不合法')
            columns = {}
            for kind, names in [('city', city_fields), ('brand', brand_fields)]:
                positions = {c.column for row in ws.iter_rows(max_row=header_rows) for c in row
                             if str(c.value or '').strip() in names}
                if len(positions) > 1:
                    raise RuntimeError(f'{ws.title}: {kind} 列有歧义')
                columns[kind] = next(iter(positions), None)
            required = {'运营主体': ('city', 'brand'), '城市': ('city',),
                        '品牌': ('brand',), '纯品牌': ('brand',)}[split_mode]
            if any(columns[k] is None for k in required):
                raise RuntimeError(f'{ws.title}: 缺少所选模式必要列，禁止静默回退')
            headers = [[cell_snapshot(c) for c in row] for row in ws.iter_rows(max_row=header_rows)]
            if any(c['value'] is not None and str(c['value']).startswith('=')
                   for row in headers for c in row):
                raise RuntimeError(f'{ws.title}: 表头公式无法保证交付正确')
            merges = [str(m) for m in ws.merged_cells.ranges if m.max_row <= header_rows]
            if any(m.min_row <= header_rows < m.max_row for m in ws.merged_cells.ranges):
                raise RuntimeError(f'{ws.title}: 合并单元格跨表头与数据范围')
            if any(m.min_row > header_rows for m in ws.merged_cells.ranges):
                raise RuntimeError(f'{ws.title}: 数据区合并单元格无法保证拆分后格式')
            plan['sheets'][ws.title] = {'headers': headers, 'header_rows': header_rows,
                                      'widths': {k: d.width for k, d in ws.column_dimensions.items()},
                                      'merges': merges}
            plan['excluded_rows'].append({'sheet': ws.title, 'rows': [1, header_rows],
                                          'reason': 'header'})
            for row in ws.iter_rows(min_row=header_rows + 1):
                values = tuple(c.value for c in row)
                if all(v is None or isinstance(v, str) and not v.strip() for v in values):
                    plan['excluded_rows'].append({'sheet': ws.title,
                                                  'rows': [row[0].row, row[0].row],
                                                  'reason': 'blank'})
                    continue
                city = str(values[columns['city'] - 1] or '').strip() if columns['city'] else ''
                brand = str(values[columns['brand'] - 1] or '').strip() if columns['brand'] else ''
                if city.startswith('=') or brand.startswith('='):
                    raise RuntimeError(f'{ws.title}: 范围字段包含公式')
                identity = (source_hash, ws.title, row[0].row)
                if split_mode == '纯品牌':
                    candidates = {(None, brand)} if brand else set()
                    matched = bool(candidates)
                else:
                    matches = {(p, op) for op, b, c, p in relations
                               if (not columns['city'] or city and c == city)
                               and (not columns['brand'] or brand and b == brand)}
                    if any(not p for p, _op in matches):
                        raise RuntimeError(f'{ws.title}: 匹配码表缺少对接人归属')
                    matched = bool(matches)
                    candidates = {(p, op) for p, op in matches if p in persons}
                category = 'target' if candidates else 'filtered' if matched else 'unmatched'
                plan['counts']['source'] += 1
                plan['counts'][category] += 1
                plan['classifications'].append({'source_row': identity, 'category': category,
                                                'targets': sorted(candidates, key=str)})
                if category == 'unmatched':
                    plan['unmatched'][ws.title].append(
                        (values, brand, city, '必要范围为空或完整码表中无匹配关系'))
                if candidates:
                    if any(c.data_type == 'f' for c in row):
                        raise RuntimeError(f'{ws.title}: 数据公式无法保证拆分后的引用，停止该文件')
                    record = {'identity': identity, 'values': values,
                              'styles': [cell_snapshot(c) for c in row]}
                    for target in sorted(candidates, key=str):
                        plan['groups'][target][ws.title].append(record)
                        plan['counts']['expected_relations'] += 1
        if not plan['sheets']:
            raise RuntimeError('没有可拆分的数据 sheet')
        # Fail on unsafe/colliding output names before creating any formal output.
        paths = [(safe_name(owner or '管理端').casefold(), safe_name(op).casefold())
                 for owner, op in plan['groups']]
        if len(paths) != len(set(paths)):
            raise RuntimeError('输出名称转换后冲突')
        if file_hash(file_path) != source_hash:
            raise RuntimeError('解析期间源文件发生变化')
        return plan
    finally:
        wb.close()


def write_delivery_files(plan, task_dir):
    files = {}
    for target, sheets in sorted(plan['groups'].items(), key=lambda item: str(item[0])):
        person, operator = target
        directory = task_dir / '工作文件' / safe_name(person or '管理端')
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / (safe_name(operator) + '.xlsx')
        if output.exists():
            raise RuntimeError('输出文件冲突')
        wb = Workbook()
        wb.remove(wb.active)
        try:
            for name, records in sheets.items():
                ws = wb.create_sheet(name)
                info = plan['sheets'][name]
                all_rows = info['headers'] + [r['styles'] for r in records]
                for row_number, cells in enumerate(all_rows, 1):
                    for column, data in enumerate(cells, 1):
                        cell = ws.cell(row_number, column, data['value'])
                        for attr in ('font', 'border', 'fill', 'alignment', 'number_format'):
                            setattr(cell, attr, copy(data[attr]))
                for column, width in info['widths'].items():
                    ws.column_dimensions[column].width = width
                for merged in info['merges']:
                    ws.merge_cells(merged)
            wb.save(output)
        finally:
            wb.close()
        files[target] = output
    return files


def verify_workbook(plan, target, source):
    wb = load_workbook(source, data_only=False, keep_links=False)
    try:
        expected = plan['groups'][target]
        if set(wb.sheetnames) != set(expected):
            raise RuntimeError('工作簿含多余或缺失 sheet')
        count = 0
        for name, records in expected.items():
            ws = wb[name]
            info = plan['sheets'][name]
            header = [tuple(c['value'] for c in row) for row in info['headers']]
            want = header + [r['values'] for r in records]
            actual = list(ws.iter_rows(values_only=True))
            normalize = lambda row: tuple(None if v == '' else v for v in row)
            if list(map(normalize, actual)) != list(map(normalize, want)):
                raise RuntimeError('实际文件内容、行数或表头与源行关系不一致')
            expected_styles = info['headers'] + [r['styles'] for r in records]
            for row, expected_cells in zip(ws.iter_rows(), expected_styles):
                for cell, data in zip(row, expected_cells):
                    if cell.__class__.__name__ == 'MergedCell':
                        continue
                    if any(copy(getattr(cell, attr)) != data[attr]
                           for attr in ('font', 'border', 'fill', 'alignment', 'number_format')):
                        raise RuntimeError('实际样式与源表不一致')
            for column, width in info['widths'].items():
                if ws.column_dimensions[column].width != width:
                    raise RuntimeError('实际列宽不一致')
            if {str(m) for m in ws.merged_cells.ranges} != set(info['merges']):
                raise RuntimeError('实际表头合并不一致')
            count += len(records)
        return count
    finally:
        wb.close()


def pack_results(plan, files, task_dir):
    """Package each recipient separately; never include source or kept sheets."""
    import io
    by_person = defaultdict(dict)
    for target, path in files.items():
        person, _operator = target
        by_person[person][path.name] = (target, path)
    packages = []
    actual = 0
    for person, members in sorted(by_person.items(), key=lambda item: str(item[0])):
        folder = task_dir / ('交付包' if person is not None else '本地品牌包')
        folder.mkdir(exist_ok=True)
        package = folder / (safe_name(person) + '.zip' if person is not None else 'local-brand.zip')
        for target, path in members.values():
            verify_workbook(plan, target, path)
        with zipfile.ZipFile(package, 'x', zipfile.ZIP_DEFLATED) as zf:
            for name, (_target, path) in sorted(members.items()):
                zf.write(path, name)
        with zipfile.ZipFile(package) as zf:
            if zf.testzip() is not None or len(zf.namelist()) != len(members) or set(
                    zf.namelist()) != set(members):
                raise RuntimeError('ZIP 成员或结构不正确')
            for name, (target, _path) in members.items():
                actual += verify_workbook(plan, target, io.BytesIO(zf.read(name)))
        packages.append(package)
    plan['counts']['actual_relations'] = actual
    if actual != plan['counts']['expected_relations']:
        raise RuntimeError('输出关系遗漏或重复')
    return packages

def output_unmatch_report(unmatch_data, file_path, output_dir, header_info):
    """输出未匹配数据报告。"""
    if not unmatch_data:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_name = f"{timestamp}_{file_path.stem}_未匹配.xlsx"
    report_path = output_dir / report_name

    try:
        wb = Workbook()
        wb.remove(wb.active)
        total_rows = 0

        for sheet_name, rows in unmatch_data.items():
            if not rows:
                continue

            ws = wb.create_sheet(title=sheet_name[:31])
            h_info = header_info.get(sheet_name, {})
            header_rows_count = h_info.get('header_rows', 1)

            if h_info.get('rows'):
                orig_col_count = 0
                for row_idx, row_data in enumerate(h_info['rows'], 1):
                    for col_idx, value in enumerate(row_data, 1):
                        ws.cell(row=row_idx, column=col_idx, value=value)
                    orig_col_count = max(orig_col_count, len(row_data))
                ws.cell(row=header_rows_count, column=orig_col_count + 1, value="品牌")
                ws.cell(row=header_rows_count, column=orig_col_count + 2, value="城市")
                ws.cell(row=header_rows_count, column=orig_col_count + 3, value="未匹配原因")
            else:
                if rows:
                    orig_col_count = len(rows[0][0])
                    for i in range(1, orig_col_count + 1):
                        ws.cell(row=1, column=i, value=f"列{i}")
                    ws.cell(row=1, column=orig_col_count + 1, value="品牌")
                    ws.cell(row=1, column=orig_col_count + 2, value="城市")
                    ws.cell(row=1, column=orig_col_count + 3, value="未匹配原因")
                    header_rows_count = 1

            start_row = header_rows_count + 1
            for row_data, brand, city, reason in rows:
                orig_col_count = len(row_data)
                for col_idx, value in enumerate(row_data, 1):
                    ws.cell(row=start_row, column=col_idx, value=value)
                ws.cell(row=start_row, column=orig_col_count + 1, value=brand)
                ws.cell(row=start_row, column=orig_col_count + 2, value=city)
                ws.cell(row=start_row, column=orig_col_count + 3, value=reason)
                start_row += 1
                total_rows += 1

        wb.save(report_path)
        wb.close()

        print(f"  未匹配报告: {report_name} ({total_rows}行)")
        return report_path

    except Exception as e:
        print(f"  ⚠️ 未匹配报告生成失败: {e}")
        try:
            wb.close()
        except Exception:
            pass
        return None


def run_file(file_path, mapping, file_config, split_mode, persons, work_dir):
    plan = process_file_optimized(file_path, mapping, file_config, split_mode,
                                  person_list=persons)
    task_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid.uuid4().hex[:8]
    task_dir = work_dir / '输出' / task_id
    task_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    archive_path = None
    phase = 'write'
    try:
        files = write_delivery_files(plan, task_dir)
        phase = 'verify_and_pack'
        packages = pack_results(plan, files, task_dir)
        counts = plan['counts']
        if counts['source'] != counts['target'] + counts['filtered'] + counts['unmatched']:
            raise RuntimeError('源行分类不闭合')
        phase = 'report'
        if plan['unmatched']:
            headers = {name: {'rows': [[c['value'] for c in row] for row in info['headers']],
                              'header_rows': info['header_rows']}
                       for name, info in plan['sheets'].items()}
            if not output_unmatch_report(plan['unmatched'], file_path, task_dir, headers):
                raise RuntimeError('未匹配报告写入失败')
        complete = bool(files) and not plan['excluded_sheets'] and counts['unmatched'] == 0
        audit = {'source_name': file_path.name, 'source_sha256': plan['source_sha256'],
                 'mode': split_mode, 'complete': complete, 'counts': counts,
                 'excluded_sheets': plan['excluded_sheets'],
                 'excluded_rows': plan['excluded_rows'],
                 'source_rows': plan['classifications'],
                 'packages': [str(p.relative_to(task_dir)) for p in packages],
                 'delivery_scope': 'local-only' if split_mode == '纯品牌' else 'contact',
                 'archive_status': 'planned' if complete else 'retained',
                 'mapping_audit': mapping['_query_audit']}
        with (task_dir / 'audit.json').open('x', encoding='utf-8') as out:
            json.dump(audit, out, ensure_ascii=False, indent=2, default=str)
        entry = {'file_path': file_path, 'zip_path': None, 'archive_path': None,
                 'stats': {str(k): sum(len(r) for r in v.values())
                           for k, v in plan['groups'].items()},
                 'unmatch_count': counts['unmatched'], 'counts': counts,
                 'packages': audit['packages'], 'complete': complete}
        log_path = write_processing_log(work_dir / '处理日志' / task_id,
                                        [entry], split_mode, persons, persons)
        if not log_path or not Path(log_path).is_file():
            raise RuntimeError('处理日志未完成')
        if file_hash(file_path) != plan['source_sha256']:
            raise RuntimeError('验收后源文件发生变化，不归档或交付')
        phase = 'archive'
        if complete:
            archive_dir = work_dir / '原表存档' / task_id
            archive_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
            archive_path = archive_dir / file_path.name
            if archive_path.exists() or archive_path.is_symlink():
                raise RuntimeError('归档目标冲突，禁止覆盖')
            shutil.move(str(file_path), str(archive_path))
            if file_hash(archive_path) != plan['source_sha256']:
                raise RuntimeError('归档原件哈希不一致')
        phase = 'receipt'
        receipt = {'status': 'ready' if packages else 'no-target-data',
                   'complete': complete, 'delivery_scope': audit['delivery_scope'],
                   'packages': audit['packages'], 'counts': counts,
                   'source_retained': file_path.exists(),
                   'archive': str(archive_path.relative_to(work_dir)) if archive_path else None,
                   'source_sha256': plan['source_sha256']}
        with (task_dir / 'ready.json').open('x', encoding='utf-8') as out:
            json.dump(receipt, out, ensure_ascii=False, indent=2)
        print(f"任务: {task_id}；源行 {counts['source']}；目标 {counts['target']}；"
              f"其他人过滤 {counts['filtered']}；未匹配 {counts['unmatched']}；"
              f"展开 {counts['actual_relations']}；包数 {len(packages)}；"
              f"整表完成 {complete}；仅本地品牌 {split_mode == '纯品牌'}")
        return receipt
    except Exception as exc:
        failure = {'status': 'failed', 'phase': phase, 'source_present': file_path.exists(),
                   'archive_present': bool(archive_path and archive_path.exists()),
                   'archive': str(archive_path.relative_to(work_dir)) if archive_path else None}
        try:
            with (task_dir / 'failure.json').open('x', encoding='utf-8') as out:
                json.dump(failure, out, ensure_ascii=False, indent=2)
        except OSError:
            pass
        raise RuntimeError(f'阶段 {phase} 失败，保留现场；源存在={failure["source_present"]}，'
                           f'归档存在={failure["archive_present"]}；{exc}') from exc


def write_processing_log(log_dir, log_entries, split_mode, person_list, default_persons):
    """在处理日志文件夹写入 Markdown 格式的拆分日志。

    Args:
        log_dir: 处理日志目录（Path 对象）
        log_entries: [{'file_path', 'zip_path', 'archive_path', 'stats', 'unmatch_count'}, ...]
        split_mode: 拆分模式名称
        person_list: 对接人列表或 '全部'
        default_persons: 默认对接人列表
    """
    log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_name = f"{timestamp}_lx-zhutichaibiao_处理日志.md"
    log_path = log_dir / log_name

    total_rows = 0
    total_files = 0
    total_unmatch = 0

    lines = []
    lines.append(f"# lx-zhutichaibiao 拆分处理日志")
    lines.append(f"")
    lines.append(f"**处理时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**拆分模式**: {split_mode}")
    lines.append(f"**对接人**: {person_list if isinstance(person_list, str) else ', '.join(person_list)}")
    lines.append(f"**处理文件数**: {len(log_entries)}")
    lines.append(f"")

    for i, entry in enumerate(log_entries, 1):
        fp = entry['file_path']
        stats = entry.get('stats', {})
        unmatch_count = entry.get('unmatch_count', 0)
        file_rows = sum(stats.values())

        total_rows += file_rows
        total_files += len(stats)
        total_unmatch += unmatch_count

        lines.append(f"## 文件 {i}: {fp.name}")
        lines.append(f"")
        lines.append(f"- **输出 ZIP**: {entry['zip_path'].name if entry['zip_path'] else 'N/A'}")
        lines.append(f"- **原表存档**: {entry['archive_path'].name if entry['archive_path'] else 'N/A'}")
        lines.append(f"- **数据工作簿数（接收人+主体/品牌）**: {len(stats)}")
        lines.append(f"- **展开输出关系行数**: {file_rows}")
        lines.append(f"- **未匹配行**: {unmatch_count}")
        if entry.get('counts'):
            lines.append(f"- **源行分类与展开关系**: {entry['counts']}")
            lines.append(f"- **任务目录内包路径**: {entry['packages']}")
            lines.append(f"- **整表完成**: {entry['complete']}；归档实际结果见任务 ready.json/failure.json")
        lines.append(f"")

        if stats:
            lines.append(f"### 各主体行数")
            lines.append(f"")
            lines.append(f"| 运营主体/品牌 | 数据行数 |")
            lines.append(f"|-------------|---------|")
            for operator, row_count in sorted(stats.items(), key=lambda x: -x[1]):
                lines.append(f"| {operator} | {row_count} |")
            lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 汇总")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 处理文件数 | {len(log_entries)} |")
    lines.append(f"| 生成主体/品牌文件 | {total_files} |")
    lines.append(f"| 展开输出关系行数（不等于源行数） | {total_rows} |")
    lines.append(f"| 未匹配总行数 | {total_unmatch} |")
    lines.append(f"")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n处理日志: {log_path.relative_to(log_dir.parent)}")
    return log_path


# ========================================
# 主函数
# ========================================

def main(argv=None):
    print("=" * 60)
    print("按运营主体/城市/品牌拆表工具（独立版）")
    print("=" * 60)

    args = parse_args(argv)
    force_config = args.config
    config = load_config()

    if not args.confirmed:
        if force_config:
            print("\n预览模式不会修改配置；确认重新配置需追加 --confirmed。")
        if not config:
            print("\n未找到 lx_zhutichaibiao 配置。预览模式不会创建配置或目录。")
            return 0
        work_dir = Path(config["工作目录"])
        todo_dir = work_dir / "输入"
        todo_files = (
            sorted(todo_dir.glob("*.xlsx")) + sorted(todo_dir.glob("*.xlsm"))
            if todo_dir.is_dir()
            else []
        )
        print("\n预览模式：未连接公司库，未创建目录，未生成/压缩文件，未移动原表。")
        print(f"工作目录: {work_dir}")
        print(f"待拆目录存在: {todo_dir.is_dir()}")
        print(f"检测到 Excel 文件: {len(todo_files)}")
        for file_path in todo_files:
            print(f"  - {file_path.name}")
        print("确认输入和目标后追加 --confirmed 执行。")
        return 0

    if not config or force_config:
        config = interactive_setup()
        if not config:
            return

    work_dir = Path(config["工作目录"])
    if any((work_dir / name).is_symlink() for name in ('输入', '输出', '处理日志', '原表存档')):
        print('工作目录入口不能是符号链接')
        return 1
    todo_dir = work_dir / '输入'
    todo_files = sorted(todo_dir.glob('*.xlsx')) + sorted(todo_dir.glob('*.xlsm'))
    if not todo_files:
        print('没有待拆文件')
        return 0
    default_persons = config.get('默认对接人', DEFAULT_PERSONS)
    mode = args.mode
    if mode is None:
        mode = int(input('拆分维度（1=运营主体，2=城市，3=品牌→主体，4=纯品牌）: ').strip() or '1')
    split_mode = {1: '运营主体', 2: '城市', 3: '品牌', 4: '纯品牌'}[mode]
    requested = args.person
    if requested is None:
        requested = input('对接人（中文全名逗号分隔/all，回车用默认）: ').strip()
        requested = requested or default_persons
    target = '全部' if isinstance(requested, str) and requested.lower() == 'all' else requested
    try:
        mapping = load_company_mabiao()
        persons = resolve_persons(mapping, target)
    except Exception as exc:
        print(f'码表或接收人核验失败: {exc}')
        return 1
    failed = False
    for file_path in todo_files:
        file_config = dict(get_file_config(config, file_path.name))
        if args.keep_sheets is not None:
            file_config['保留 sheet'] = [s.strip() for s in args.keep_sheets.split(',') if s.strip()]
        try:
            run_file(file_path, mapping, file_config, split_mode, persons, work_dir)
        except Exception as exc:
            failed = True
            print(f'{file_path.name}: 未完成，{exc}')
    print('部分任务失败，勿全批重跑' if failed else '本地任务结束；按 ready.json 区分可交付与仅本地、整表与部分范围')
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
