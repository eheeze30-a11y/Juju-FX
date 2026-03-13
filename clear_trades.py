#!/usr/bin/env python3
"""
Clear all trade history from Juju FX Dashboard
Run: python3 clear_trades.py
"""

import sqlite3
import os
from datetime import datetime

print("=" * 60)
print("🧹 JUJU FX - CLEAR TRADE HISTORY")
print("=" * 60)

# Database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'ea_manager.db')

# Confirm with user
print(f"\n📁 Database: {DB_PATH}")
print("\n⚠️  WARNING: This will DELETE ALL trade history!")
print("   • All trades will be removed")
print("   • Performance data will be reset")
print("   • Charts will start from zero")

confirm = input("\nType 'YES' to confirm: ")

if confirm != "YES":
    print("\n❌ Operation cancelled")
    exit()

try:
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current counts
    cursor.execute("SELECT COUNT(*) FROM trades")
    trade_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM performance")
    perf_count = cursor.fetchone()[0]
    
    print(f"\n📊 Current data:")
    print(f"   • Trades: {trade_count}")
    print(f"   • Performance records: {perf_count}")
    
    # Delete all data
    print("\n🔄 Clearing data...")
    
    cursor.execute("DELETE FROM trades")
    trades_deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM performance")
    perf_deleted = cursor.rowcount
    
    # Reset auto-increment
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='performance'")
    
    conn.commit()
    
    print(f"\n✅ SUCCESS!")
    print(f"   • {trades_deleted} trades deleted")
    print(f"   • {perf_deleted} performance records deleted")
    print(f"   • Database reset complete")
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM trades")
    new_trade_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM performance")
    new_perf_count = cursor.fetchone()[0]
    
    print(f"\n📊 New counts:")
    print(f"   • Trades: {new_trade_count}")
    print(f"   • Performance: {new_perf_count}")
    
    conn.close()
    
    print("\n🎯 Dashboard will now show EMPTY data")
    print("   New trades from today will be recorded")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    
print("\n" + "=" * 60)