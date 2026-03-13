# reset_and_create.py
import os
from app import app, DATA_DIR, migrate_database
from werkzeug.security import generate_password_hash
import secrets

# Delete old database
db_path = os.path.join(DATA_DIR, 'ea_manager.db')
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"🗑️ Deleted old database: {db_path}")

# Run migration to create fresh database
with app.app_context():
    migrate_database()
    
    # Create admin user
    db = get_db()
    password_hash = generate_password_hash('Zizie_Juju_300')
    api_key = secrets.token_urlsafe(32)
    api_secret = secrets.token_urlsafe(32)
    
    db.execute('''
        INSERT INTO users (
            username, password_hash, email, full_name, 
            user_type, status, subscription_plan, 
            api_key, api_secret
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'Abdul.Baderien', 
        password_hash, 
        'abdul@jujufx.com', 
        'Abdul Baderien',
        'admin', 
        'active', 
        'lifetime',
        api_key, 
        api_secret
    ))
    db.commit()
    print("✅ Fresh database created with admin user!")
    print(f"   Username: Abdul.Baderien")
    print(f"   Password: Zizie_Juju_300")