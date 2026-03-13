# mt5_proxy.py - HTTP Proxy for MT5 - QUANTUM EDITION v3.6
# FIXED VERSION with corrected URLs and thread safety

from flask import Flask, jsonify, request
import requests
import threading
import time
import json
import os
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store current level with lock protection
CURRENT_LEVEL = 0
level_lock = threading.Lock()
LAST_SYNC = None
SYNC_INTERVAL = 5  # seconds

# Configuration
MAIN_SERVER = 'http://localhost:8443'
PROXY_PORT = 5002

# Thread-local storage for DB connections
thread_local = threading.local()

print("\n" + "="*60)
print("🚀 MT5 PROXY SERVER v3.6 QUANTUM EDITION")
print("="*60)
print(f"📡 Server: http://127.0.0.1:{PROXY_PORT}")  # FIXED: removed space
print(f"🔗 Main App: {MAIN_SERVER}")
print("="*60)

def get_queue_db():
    """Get thread-local database connection"""
    if not hasattr(thread_local, 'queue_db'):
        thread_local.queue_db = sqlite3.connect(QUEUE_DB, check_same_thread=False)
        thread_local.queue_db.execute('''
            CREATE TABLE IF NOT EXISTS pending_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_data TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_attempt TIMESTAMP
            )
        ''')
        thread_local.queue_db.execute('CREATE INDEX IF NOT EXISTS idx_pending ON pending_trades(created_at, attempts)')
        thread_local.queue_db.commit()
    return thread_local.queue_db

QUEUE_DB = 'proxy_queue.db'
QUEUE_LOCK = threading.Lock()

def queue_trade(trade_data):
    """Queue trade for later delivery if main server is down"""
    try:
        with QUEUE_LOCK:
            db = get_queue_db()
            db.execute(
                'INSERT INTO pending_trades (trade_data) VALUES (?)',
                (json.dumps(trade_data),)
            )
            db.commit()
        logger.info(f"📥 Queued trade {trade_data.get('ticket')} for later delivery")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to queue trade: {e}")
        return False

def process_queue():
    """Background thread to process queued trades"""
    while True:
        try:
            with QUEUE_LOCK:
                db = get_queue_db()
                cursor = db.execute(
                    '''SELECT id, trade_data, attempts FROM pending_trades 
                       WHERE attempts < 5 
                       ORDER BY created_at LIMIT 5'''
                )
                pending = cursor.fetchall()
            
            for trade_id, trade_data, attempts in pending:
                data = json.loads(trade_data)
                logger.info(f"🔄 Attempting to deliver queued trade {data.get('ticket')} (attempt {attempts + 1})")
                
                response = forward_to_main('/api/record_trade', data, max_retries=1)
                
                if response and response.status_code == 200:
                    with QUEUE_LOCK:
                        db = get_queue_db()
                        db.execute('DELETE FROM pending_trades WHERE id = ?', (trade_id,))
                        db.commit()
                    logger.info(f"✅ Queued trade {data.get('ticket')} delivered successfully")
                else:
                    with QUEUE_LOCK:
                        db = get_queue_db()
                        db.execute(
                            'UPDATE pending_trades SET attempts = attempts + 1, last_attempt = CURRENT_TIMESTAMP WHERE id = ?',
                            (trade_id,)
                        )
                        db.commit()
                        
        except Exception as e:
            logger.error(f"❌ Queue processing error: {e}")
        
        time.sleep(10)

