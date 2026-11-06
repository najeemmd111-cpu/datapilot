import pytest

from guard import UnsafeQuery, check_sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM snapshots WHERE 1=1",
    "DROP TABLE stations",
    "UPDATE stations SET name = 'x' WHERE true",
    "INSERT INTO stations (name) VALUES ('x')",
    "CREATE TABLE copy AS SELECT * FROM stations",
    "SELECT 1; DROP TABLE stations",
    "SELECT * FROM secrets",
    "SELECT * FROM other_dataset.snapshots",
    "SELECT * FROM `other-project.datapilot.snapshots`",
    "SELECT * FROM stations JOIN secrets USING (station_id)",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT 1",
    "this is not sql",
])
def test_blocks_unsafe_sql(sql):
    with pytest.raises(UnsafeQuery):
        check_sql(sql)


def test_allows_select_and_adds_limit():
    assert "LIMIT 100" in check_sql("SELECT name FROM stations")


def test_allows_cte_and_keeps_own_limit():
    sql = check_sql("WITH t AS (SELECT * FROM snapshots) SELECT bikes FROM t LIMIT 5")
    assert "LIMIT 5" in sql and "LIMIT 100" not in sql


def test_cte_cannot_hide_a_forbidden_table():
    with pytest.raises(UnsafeQuery):
        check_sql("WITH t AS (SELECT * FROM secrets) SELECT * FROM t")
