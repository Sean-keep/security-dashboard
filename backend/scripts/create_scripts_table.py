from app.models.base import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS scripts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            script_type VARCHAR(32) DEFAULT "python",
            description TEXT DEFAULT "",
            content TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX ix_scripts_name (name)
        )
    '''))
    conn.commit()
print('Table created')
