"""Generate SQL DDL for the database tables to a file."""

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import models as database


def main() -> None:
    """Write CREATE TABLE statements for all SQLModel tables to a file."""
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sql/create_tables.sql")
    output.parent.mkdir(parents=True, exist_ok=True)
    statements = [
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in database.SQLModel.metadata.sorted_tables
    ]
    output.write_text(";\n\n".join(statements) + ";\n")


if __name__ == "__main__":
    main()
