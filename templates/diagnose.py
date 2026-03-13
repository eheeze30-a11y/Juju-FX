#!/usr/bin/env python3
import sqlite3
import json
import sys
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up one level if we're in templates, to find app.py
if os.path.basename(SCRIPT_DIR) == 'templates':
    DASHBOARD_DIR = os.path.dirname(SCRIPT_DIR)
else:
    DASHBOARD_DIR = SCRIPT_DIR

sys.path.insert(0, DASHBOARD_DIR)

# Change to dashboard directory so SQLite finds the database
os.chdir(DASHBOARD_DIR)

try:
    from app import app, get_db
except ImportError as e:
    print(f"❌ Cannot import app.py: {e}")
    print(f"Looking in: {DASHBOARD_DIR}")
    print(f"Files found: {os.listdir(DASHBOARD_DIR) if os.path.exists(DASHBOARD_DIR) else 'directory not found'}")
    sys.exit(1)

def diagnose():
    with app.app_context():
        try:
            db = get_db()
            
            print("=" * 60)
            print("JUJU FX TRADE DIAGNOSTICS")
            print("=" * 60)
            
            # 1. Check trade count
            count = db.execute('SELECT COUNT(*) as c FROM trades').fetchone()['c']
            print(f"\n1. Total trades in database: {count}")
            
            if count == 0:
                print("   ❌ CRITICAL: No trades found in database")
                print("   → Check if MT5 proxy is running and connected")
                return
            
            # 2. Check trade structure
            sample = db.execute('SELECT * FROM trades LIMIT 1').fetchone()
            print(f"\n2. Sample trade fields:")
            for key in sample.keys():
                val = sample[key]
                print(f"   {key}: {val} (type: {type(val).__name__})")
            
            # 3. Check for NULL close_times
            null_closed = db.execute("SELECT COUNT(*) as c FROM trades WHERE close_time IS NULL OR close_time = ''").fetchone()['c']
            print(f"\n3. Trades with NULL/empty close_time: {null_closed}")
            if null_closed == count:
                print("   ⚠️  WARNING: All trades have no close_time!")
                print("   → Recent trades query will return empty")
            
            # 4. Check profit values
            profit_check = db.execute('SELECT profit, profit + COALESCE(swap, 0) + COALESCE(commission, 0) as total FROM trades WHERE profit IS NOT NULL LIMIT 3').fetchall()
            print(f"\n4. Sample profit calculations:")
            for row in profit_check:
                print(f"   profit={row['profit']}, total_with_fees={row['total']}")
            
            # 5. Check level distribution
            levels = db.execute('SELECT level, COUNT(*) as c FROM trades GROUP BY level').fetchall()
            print(f"\n5. Trades by level:")
            for row in levels:
                print(f"   Level {row['level']}: {row['c']} trades")
            
            # 6. Test the actual API query used by dashboard
            print(f"\n6. Testing CURRENT recent trades query (will show why it's empty)...")
            recent = db.execute('''
                SELECT ticket, symbol, profit, close_time, level 
                FROM trades 
                WHERE close_time IS NOT NULL AND close_time != ''
                ORDER BY close_time DESC 
                LIMIT 5
            ''').fetchall()
            
            print(f"   Current query returned: {len(recent)} trades")
            
            if not recent:
                print("   ❌ Query returned NO results - THIS IS THE PROBLEM!")
                print("\n   Testing ALTERNATIVE query (using open_time)...")
                recent = db.execute('''
                    SELECT ticket, symbol, profit, open_time as time, level 
                    FROM trades 
                    WHERE open_time IS NOT NULL AND open_time != ''
                    ORDER BY open_time DESC 
                    LIMIT 5
                ''').fetchall()
                print(f"   Alternative query returned: {len(recent)} trades")
                for row in recent:
                    print(f"   #{row['ticket']} {row['symbol']} L{row['level']} Profit:{row['profit']}")
            
            print("\n" + "=" * 60)
            print("RECOMMENDATIONS:")
            print("=" * 60)
            
            if null_closed == count:
                print("🔧 FIX NEEDED: Update get_recent_trades() in app.py")
                print("   Replace the close_time filter with COALESCE logic")
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    diagnose()