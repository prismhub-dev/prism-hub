from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS font_family VARCHAR(50) DEFAULT 'Inter';"))
        conn.commit()
    print("Migration done.")