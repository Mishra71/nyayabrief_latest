import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from nyayabrief import db

with db.get_conn() as c:
    n = c.execute("DELETE FROM issues WHERE issue_date = '2019-11-08'").rowcount
print(n, "issue deleted")