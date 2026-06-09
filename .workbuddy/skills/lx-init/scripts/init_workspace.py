"""初始化 FOG workspace 目录。"""

from __future__ import annotations

from pathlib import Path

from utils import WriteResult, resolve_project_path


DEFAULT_DIRS = [
    "workspace/01主体拆表",
    "workspace/01主体拆表/输入",
    "workspace/01主体拆表/输出",
    "workspace/01主体拆表/原表存档",
    "workspace/01主体拆表/处理日志",
    "workspace/03数据报表/日报",
    "workspace/03数据报表/周报",
    "workspace/03数据报表/月报",
    "workspace/03数据报表/其他",
    "workspace/04数据分析",
]


def workspace_dirs(config: dict, project_root: Path) -> list[Path]:
    """根据配置返回需要创建的 workspace 目录。"""
    dirs = [resolve_project_path(project_root, value) for value in DEFAULT_DIRS]
    zhutichaibiao = config.get("lx_zhutichaibiao", {})
    work_dir = zhutichaibiao.get("work_dir")
    if work_dir:
        base = resolve_project_path(project_root, work_dir)
        dirs.extend([
            base,
            base / "输入",
            base / "输出",
            base / "原表存档",
            base / "处理日志",
        ])
    if config.get("enabled_skills", {}).get("lx_dapanribao"):
        dailyreport = config.get("lx_dapanribao", {})
        output_dir = dailyreport.get("output_dir", "workspace/03数据报表/日报")
        dirs.append(resolve_project_path(project_root, output_dir))
    if config.get("enabled_skills", {}).get("lx_haibao"):
        haibao = config.get("lx_haibao", {})
        for key, default in (
            ("output_dir", "workspace/09端外海报图/产出图"),
            ("meta_dir", "workspace/09端外海报图/元数据"),
            ("tmp_dir", "workspace/09端外海报图/临时图"),
        ):
            dirs.append(resolve_project_path(project_root, haibao.get(key, default)))
    unique: list[Path] = []
    seen = set()
    for path in dirs:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def init_workspace(config: dict, project_root: Path, dry_run: bool = False) -> list[WriteResult]:
    """创建 workspace 目录和 .gitkeep。"""
    results: list[WriteResult] = []
    for path in workspace_dirs(config, project_root):
        gitkeep = path / ".gitkeep"
        if dry_run:
            results.append(WriteResult(path=path, action="dry-run", message="预览创建目录"))
            continue
        path.mkdir(parents=True, exist_ok=True)
        gitkeep.touch(exist_ok=True)
        results.append(WriteResult(path=path, action="created", message="目录已存在或已创建"))
    return results
