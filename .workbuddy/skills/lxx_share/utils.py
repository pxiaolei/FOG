"""FOG 共享 Skill 的日志与 Python 路径辅助。"""

import logging
import os
import sys
from pathlib import Path


def setup_skills_path(caller_file: str) -> Path:
    """将 skills 目录加入 sys.path，并返回该目录。"""
    current = Path(caller_file).resolve()
    for parent in current.parents:
        if (parent / "lxx_share").is_dir():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return parent
    skills_dir = current.parents[2]
    if str(skills_dir) not in sys.path:
        sys.path.insert(0, str(skills_dir))
    return skills_dir


def get_logger(name: str) -> logging.Logger:
    """返回遵循 LOG_LEVEL 的标准输出 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))
    return logger
