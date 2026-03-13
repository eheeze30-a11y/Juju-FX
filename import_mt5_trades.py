#!/usr/bin/env python3
# import_mt5_trades.py - Import trades to dashboard - QUANTUM EDITION

import requests
import json
import sys
from datetime import datetime, timedelta
import random

DASHBOARD_URL = 'http://127.0.0.1:5002'  # Via proxy
# DASHBOARD_URL = 'http://127.0.0.1:8443'  # Direct to main server

def create_sample_trades():
    """Create sample trades for testing"""
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'AUDUSD', 'US30']
    types = ['buy', 'sell']
    levels = list(range(7))
    eas = ['TrendFollower', 'BreakoutBot', 'ScalperPro', 'GridMaster', 'MartingaleAI']
    
    trades = []
    base_time = datetime.now() - timedelta(days=7)
    
    for i in range(50):
        ticket = 1000 + i
        symbol = random.choice(symbols)
        trade_type = random.choice(types)
        level = random.choice(levels)
        ea = random.choice(eas)
        
        # Generate realistic P/L
        base_profit = random.uniform(-50, 80)
        if level > 0:
            base_profit *= (level * 0.5 + 0.5)  # Higher levels = bigger trades
        
        trade_time = base_time + timedelta(hours=i*3, minutes=random.randint(0, 59))
        
        trades.append({
            "ticket": ticket,
            "symbol": symbol,
            "type": trade_type,
            "volume": round(random.uniform(0.1, 2.0), 2),
            "open_price": round(random.uniform(1.0, 2000.0), 5),
            "close_price": round(random.uniform(1.0, 2000.0), 5),
            "open_time": trade_time.strftime('%Y-%m-%d %H:%M:%S'),
            "close_time": (trade_time + timedelta(hours=random.randint(1, 8))).strftime('%Y-%m-%d %H:%M:%S'),
            "profit": round(base_profit, 2),
            "swap": round(random.uniform(-2, 0), 2),
            "commission": round(random.uniform(0, 7), 2),
            "magic_number": 10000 + level,
            "comment": f"AutoTrade L{level}",
            "level": level,
            "ea_name": ea,
            "ea_version": "2.0"
        })
    
    return trades

def import_trades(trades):
    """Import trades to dashboard"""
    print(f"\n📤 Importing {len(trades)} trades to {DASHBOARD_URL}")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for trade in trades:
        try:
            response = requests.post(
                f'{DASHBOARD_URL}/api/record_trade',
                json=trade,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') in ['success', 'queued']:
                    print(f"✅ Trade {trade['ticket']:4d} ({trade['symbol']:8s} L{trade['level']}) - ${trade['profit']:7.2f} - {result.get('status')}")
                    success_count += 1
                else:
                    print(f"⚠️  Trade {trade['ticket']:4d} - {result.get('message')}")
                    failed_count += 1
            else:
                print(f"❌ Trade {trade['ticket']:4d} - HTTP {response.status_code}")
                failed_count += 1
                
        except Exception as e:
            print(f"❌ Trade {trade['ticket']:4d} - Error: {e}")
            failed_count += 1
    
    print("=" * 60)
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"\n💡 View dashboard at: http://localhost:8443")
    return success_count > 0

def check_health():
    """Check if dashboard is running"""
    try:
        response = requests.get(f'{DASHBOARD_URL}/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Dashboard is online")
            print(f"   Trades in DB: {data.get('trade_count', 'N/A')}")
            print(f"   Current Level: {data.get('current_level', 'N/A')}")
            return True
    except Exception as e:
        print(f"❌ Cannot connect to dashboard: {e}")
        print(f"   Make sure the server is running on {DASHBOARD_URL}")
        return False

if __name__ == '__main__':
    print("🚀 JUJU FX Trade Importer")
    print("=" * 60)
    
    if not check_health():
        sys.exit(1)
    
    # Ask for confirmation
    print("\n1. Import sample trades (50 trades)")
    print("2. Import from file")
    print("3. Clear all trades")
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == '1':
        trades = create_sample_trades()
        if import_trades(trades):
            print("\n✨ Sample data imported successfully!")
            print("🌐 Open http://localhost:8443 to view your dashboard")
    elif choice == '2':
        filename = input("Enter filename: ").strip()
        try:
            with open(filename, 'r') as f:
                trades = json.load(f)
            import_trades(trades)
        except Exception as e:
            print(f"❌ Error loading file: {e}")
    elif choice == '3':
        confirm = input("⚠️  Are you sure? This will delete ALL trades! (yes/no): ").strip().lower()
        if confirm == 'yes':
            # Note: This would need a delete endpoint
            print("Feature not implemented in this version")
    else:
        print("Invalid option")