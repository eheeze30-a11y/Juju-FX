# migrate.py - Run this first
from app import app, get_db, migrate_database

with app.app_context():
    migrate_database()
    print("Database migration complete!")