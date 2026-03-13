#!/usr/bin/env python3
"""
Create admin user script
"""
import sqlite3
import os
from werkzeug.security import generate_password_hash

# Database path
DB_PATH = 'data/ea_manager_secure.db'

# Admin credentials
ADMIN_USERNAME = 'Abdul.Baderien'
ADMIN_PASSWORD = 'Zizie_Juju_300'
ADMIN_EMAIL = 'admin@jujufx.com'
ADMIN_FULLNAME = 'Abdul Baderien'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Connect to database
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Create users table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        full_name TEXT,
        user_type TEXT DEFAULT 'member',
        status TEXT DEFAULT 'pending',
        subscription_plan TEXT DEFAULT 'trial',
        subscription_start DATE,
        subscription_end DATE,
        auto_renew INTEGER DEFAULT 1,
        ib_id TEXT UNIQUE,
        referred_by TEXT,
        commission_rate REAL DEFAULT 0.0,
        mt5_account TEXT,
        mt5_server TEXT,
        mt5_password_encrypted TEXT,
        phone TEXT,
        country TEXT,
        timezone TEXT DEFAULT 'Africa/Johannesburg',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        last_active TIMESTAMP,
        settings TEXT DEFAULT '{}',
        failed_login_attempts INTEGER DEFAULT 0,
        last_failed_login TIMESTAMP,
        locked_until TIMESTAMP,
        two_factor_secret TEXT,
        two_factor_enabled INTEGER DEFAULT 0,
        password_changed_at TIMESTAMP,
        password_reset_token TEXT,
        password_reset_expires TIMESTAMP,
        email_verified INTEGER DEFAULT 0,
        verification_token TEXT
    )
''')

# Check if admin exists
cursor.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,))
admin = cursor.fetchone()

if admin:
    # Update existing admin
    password_hash = generate_password_hash(ADMIN_PASSWORD)
    cursor.execute("""
        UPDATE users 
        SET password_hash = ?, status = 'active', email_verified = 1
        WHERE username = ?
    """, (password_hash, ADMIN_USERNAME))
    print(f"✅ Updated admin user: {ADMIN_USERNAME}")
else:
    # Create new admin
    password_hash = generate_password_hash(ADMIN_PASSWORD)
    try:
        cursor.execute("""
            INSERT INTO users (
                username, password_hash, email, full_name, 
                user_type, status, subscription_plan, email_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ADMIN_USERNAME, password_hash, ADMIN_EMAIL, ADMIN_FULLNAME, 
            'admin', 'active', 'lifetime', 1
        ))
        print(f"✅ Created admin user: {ADMIN_USERNAME}")
    except sqlite3.IntegrityError as e:
        print(f"❌ Error creating admin: {e}")

# Commit and close
conn.commit()

# Verify user was created
cursor.execute("SELECT id, username, status FROM users WHERE username = ?", (ADMIN_USERNAME,))
user = cursor.fetchone()
if user:
    print(f"✅ Verified: User {user['username']} (ID: {user['id']}) has status: {user['status']}")
else:
    print("❌ Failed to verify user creation")

conn.close()

print(f"\n🔑 Admin credentials:")
print(f"   Username: {ADMIN_USERNAME}")
print(f"   Password: {ADMIN_PASSWORD}")
print("\n🚀 You can now login with these credentials")
