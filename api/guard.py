"""Read-only check for SQL written by the agent.

This is the second lock. The first is the service account, which can only read.
"""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

ALLOWED_TABLES = {"snapshots", "stations"}
MAX_ROWS = 100
BLOCKED = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Merge, exp.Command)


class UnsafeQuery(ValueError):
    pass


def check_sql(sql: str, dataset: str = "datapilot") -> str:
    """Return safe BigQuery SQL with a row limit, or raise UnsafeQuery."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="bigquery") if s is not None]
    except SqlglotError as error:
        raise UnsafeQuery(f"The SQL could not be read: {error}") from error
    if len(statements) != 1:
        raise UnsafeQuery("Only one statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeQuery("Only SELECT queries are allowed.")
    if any(tree.find_all(*BLOCKED)):
        raise UnsafeQuery("Only SELECT queries are allowed.")

    cte_names = {cte.alias for cte in tree.find_all(exp.CTE)}
    used = set()
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeQuery("Table functions are not allowed.")
        if table.name in cte_names and not table.db:
            continue
        if table.catalog or table.db not in ("", dataset):
            raise UnsafeQuery(f"Table not allowed: {table.sql(dialect='bigquery')}")
        used.add(table.name)
    if not used:
        raise UnsafeQuery("The query must read a table.")
    if not used <= ALLOWED_TABLES:
        raise UnsafeQuery(f"Table not allowed: {', '.join(sorted(used - ALLOWED_TABLES))}")
    if isinstance(tree, exp.Select) and tree.args.get("limit") is None:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="bigquery")
