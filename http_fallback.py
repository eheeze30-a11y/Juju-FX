# http_fallback.py - HTTP server on port 8080 for MT5 fallback
from flask import Flask, jsonify, request
import time
from datetime import datetime
import json

# Create Flask app for HTTP
http_app = Flask(__name__)

# Try to get current level from main app
try:
    # This file should be in the same folder as app.py
    import sys
    sys.path.append('.')
    from app import CURRENT_LEVEL
    print(f"✅ Connected to main app. Current level: {CURRENT_LEVEL}")
except ImportError as e:
    print(f"⚠️ Could not import from main app: {e}")
    CURRENT_LEVEL = 0
    print(f"⚠️ Using default level: {CURRENT_LEVEL}")

# Simple endpoint for MT5
@http_app.route('/api/level', methods=['GET'])
def http_level():
    """HTTP endpoint for MT5"""
    return jsonify({
        "status": "success",
        "level": CURRENT_LEVEL,
        "message": "HTTP Fallback Server",
        "timestamp": datetime.now().isoformat(),
        "server": "http://localhost:8080"
    })

# Alternative endpoint
@http_app.route('/mt5/level', methods=['GET'])
def http_mt5_level():
    """Alternative HTTP endpoint"""
    return jsonify({
        "level": CURRENT_LEVEL,
        "status": "ok",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# Health check
@http_app.route('/health', methods=['GET'])
def http_health():
    return jsonify({
        'status': 'healthy',
        'server': 'http_fallback',
        'port': 8080,
        'timestamp': datetime.now().isoformat()
    })

# Record trade (for MT5)
@http_app.route('/api/record_trade', methods=['POST'])
def http_record_trade():
    try:
        data = request.get_json()
        print(f"📝 Trade received via HTTP: {data}")
        return jsonify({
            "status": "success",
            "message": "Trade recorded via HTTP",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# Test endpoint
@http_app.route('/test', methods=['GET'])
def test():
    return jsonify({
        "message": "HTTP Fallback Server is running",
        "time": datetime.now().isoformat(),
        "level": CURRENT_LEVEL
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting HTTP Fallback Server for MT5")
    print("=" * 60)
    print("📡 Server: http://localhost:8080")
    print("🔗 Endpoints:")
    print("  • GET  /api/level     - Get current level")
    print("  • GET  /mt5/level     - Alternative level endpoint")
    print("  • GET  /health        - Health check")
    print("  • POST /api/record_trade - Record trades")
    print("  • GET  /test          - Test connection")
    print("=" * 60)
    print("💡 Use this if MT5 has issues with HTTPS")
    print("=" * 60)
    
    # Run HTTP server
    http_app.run(
        host='0.0.0.0',
        port=8080,
        debug=False
    )