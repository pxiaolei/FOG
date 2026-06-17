"""
通用工具模块

提供：
- setup_skills_path: 统一的 sys.path 初始化
- get_logger: 日志记录器
- Config: 配置管理
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


def setup_skills_path(caller_file: str) -> Path:
    """
    将 skills 目录添加到 sys.path，返回 skills 目录的 Path 对象。

    由于此函数本身位于 lxx_share 包内，调用前需要先将 lxx_share 所在目录
    加入 sys.path。因此各 Skill 脚本通常使用内联的 _find_skills_dir() 函数
    （逻辑与此函数相同），而非导入此函数。

    内联模板（复制到各脚本头部）：

        def _find_skills_dir():
            from pathlib import Path
            for p in Path(__file__).resolve().parents:
                if (p / "lxx_share").is_dir():
                    return p
            return Path(__file__).resolve().parents[2]

        _skills_dir = _find_skills_dir()
        import sys
        if str(_skills_dir) not in sys.path:
            sys.path.insert(0, str(_skills_dir))

    Args:
        caller_file: 调用者的 __file__，用于定位 skills 目录

    Returns:
        skills 目录的 Path 对象
    """
    # 从调用者向上查找包含 lxx_share/ 子目录的父目录
    current = Path(caller_file).resolve()
    for parent in current.parents:
        if (parent / "lxx_share").is_dir():
            skills_dir = parent
            if str(skills_dir) not in sys.path:
                sys.path.insert(0, str(skills_dir))
            return skills_dir
    # 回退：假定 skills 目录是 caller 的 parents[2]
    skills_dir = current.parents[2]
    if str(skills_dir) not in sys.path:
        sys.path.insert(0, str(skills_dir))
    return skills_dir


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: logger 名称，通常用 __name__

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))

    return logger


class Config:
    """
    配置管理类

    读取项目根目录 config/fog_config.yaml 的 database 段。
    如果共享配置中的 database 为空，则使用本地 config/personal_config.yaml 的 database 段。
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置

        Args:
            config_file: 配置文件路径，默认使用项目根目录的 config/fog_config.yaml
        """
        self._config_file = config_file
        self._config = self._load_config(config_file)

    def _load_config(self, config_file: Optional[str] = None) -> dict:
        """加载配置文件"""
        import yaml

        if config_file is None:
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent.parent
            config_file = project_root / 'config' / 'fog_config.yaml'

        config_path = Path(config_file)
        if not config_path.exists():
            possible_paths = [
                Path(__file__).parent.parent.parent.parent / 'config' / 'fog_config.yaml',
                Path.cwd() / 'config' / 'fog_config.yaml',
            ]
            for p in possible_paths:
                if p.exists():
                    config_path = p
                    break

        try:
            database = _database_from_path(config_path)
            if not _has_database_values(database):
                project_config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'fog_config.yaml'
                if config_path != project_config_path:
                    database = _database_from_path(project_config_path)
            if not _has_database_values(database):
                personal_path = config_path.parent / 'personal_config.yaml'
                database = _database_from_path(personal_path)
            return {'database': database if isinstance(database, dict) else {}}
        except Exception as e:
            print(f"⚠️ 加载配置文件失败: {e}")
            return {}

    @property
    def config_file(self) -> Optional[str]:
        """获取配置文件路径"""
        return self._config_file

    @property
    def database(self) -> dict:
        """获取数据库配置"""
        return self._config.get('database', {})

    def get(self, key: str, default: any = None) -> any:
        """获取配置项"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


def _has_database_values(database: object) -> bool:
    if not isinstance(database, dict):
        return False
    return any(database.get(key) not in (None, "") for key in ("host", "database", "user", "password"))


def _database_from_path(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    database = data.get('database', {})
    if not _has_database_values(database):
        aliyun_database = data.get('aliyun_database', {})
        if _has_database_values(aliyun_database):
            database = aliyun_database
    return database if isinstance(database, dict) else {}
