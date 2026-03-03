"""
Database connection utilities for MS SQL Server
"""
import os
import pyodbc
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

load_dotenv()


def get_connection():
    server   = os.getenv('MSSQL_SERVER')
    database = os.getenv('MSSQL_DATABASE')
    username = os.getenv('MSSQL_USERNAME')
    password = os.getenv('MSSQL_PASSWORD')
    driver   = os.getenv('MSSQL_DRIVER', 'ODBC Driver 18 for SQL Server')

    if not all([server, database, username, password]):
        raise ValueError("Missing database config. Check .env: MSSQL_SERVER, MSSQL_DATABASE, MSSQL_USERNAME, MSSQL_PASSWORD")

    connection_string = (
        f'DRIVER={{{driver}}};SERVER={server};DATABASE={database};'
        f'UID={username};PWD={password};TrustServerCertificate=yes;'
    )
    try:
        return pyodbc.connect(connection_string, timeout=10)
    except pyodbc.Error as e:
        raise ConnectionError(f"Failed to connect: {str(e)}")


def create_db_engine() -> Engine:
    server   = os.getenv('MSSQL_SERVER')
    database = os.getenv('MSSQL_DATABASE')
    username = os.getenv('MSSQL_USERNAME')
    password = os.getenv('MSSQL_PASSWORD')
    driver   = os.getenv('MSSQL_DRIVER', 'ODBC Driver 18 for SQL Server')

    if not all([server, database, username, password]):
        raise ValueError("Missing database config. Check .env")

    connection_string = (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}"
        f"?driver={driver.replace(' ', '+')}&TrustServerCertificate=yes"
    )
    return create_engine(connection_string, pool_pre_ping=True)


def validate_connection() -> tuple[bool, str]:
    try:
        engine = create_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT @@VERSION"))
            version = result.fetchone()[0]
            return True, f"✅ Connected!\nSQL Server: {version[:100]}..."
    except Exception as e:
        return False, f"❌ Connection failed: {str(e)}"


def get_database_schema() -> str:
    """Full schema — ทุก column ทุก table"""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.TABLE_SCHEMA, t.TABLE_NAME, c.COLUMN_NAME,
                c.DATA_TYPE, c.IS_NULLABLE,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'PRIMARY KEY' ELSE '' END AS KEY_TYPE
            FROM INFORMATION_SCHEMA.TABLES t
            INNER JOIN INFORMATION_SCHEMA.COLUMNS c
                ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
            LEFT JOIN (
                SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                    ON tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            ) pk ON c.TABLE_NAME = pk.TABLE_NAME AND c.TABLE_SCHEMA = pk.TABLE_SCHEMA
                 AND c.COLUMN_NAME = pk.COLUMN_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE'
            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
        """)
        rows = cursor.fetchall()
        conn.close()

        schema_text  = []
        current_table = None
        for row in rows:
            table_schema, table_name, column_name, data_type, is_nullable, key_type = row
            full_table_name = f"{table_schema}.{table_name}"
            if full_table_name != current_table:
                if current_table is not None:
                    schema_text.append("")
                schema_text.append(f"Table: {full_table_name}")
                current_table = full_table_name
            nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
            key_info = f" ({key_type})" if key_type else ""
            schema_text.append(f"  - {column_name}: {data_type} {nullable}{key_info}")

        return "\n".join(schema_text) if schema_text else "No tables found."
    except Exception as e:
        return f"Error retrieving schema: {str(e)}"


def get_slim_schema() -> str:
    """
    Slim schema — ดึงแค่ข้อมูลที่จำเป็นสำหรับ query:
    - ชื่อ table (schema.table)
    - Primary Keys
    - Foreign Keys (relationship ระหว่าง table)
    - ทุก column พร้อม data type (แต่ไม่มี nullable ให้สั้นลง)

    ลด token ได้ ~60% เทียบกับ full schema
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        # ดึง PK
        cursor.execute("""
            SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                ON tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            ORDER BY ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.ORDINAL_POSITION
        """)
        pk_set = {(r[0], r[1], r[2]) for r in cursor.fetchall()}

        # ดึง FK relationships
        cursor.execute("""
            SELECT 
                fk.TABLE_SCHEMA, fk.TABLE_NAME, fk.COLUMN_NAME,
                pk.TABLE_SCHEMA AS REF_SCHEMA, pk.TABLE_NAME AS REF_TABLE, pk.COLUMN_NAME AS REF_COLUMN
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk
                ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
                ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
                AND fk.ORDINAL_POSITION = pk.ORDINAL_POSITION
            ORDER BY fk.TABLE_SCHEMA, fk.TABLE_NAME
        """)
        fk_map = {}  # (schema, table, col) -> "ref_schema.ref_table.ref_col"
        for r in cursor.fetchall():
            fk_map[(r[0], r[1], r[2])] = f"{r[3]}.{r[4]}.{r[5]}"

        # ดึง columns ทุกตัว (แต่แสดงแบบกระชับ)
        cursor.execute("""
            SELECT t.TABLE_SCHEMA, t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
            FROM INFORMATION_SCHEMA.TABLES t
            INNER JOIN INFORMATION_SCHEMA.COLUMNS c
                ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
            WHERE t.TABLE_TYPE = 'BASE TABLE'
            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
        """)
        rows = cursor.fetchall()
        conn.close()

        schema_text   = []
        current_table = None

        for row in rows:
            table_schema, table_name, col_name, data_type = row
            full_name = f"{table_schema}.{table_name}"

            if full_name != current_table:
                if current_table is not None:
                    schema_text.append("")
                schema_text.append(f"Table: {full_name}")
                current_table = full_name

            # tag สำคัญ
            tags = []
            if (table_schema, table_name, col_name) in pk_set:
                tags.append("PK")
            fk_ref = fk_map.get((table_schema, table_name, col_name))
            if fk_ref:
                tags.append(f"FK→{fk_ref}")

            tag_str = f" [{', '.join(tags)}]" if tags else ""
            schema_text.append(f"  {col_name} ({data_type}){tag_str}")

        return "\n".join(schema_text) if schema_text else "No tables found."

    except Exception as e:
        return f"Error retrieving slim schema: {str(e)}"


def test_connection():
    return validate_connection()


# Alias สำหรับ backward compatibility กับ bi_service.py
def get_schema_info() -> str:
    """Alias of get_slim_schema — kept for backward compatibility"""
    return get_slim_schema()