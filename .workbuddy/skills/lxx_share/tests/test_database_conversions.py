from pymysql.constants import FIELD_TYPE

from lxx_share.database import _MYSQL_CONVERSIONS


def test_mysql_decimal_types_are_converted_to_float():
    assert _MYSQL_CONVERSIONS[FIELD_TYPE.DECIMAL]("1.23") == 1.23
    assert _MYSQL_CONVERSIONS[FIELD_TYPE.NEWDECIMAL]("4.56") == 4.56
