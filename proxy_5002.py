# proxy_5002.py - MT5 Proxy Server v1.0
from flask import Flask, jsonify, request
from datetime import datetime
import os
import json
import sys

app = Flask(__name__)

# Store level persistently
LEVEL_FILE = "current_level.dat"
current_level = 5  # Default level
last_update = datetime.now()

# Load saved level on startup
def load_level():
    global current_level
    try:
        if os.path.exists(LEVEL_FILE):
            with open(LEVEL_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    current_level = int(content)
                    print(f"📊 Loaded saved level: {current_level}")
                else:
                    current_level = 5
                    save_level()
        else:
            current_level = 5
            save_level()
    except Exception as e:
        print(f"⚠️ Error loading level: {e}")
        current_level = 5
        save_level()

def save_level():
    """Save level to file"""
    try:
        with open(LEVEL_FILE, 'w') as f:
            f.write(str(current_level))
    except Exception as e:
        print(f"⚠️ Error saving level: {e}")

# Load on startup
load_level()

# ===========================================
# API ENDPOINTS
# ===========================================

@app.route('/')
def index():
    """Home page"""
    return jsonify({
        "status": "success",
        "message": "MT5 Proxy Server is running",
        "endpoints": {
            "get_level": "GET /api/level",
            "set_level": "POST /set_level",
            "record_trade": "POST /api/record_trade",
            "health": "GET /health"
        },
        "current_level": current_level,
        "server": "http://127.0.0.1:5002",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/level', methods=['GET'])
def get_level():
    """Endpoint for MT5 EA - THIS IS WHAT MT5 CALLS"""
    global current_level, last_update
    client_ip = request.remote_addr
    print(f"🌐 MT5 requested level: {current_level} from {client_ip} at {datetime.now().strftime('%H:%M:%S')}")
    
    return jsonify({
        "status": "success",
        "level": current_level,
        "message": "OK",
        "timestamp": datetime.now().isoformat(),
        "server": "MT5 Proxy v1.0",
        "synced": True
    })

@app.route('/set_level', methods=['POST'])
def set_level():
    """Set level from dashboard - THIS IS WHAT DASHBOARD CALLS"""
    global current_level, last_update
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        
        new_level = int(data.get('level', current_level))
        
        if 0 <= new_level <= 6:
            old_level = current_level
            current_level = new_level
            last_update = datetime.now()
            save_level()  # Save to file
            
            print(f"✅ Level changed: {old_level} → {new_level}")
            
            # Also update dashboard (8443) if it's running
            try:
                import requests
                requests.post('https://localhost:8443/api/public/set_level', 
                            json={'level': new_level}, 
                            verify=False, timeout=1)
                print(f"   📡 Updated dashboard to level {new_level}")
            except Exception as e:
                print(f"   ⚠️ Could not update dashboard: {e}")
            
            return jsonify({
                "status": "success",
                "level": current_level,
                "message": f"Level {new_level} activated",
                "timestamp": last_update.isoformat()
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Level must be between 0 and 6"
            }), 400
            
    except Exception as e:
        print(f"❌ Error setting level: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/set_level', methods=['POST'])
def api_set_level():
    """Alternative endpoint for set_level"""
    return set_level()

@app.route('/api/record_trade', methods=['POST'])
def record_trade():
    """Record trade from MT5"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        
        print(f"\n📥 TRADE RECEIVED FROM MT5:")
        print(f"   Ticket: {data.get('ticket')}")
        print(f"   Symbol: {data.get('symbol')}")
        print(f"   Type: {data.get('type')}")
        print(f"   Volume: {data.get('volume')}")
        print(f"   Profit: ${data.get('profit')}")
        print(f"   Level: {data.get('level')}")
        
        # Forward to main dashboard (port 8443) if running
        try:
            import requests
            response = requests.post(
                'https://localhost:8443/api/record_trade',
                json=data,
                verify=False,
                timeout=2
            )
            print(f"   ✅ Forwarded to dashboard (8443)")
            return jsonify(response.json()), response.status_code
        except Exception as e:
            print(f"   ⚠️ Main dashboard not running ({e}), storing locally")
            
            # Store locally
            TRADES_FILE = "trades_backup.json"
            trades = []
            if os.path.exists(TRADES_FILE):
                try:
                    with open(TRADES_FILE, 'r') as f:
                        trades = json.load(f)
                except:
                    trades = []
            
            # Add metadata
            trade_with_meta = {
                **data,
                "proxy_received": datetime.now().isoformat(),
                "proxy_version": "1.0",
                "stored_locally": True
            }
            
            trades.append(trade_with_meta)
            
            # Save to file
            with open(TRADES_FILE, 'w') as f:
                json.dump(trades, f, indent=2)
            
            print(f"   💾 Stored locally in {TRADES_FILE}")
            
            return jsonify({
                "status": "success", 
                "message": "Trade stored locally (dashboard offline)",
                "stored": True,
                "local_file": TRADES_FILE
            })
            
    except Exception as e:
        print(f"❌ Error recording trade: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "level": current_level,
        "last_update": last_update.isoformat(),
        "server": "MT5 Proxy on port 5002",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "mt5_get_level": "http://127.0.0.1:5002/api/level",
            "dashboard_set_level": "http://127.0.0.1:5002/set_level",
            "record_trade": "http://127.0.0.1:5002/api/record_trade"
        }
    })

@app.route('/debug', methods=['GET'])
def debug():
    """Debug info"""
    return jsonify({
        "current_level": current_level,
        "level_file": LEVEL_FILE,
        "file_exists": os.path.exists(LEVEL_FILE),
        "last_update": last_update.isoformat(),
        "server_time": datetime.now().isoformat(),
        "python_version": sys.version
    })

# ===========================================
# ERROR HANDLERS
# ===========================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found",
        "available_endpoints": {
            "GET /": "Home page",
            "GET /api/level": "Get current level (MT5 uses this)",
            "POST /set_level": "Set level from dashboard",
            "POST /api/record_trade": "Record trade from MT5",
            "GET /health": "Health check",
            "GET /debug": "Debug info"
        }
    }), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "status": "error",
        "message": "Internal server error",
        "current_level": current_level
    }), 500

# ===========================================
# STARTUP
# ===========================================

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 MT5 PROXY SERVER v1.0")
    print("=" * 70)
    print(f"📊 Current Level: {current_level}")
    print("🌐 Port: 5002")
    print("🔗 URL: http://127.0.0.1:5002")
    print("")
    print("📡 MT5 EA CONNECTION:")
    print("  • Get Level: http://127.0.0.1:5002/api/level")
    print("  • Record Trade: http://127.0.0.1:5002/api/record_trade")
    print("")
    print("📊 DASHBOARD CONNECTION:")
    print("  • Set Level: http://127.0.0.1:5002/set_level")
    print("  • Forwarding to: https://localhost:8443")
    print("")
    print("🔧 DEBUG ENDPOINTS:")
    print("  • /health - Health check")
    print("  • /debug - Debug info")
    print("=" * 70)
    print("")
    print("📝 To test connection:")
    print("  • Browser: http://127.0.0.1:5002/api/level")
    print("  • curl: curl http://127.0.0.1:5002/api/level")
    print("=" * 70)
    
    # Run the server
    try:
        app.run(host='127.0.0.1', port=5002, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\n👋 Proxy server stopped")
        print("💾 Last level saved:", current_level)
    except Exception as e:
        print(f"\n❌ Failed to start proxy: {e}")
        print("💡 Check if port 5002 is already in use:")
        print("   netstat -ano | findstr :5002")