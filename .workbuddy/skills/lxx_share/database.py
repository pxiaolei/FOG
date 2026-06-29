"""
统一数据库连接模块

所有 LX 分析类 skill 应使用此类进行数据库连接，
确保连接管理和错误处理的一致性。

驱动：PyMySQL
"""

from contextlib import contextmanager
from typing import Optional, Generator, Any

import pandas as pd
import pymysql
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions

from lxx_share.utils import Config, get_logger

logger = get_logger("lxx_share.database")

_ConnectionType = Any  # PyMySQL connection
_MYSQL_CONVERSIONS = conversions.copy()
_MYSQL_CONVERSIONS[FIELD_TYPE.DECIMAL] = float
_MYSQL_CONVERSIONS[FIELD_TYPE.NEWDECIMAL] = float


class DatabaseConnector:
    """
    统一数据库连接管理器

    使用方式:
        db = DatabaseConnector()
        df = db.execute("SELECT * FROM table WHERE date >= %s", ["2026-01-01"])

        # 或使用上下文管理器
        with DatabaseConnector() as db:
            df = db.execute(sql, params)
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化数据库连接管理器

        Args:
            config_file: 配置文件路径，默认使用项目配置
        """
        self.config = Config(config_file)
        self.db_config = self.config.database

    @contextmanager
    def connect(self) -> Generator[_ConnectionType, None, None]:
        """
        获取数据库连接的上下文管理器

        Yields:
            数据库连接对象

        Example:
            with db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
        """
        host = self.db_config.get('host', 'localhost')
        port = int(self.db_config.get('port', 3306))
        user = self.db_config.get('user')
        password = self.db_config.get('password')
        dbname = self.db_config.get('database')  # config.yaml 用 database 作为 key
        connect_timeout = self.db_config.get('connect_timeout')
        read_timeout = self.db_config.get('read_timeout')
        write_timeout = self.db_config.get('write_timeout')

        conn = None
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                database=dbname,
                user=user,
                password=password,
                charset=self.db_config.get('charset', 'utf8mb4'),
                conv=_MYSQL_CONVERSIONS,
                autocommit=False,
                connect_timeout=int(connect_timeout or 10),
                read_timeout=int(read_timeout or 300),
                write_timeout=int(write_timeout or 300),
            )
            yield conn
        finally:
            if conn is not None:
                conn.close()

    def execute(self, query: str, params: Optional[list] = None) -> pd.DataFrame:
        """
        执行查询并返回 DataFrame

        Args:
            query: SQL 查询语句
            params: 查询参数列表

        Returns:
            查询结果 DataFrame

        Raises:
            Exception: 查询执行失败时记录日志并返回空 DataFrame
        """
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or [])
                columns = [desc[0] for desc in cursor.description or []]
                df = pd.DataFrame(cursor.fetchall(), columns=columns)
                logger.info(f"✅ 查询成功，返回 {len(df)} 行")
                return df
        except Exception as e:
            logger.error(f"❌ 查询失败: {e}")
            return pd.DataFrame()

    def execute_scalar(self, query: str, params: Optional[list] = None) -> Optional[Any]:
        """
        执行查询并返回标量值（第一行第一列）

        Args:
            query: SQL 查询语句
            params: 查询参数列表

        Returns:
            标量值，查询失败返回 None
        """
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ 标量查询失败: {e}")
            return None

    def execute_non_query(self, query: str, params: Optional[list] = None) -> int:
        """
        执行非查询 SQL（INSERT/UPDATE/DELETE），返回影响的行数

        Args:
            query: SQL 语句
            params: 参数列表

        Returns:
            影响的行数
        """
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"❌ 执行失败: {e}")
            return 0

    def test_connection(self) -> bool:
        """
        测试数据库连接是否正常

        Returns:
            连接是否正常
        """
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"❌ 数据库连接测试失败: {e}")
            return False

    def get_table_sample(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        """
        获取表的样例数据

        Args:
            table_name: 表名（支持 schema.table 格式）
            limit: 返回行数

        Returns:
            样例数据 DataFrame
        """
        query = f"SELECT * FROM {table_name} LIMIT %s"
        return self.execute(query, [limit])
