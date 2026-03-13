#!/usr/bin/env python3
from app import app, get_db

with app.app_context():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username='Abdul.Baderien'").fetchone()
    if user:
        print("✅ User found!")
        print(f"ID: {user['id']}")
        print(f"Username: {user['username']}")
        print(f"Status: {user['status']}")
        print(f"Type: {user['user_type']}")
    else:
        print("❌ User not found")