def forward_to_main(endpoint, data=None, max_retries=3):
    """Forward request to main HTTP server with exponential backoff"""
    headers = {
        'Content-Type': 'application/json',
        'Origin': f'http://127.0.0.1:{PROXY_PORT}'  # FIXED: removed space
    }
    
    for attempt in range(max_retries):
        try:
            url = f'{MAIN_SERVER}{endpoint}'
            
            if data:
                response = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                return response
            
            if response.status_code >= 500:
                raise requests.exceptions.RequestException(f"Server error: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            wait_time = (2 ** attempt) + (attempt * 0.5)
            logger.warning(f"⚠️ Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s...")
            if attempt < max_retries - 1:
                time.sleep(wait_time)
    
    logger.error(f"❌ Failed after {max_retries} attempts")
    return None

def sync_with_main():
    """Sync with main HTTP server"""
    global CURRENT_LEVEL, LAST_SYNC
    
    while True:
        try:
            headers = {'Origin': f'http://127.0.0.1:{PROXY_PORT}'}  # FIXED: removed space
            
            response = requests.get(f'{MAIN_SERVER}/api/level', 
                                  headers=headers,
                                  timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                new_level = data.get('level', 0)
                
                with level_lock:
                    if new_level != CURRENT_LEVEL:
                        old_level = CURRENT_LEVEL
                        CURRENT_LEVEL = new_level
                        logger.info(f"🔄 Synced level: {old_level} → {new_level}")
                
                LAST_SYNC = datetime.now()
            else:
                logger.warning(f"❌ Sync failed: HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Sync error: {e}")
        
        time.sleep(SYNC_INTERVAL)

def initialize_level():
    """Get current level from dashboard on startup"""
    global CURRENT_LEVEL
    try:
        response = requests.get(f'{MAIN_SERVER}/api/level', timeout=5)
        if response.status_code == 200:
            with level_lock:
                CURRENT_LEVEL = response.json().get('level', 0)
            logger.info(f"📊 Initial level loaded: {CURRENT_LEVEL}")
    except Exception as e:
        logger.error(f"⚠️ Could not load initial level: {e}")

# ===========================================
# PROXY ENDPOINTS
# ===========================================

@app.route('/')
def index():
    """Proxy homepage"""
    with QUEUE_LOCK:
        db = get_queue_db()
        queue_count = db.execute('SELECT COUNT(*) FROM pending_trades').fetchone()[0]
    
    with level_lock:
        current_level = CURRENT_LEVEL
    
    return jsonify({
        "server": "MT5 Quantum Proxy",
        "status": "running",
        "port": PROXY_PORT,
        "main_server": MAIN_SERVER,
        "current_level": current_level,
        "last_sync": LAST_SYNC.isoformat() if LAST_SYNC else None,
        "queued_trades": queue_count,
        "version": "3.6"
    })

@app.route('/api/level', methods=['GET'])
def get_level():
    """Get current level - MT5 uses this"""
    with level_lock:
        level = CURRENT_LEVEL
    
    return jsonify({
        "status": "success",
        "level": level,
        "message": "MT5 Quantum Proxy Server",
        "server": f"http://127.0.0.1:{PROXY_PORT}",  # FIXED: removed space
        "timestamp": datetime.now().isoformat(),
        "synced": LAST_SYNC is not None
    })

@app.route('/api/record_trade', methods=['POST'])
def record_trade():
    """Forward trades to main app with queue fallback"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        
        ticket = data.get('ticket')
        logger.info(f"📤 Received trade {ticket} at proxy")
        
        # Clean symbol
        symbol = data.get('symbol', '')
        if symbol and symbol.endswith('.m'):
            data['symbol'] = symbol[:-2]
        
        response = forward_to_main('/api/record_trade', data)
        
        if response and response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Trade {ticket} forwarded successfully")
            return jsonify(result)
        else:
            if queue_trade(data):
                return jsonify({
                    "status": "queued",
                    "message": "Main server unavailable, trade queued for delivery",
                    "ticket": ticket
                }), 202
            else:
                return jsonify({
                    "status": "error",
                    "message": "Failed to queue trade"
                }), 500
            
    except Exception as e:
        logger.error(f"❌ Error in record_trade proxy: {e}")
        try:
            if queue_trade(request.get_json()):
                return jsonify({"status": "queued", "message": "Error occurred, trade queued"}), 202
        except:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    with QUEUE_LOCK:
        db = get_queue_db()
        queue_count = db.execute('SELECT COUNT(*) FROM pending_trades').fetchone()[0]
    
    with level_lock:
        level = CURRENT_LEVEL
    
    return jsonify({
        "status": "healthy",
        "server": f"Quantum Proxy on port {PROXY_PORT}",
        "current_level": level,
        "main_server": MAIN_SERVER,
        "last_sync": LAST_SYNC.isoformat() if LAST_SYNC else "Never",
        "queued_trades": queue_count,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/set_level', methods=['POST'])
def set_level():
    """Receive level updates from dashboard"""
    global CURRENT_LEVEL
    
    try:
        data = request.get_json()
        new_level = int(data.get('level', CURRENT_LEVEL))
        
        if 0 <= new_level <= 6:
            with level_lock:
                CURRENT_LEVEL = new_level
                level = CURRENT_LEVEL
            logger.info(f"📊 Level updated via proxy: {new_level}")
            
            # Forward to main server
            try:
                forward_to_main('/api/public/set_level', {'level': new_level}, max_retries=1)
            except:
                pass
            
            return jsonify({"status": "success", "level": level})
        else:
            return jsonify({"status": "error", "message": "Invalid level"}), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ===========================================
# START PROXY
# ===========================================

if __name__ == '__main__':
    # Initialize level before starting threads
    initialize_level()
    
    # Start sync thread
    sync_thread = threading.Thread(target=sync_with_main, daemon=True)
    sync_thread.start()
    
    # Start queue processor
    queue_thread = threading.Thread(target=process_queue, daemon=True)
    queue_thread.start()
    
    logger.info(f"Starting Quantum Proxy on port {PROXY_PORT}...")
    logger.info("Press CTRL+C to quit\n")
    
    # Run proxy server
    app.run(
        host='0.0.0.0',
        port=PROXY_PORT,
        debug=False,
        threaded=True
    )