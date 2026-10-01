import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # run from anywhere
"""Create tables. Run once per database (local docker AND your Neon/Supabase DB)."""
from nyayabrief import db

db.init_schema()
print("schema ready")
