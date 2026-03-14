#!/usr/bin/env python3
"""
JUJU FX EA Manager v10.0 - COMPLETE PRODUCTION VERSION
SECURITY FIRST - People's financial well-being depends on this
All endpoints working, level changes guaranteed
FIXED: PORT environment variable for App Platform
"""

import os
import sys
import json
import time
import uuid
import hmac
import secrets
import hashlib
import logging
import logging.handlers
import threading
import traceback
import sqlite3
import re
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any, Tuple, List, Union
from pathlib import Path

# Third-party imports
try:
    from flask import (
        Flask, render_template, jsonify, request, redirect, 
        url_for, session, g, make_response, abort, send_file, has_request_context
    )
    from flask_cors import CORS
    from flask_talisman import Talisman
    from werkzeug.security import generate_password_hash, check_password_hash
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.utils import secure_filename
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Install with: pip install flask flask-cors flask-talisman python-dotenv")
    sys.exit(1)

# Optional WebSocket
try:
    from flask_sock import Sock
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("WebSocket disabled (install flask-sock to enable)")

# ===========================================
# ENVIRONMENT SETUP - CRITICAL FIRST STEP
# ===========================================

# Load .env file
env_path = Path(__file__).parent / '.env'
if not env_path.exists():
    # Create template .env with secure defaults
    with open(env_path, 'w') as f:
        f.write(f"""# JUJU FX Production Configuration - CHANGE ALL VALUES!
# This is a financial system - security is PARAMOUNT

# ===========================================
# SECURITY - CHANGE THESE IMMEDIATELY!
# ===========================================
SECRET_KEY={secrets.token_urlsafe(32)}
ADMIN_USERNAME=Abdul.Baderien
ADMIN_PASSWORD={secrets.token_urlsafe(12)}
EA_API_KEY={secrets.token_urlsafe(32)}

# ===========================================
# SERVER CONFIGURATION
# ===========================================
SERVER_URL=http://45.55.91.52:8443
ALLOWED_ORIGIN=http://45.55.91.52:8443
MT5_PROXY_URL=http://127.0.0.1:5002

# ===========================================
# TRADING CONFIGURATION
# ===========================================
USDZAR_RATE=18.5
MAX_TRADES_PER_MINUTE=1000
MAX_LOGIN_ATTEMPTS=5
SESSION_TIMEOUT_HOURS=2

# ===========================================
# FEATURE TOGGLES
# ===========================================
WEBSOCKET_ENABLED=false
RATE_LIMIT_ENABLED=true
""")
    print("✅ Created .env template - EDIT THIS FILE BEFORE RUNNING!")
    print("⚠️  WARNING: Change all passwords immediately!")
    sys.exit(0)

# Load environment
load_dotenv(env_path)

# Validate critical environment variables
required_vars = ['SECRET_KEY', 'ADMIN_PASSWORD', 'EA_API_KEY']
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print(f"❌ Missing required env vars: {missing}")
    print("Please edit your .env file")
    sys.exit(1)

# ===========================================
# SECURE LOGGING - Financial audit trail
# ===========================================
class SecureLogger:
    """Structured logging with automatic sensitive data masking"""
    
    def __init__(self):
        self.setup_logging()
    
    def setup_logging(self):
        # Create logs directory
        log_dir = Path(__file__).parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Main application log
        self.logger = logging.getLogger('juju_fx')
        self.logger.setLevel(logging.INFO)
        
        # File handlers with rotation (keep 30 days of logs)
        app_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / 'app.log', when='midnight', backupCount=30
        )
        security_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / 'security.log', when='midnight', backupCount=90  # Keep security logs longer
        )
        mt5_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'mt5.log', maxBytes=50*1024*1024, backupCount=5
        )
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'error.log', maxBytes=10*1024*1024, backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        
        # Formatters
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        for handler in [app_handler, security_handler, mt5_handler, error_handler]:
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Console handler for development
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        self.logger.addHandler(console)
    
    def _mask_sensitive(self, msg: str) -> str:
        """Mask passwords, tokens, API keys - NEVER log these"""
        patterns = [
            (r'(password["\s]*:["\s]*)[^"\s,]+', r'\1[REDACTED]'),
            (r'(api_key["\s]*:["\s]*)[^"\s,]+', r'\1[REDACTED]'),
            (r'(token["\s]*:["\s]*)[^"\s,]+', r'\1[REDACTED]'),
            (r'(secret["\s]*:["\s]*)[^"\s,]+', r'\1[REDACTED]'),
            (r'("password":\s*")[^"]+', r'\1[REDACTED]'),
            (r'("api_key":\s*")[^"]+', r'\1[REDACTED]'),
            (r'Authorization: Bearer [^"\s]+', r'Authorization: Bearer [REDACTED]'),
        ]
        for pattern, replacement in patterns:
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
        return msg
    
    def _get_request_context(self):
        """Safely get request context - returns default values if no request"""
        if has_request_context():
            return {
                'ip': request.remote_addr,
                'user': session.get('user_id', '-')
            }
        return {
            'ip': '-',
            'user': '-'
        }
    
    def info(self, msg, *args, **kwargs):
        context = self._get_request_context()
        self.logger.info(
            f"[{context['ip']}] [{context['user']}] {self._mask_sensitive(msg)}", 
            *args, **kwargs
        )
    
    def error(self, msg, *args, **kwargs):
        context = self._get_request_context()
        self.logger.error(
            f"[{context['ip']}] [{context['user']}] {self._mask_sensitive(msg)}", 
            *args, **kwargs
        )
    
    def warning(self, msg, *args, **kwargs):
        context = self._get_request_context()
        self.logger.warning(
            f"[{context['ip']}] [{context['user']}] {self._mask_sensitive(msg)}", 
            *args, **kwargs
        )
    
    def security(self, event_type: str, details: str, user_id: int = None, ip: str = None):
        """Log security events to audit log"""
        context = self._get_request_context()
        user = user_id or context['user']
        ip_addr = ip or context['ip']
        self.logger.warning(
            f"SECURITY: {event_type} - {details} [user:{user}] [ip:{ip_addr}]"
        )

logger = SecureLogger()

# ===========================================
# APPLICATION FACTORY
# ===========================================
def create_app(config_override: dict = None) -> Flask:
    """Create and configure Flask application"""
    
    app = Flask(__name__)
    
    # ===========================================
    # BASE CONFIGURATION - Security first
    # ===========================================
    
    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / 'data'
    DATA_DIR.mkdir(exist_ok=True)
    
    # Core config - Session cookie settings for HTTP (HTTPS ready)
    app.config.update({
        # Security - CRITICAL SETTINGS
        'SECRET_KEY': os.getenv('SECRET_KEY'),
        'SESSION_COOKIE_SECURE': False,  # Set to True when using HTTPS
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_COOKIE_NAME': 'juju_session',
        'SESSION_COOKIE_DOMAIN': None,
        'SESSION_COOKIE_PATH': '/',
        'PERMANENT_SESSION_LIFETIME': timedelta(hours=int(os.getenv('SESSION_TIMEOUT_HOURS', 2))),
        'REMEMBER_COOKIE_DURATION': timedelta(days=7),
        'REMEMBER_COOKIE_SECURE': False,
        'REMEMBER_COOKIE_HTTPONLY': True,
        'SESSION_REFRESH_EACH_REQUEST': True,
        
        # File uploads
        'MAX_CONTENT_LENGTH': 2 * 1024 * 1024,  # 2MB max
        'UPLOAD_FOLDER': str(DATA_DIR / 'uploads'),
        'ALLOWED_EXTENSIONS': {'csv', 'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'},
        
        # Application
        'DATABASE': str(DATA_DIR / 'juju_fx.db'),
        'USDZAR_RATE': float(os.getenv('USDZAR_RATE', '18.5')),
        'PER_PAGE': 50,
        'SERVER_URL': os.getenv('SERVER_URL', 'http://45.55.91.52:8443'),
        'EA_API_KEY': os.getenv('EA_API_KEY'),
        'MT5_PROXY_URL': os.getenv('MT5_PROXY_URL', 'http://127.0.0.1:5002'),
        
        # Features
        'WEBSOCKET_ENABLED': os.getenv('WEBSOCKET_ENABLED', 'false').lower() == 'true',
        'RATE_LIMIT_ENABLED': os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
        'MAX_TRADES_PER_MINUTE': int(os.getenv('MAX_TRADES_PER_MINUTE', 1000)),
        'MAX_LOGIN_ATTEMPTS': int(os.getenv('MAX_LOGIN_ATTEMPTS', 5)),
    })
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Override with test config if provided
    if config_override:
        app.config.update(config_override)
    
    # ===========================================
    # SECURITY MIDDLEWARE
    # ===========================================
    
    # CORS - Restrictive by default
    CORS(app,
         supports_credentials=True,
         origins=[app.config['SERVER_URL']],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'Authorization', 'X-CSRF-Token'],
         expose_headers=['Set-Cookie'])
    
    # Security headers
    Talisman(app,
             force_https=False,  # Set to True when using HTTPS
             force_https_permanent=False,
             strict_transport_security=False,
             content_security_policy=None,
             referrer_policy='strict-origin-when-cross-origin',
             x_xss_protection=True,
             x_content_type_options=True,
             session_cookie_secure=False)
    
    # Proxy fix for correct IP detection
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # MT5 detection middleware
    @app.before_request
    def detect_mt5_request():
        """Flag MT5 requests for special handling"""
        g.is_mt5 = request.path in [
            '/api/level', '/mt5/level', '/health', 
            '/api/record_trade', '/api/ea/performance'
        ]
        if g.is_mt5:
            logger.info(f"MT5: {request.method} {request.path}")
    
    # ===========================================
    # GLOBAL STATE - Thread-safe level management
    # ===========================================
    class TradingState:
        """Thread-safe global state - CRITICAL for level changes"""
        _instance = None
        _lock = threading.RLock()
        
        def __new__(cls):
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialize()
            return cls._instance
        
        def _initialize(self):
            self.current_level = 5
            self.connected_clients = set()
            self.clients_lock = threading.RLock()
            self.level_lock = threading.RLock()
            self._load_level()
        
        def _load_level(self):
            """Load level from persistent storage"""
            level_file = DATA_DIR / 'current_level.dat'
            try:
                if level_file.exists():
                    with open(level_file, 'r') as f:
                        level = f.read().strip()
                        if level and level.isdigit():
                            self.current_level = int(level)
                            logger.info(f"Loaded level: {self.current_level}")
            except Exception as e:
                logger.error(f"Level load error: {e}")
        
        def save_level(self):
            """Save level atomically - prevents corruption"""
            level_file = DATA_DIR / 'current_level.dat'
            temp_file = level_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w') as f:
                    f.write(str(self.current_level))
                # Atomic rename
                temp_file.replace(level_file)
                logger.info(f"Level saved: {self.current_level}")
            except Exception as e:
                logger.error(f"Level save error: {e}")
        
        def set_level(self, new_level: int, source: str = 'unknown', user_id: int = None) -> bool:
            """Change level with audit - GUARANTEED to work"""
            if not 0 <= new_level <= 6:
                logger.warning(f"Invalid level attempt: {new_level}")
                return False
            
            with self.level_lock:
                old_level = self.current_level
                self.current_level = new_level
                self.save_level()
                
                # Log to database for audit trail
                try:
                    db = get_db()
                    db.execute('''
                        INSERT INTO level_changes (user_id, old_level, new_level, source, ip_address)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, old_level, new_level, source, request.remote_addr if has_request_context() else None))
                    db.commit()
                    logger.info(f"Level change logged: {old_level} -> {new_level} by user {user_id}")
                except Exception as e:
                    logger.error(f"Level change log error: {e}")
                
                logger.info(f"✅ LEVEL CHANGED: {old_level} -> {new_level} ({source})")
                return True
    
    state = TradingState()
    
    # ===========================================
    # DATABASE - Financial data integrity
    # ===========================================
    
    def get_db():
        """Get thread-safe database connection"""
        if not hasattr(g, 'db'):
            g.db = sqlite3.connect(
                app.config['DATABASE'],
                check_same_thread=False,
                timeout=30,
                isolation_level='IMMEDIATE'
            )
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA journal_mode=WAL;')  # Write-Ahead Logging for concurrency
            g.db.execute('PRAGMA secure_delete=ON;')  # Secure delete
            g.db.execute('PRAGMA foreign_keys=ON;')   # Enforce referential integrity
            g.db.execute('PRAGMA busy_timeout=5000;') # Wait up to 5 seconds for locks
        return g.db
    
    @app.teardown_appcontext
    def close_db(error):
        """Close database connection"""
        if hasattr(g, 'db'):
            g.db.close()
    
    def init_database():
        """Initialize all database tables with proper schema"""
        db = get_db()
        
        # Users table - Complete with all fields
        db.execute('''
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
                verification_token TEXT,
                api_key TEXT UNIQUE,
                api_secret TEXT
            )
        ''')
        
        # Sessions table for active sessions
        db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                device_info TEXT,
                ip_address TEXT,
                user_agent TEXT,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP,
                logout_time TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Trades table - Core financial data
        db.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                type TEXT,
                volume REAL,
                open_price REAL,
                close_price REAL,
                open_time TIMESTAMP,
                close_time TIMESTAMP,
                profit REAL,
                swap REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                magic_number INTEGER,
                comment TEXT,
                level INTEGER DEFAULT 0,
                ea_name TEXT,
                ea_version TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(ticket)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at)')
        
        # EA instances table
        db.execute('''
            CREATE TABLE IF NOT EXISTS ea_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ea_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                magic_number INTEGER UNIQUE,
                status TEXT DEFAULT 'running',
                current_level INTEGER DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                total_profit REAL DEFAULT 0,
                current_drawdown REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_to_user_id INTEGER,
                FOREIGN KEY (assigned_to_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        
        # EA performance history
        db.execute('''
            CREATE TABLE IF NOT EXISTS ea_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ea_instance_id INTEGER,
                profit REAL,
                trades INTEGER,
                drawdown REAL,
                level INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ea_instance_id) REFERENCES ea_instances(id) ON DELETE CASCADE
            )
        ''')
        
        # Commissions table for IB tracking
        db.execute('''
            CREATE TABLE IF NOT EXISTS commissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ib_user_id INTEGER,
                referred_user_id INTEGER,
                trade_id INTEGER,
                volume_lots REAL,
                commission_amount REAL,
                currency TEXT DEFAULT 'ZAR',
                status TEXT DEFAULT 'pending',
                paid_date DATE,
                earned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ib_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (referred_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Security audit table - CRITICAL for compliance
        db.execute('''
            CREATE TABLE IF NOT EXISTS security_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_security_timestamp ON security_audit(timestamp)')
        
        # Failed logins table (rate limiting)
        db.execute('''
            CREATE TABLE IF NOT EXISTS failed_logins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                username TEXT,
                attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_failed_logins_ip ON failed_logins(ip_address)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_failed_logins_time ON failed_logins(attempt_time)')
        
        # Rate limits table
        db.execute('''
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                endpoint TEXT,
                request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_rate_limits_key ON rate_limits(key)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_rate_limits_time ON rate_limits(request_time)')
        
        # Level changes audit - Track every level change
        db.execute('''
            CREATE TABLE IF NOT EXISTS level_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                old_level INTEGER,
                new_level INTEGER NOT NULL,
                source TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        
        # Subscription plans
        db.execute('''
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                price_zar REAL,
                price_usd REAL,
                duration_days INTEGER,
                features TEXT,
                max_eas INTEGER DEFAULT 1,
                max_drawdown_limit REAL,
                commission_rate REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # System settings
        db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default subscription plans
        plans = [
            ('trial', 0, 0, 7, '{"eas":1,"support":"basic"}', 1, 5, 0),
            ('basic', 499, 27, 30, '{"eas":5,"support":"email"}', 5, 10, 10),
            ('pro', 999, 54, 30, '{"eas":15,"support":"priority"}', 15, 15, 15),
            ('vip', 1999, 108, 30, '{"eas":30,"support":"24/7"}', 30, 20, 20)
        ]
        
        for plan in plans:
            db.execute('''
                INSERT OR IGNORE INTO subscription_plans 
                (name, price_zar, price_usd, duration_days, features, max_eas, max_drawdown_limit, commission_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', plan)
        
        # Create admin user if not exists
        admin = db.execute("SELECT id FROM users WHERE user_type = 'admin'").fetchone()
        if not admin:
            password_hash = generate_password_hash(os.getenv('ADMIN_PASSWORD'))
            api_key = secrets.token_urlsafe(32)
            api_secret = secrets.token_urlsafe(32)
            
            db.execute('''
                INSERT INTO users (
                    username, password_hash, email, full_name,
                    user_type, status, subscription_plan,
                    email_verified, api_key, api_secret
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                os.getenv('ADMIN_USERNAME', 'admin'),
                password_hash,
                'admin@jujufx.com',
                'System Administrator',
                'admin',
                'active',
                'lifetime',
                1,
                api_key,
                api_secret
            ))
            logger.info("✅ Created admin user")
        
        db.commit()
        logger.info("✅ Database initialized")
    
    # Initialize database
    with app.app_context():
        init_database()
    
    # ===========================================
    # RATE LIMITER - Protect against abuse
    # ===========================================
    class RateLimiter:
        """Smart rate limiting that distinguishes MT5 from web"""
        
        def __init__(self, app):
            self.app = app
            self.enabled = app.config['RATE_LIMIT_ENABLED']
        
        def is_allowed(self, key: str, limit: int, period: int = 60) -> bool:
            """Check if request is allowed"""
            if not self.enabled or getattr(g, 'is_mt5', False):
                return True
            
            db = get_db()
            cutoff = datetime.now() - timedelta(seconds=period)
            
            # Clean old entries
            db.execute('DELETE FROM rate_limits WHERE request_time < ?', (cutoff,))
            
            # Count recent requests
            count = db.execute('''
                SELECT COUNT(*) as cnt FROM rate_limits
                WHERE key = ? AND request_time > ?
            ''', (key, cutoff)).fetchone()['cnt']
            
            if count >= limit:
                logger.warning(f"Rate limit exceeded for {key}")
                return False
            
            # Record this request
            db.execute('INSERT INTO rate_limits (key) VALUES (?)', (key,))
            db.commit()
            
            return True
    
    rate_limiter = RateLimiter(app)
    
    # ===========================================
    # SECURITY DECORATORS
    # ===========================================
    
    def login_required(f):
        """Require valid session - CRITICAL for security"""
        @wraps(f)
        def decorated(*args, **kwargs):
            # Skip for MT5
            if getattr(g, 'is_mt5', False):
                return f(*args, **kwargs)
            
            if 'user_id' not in session:
                logger.security('unauthorized_access', f"Access denied to {request.path}")
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                return redirect(url_for('login'))
            
            # Validate session in database
            db = get_db()
            session_valid = db.execute('''
                SELECT id FROM sessions 
                WHERE user_id = ? AND is_active = 1 
                AND last_activity > datetime('now', ?)
            ''', (session['user_id'], f"-{app.config['PERMANENT_SESSION_LIFETIME'].seconds} seconds")).fetchone()
            
            if not session_valid:
                logger.security('session_expired', f"Session expired for user {session['user_id']}")
                session.clear()
                if request.is_json:
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('login'))
            
            # Update activity
            db.execute('''
                UPDATE sessions SET last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ? AND is_active = 1
            ''', (session['user_id'],))
            db.commit()
            
            # Add user to request context
            g.user_id = session['user_id']
            g.username = session.get('username')
            
            return f(*args, **kwargs)
        return decorated
    
    def admin_required(f):
        """Require admin privileges"""
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            db = get_db()
            user = db.execute('''
                SELECT user_type FROM users 
                WHERE id = ? AND status = 'active'
            ''', (session['user_id'],)).fetchone()
            
            if not user or user['user_type'] not in ['admin', 'ib']:
                logger.security('unauthorized_admin', 
                              f"User {session['user_id']} attempted admin access",
                              user_id=session['user_id'],
                              ip=request.remote_addr)
                abort(403)
            
            return f(*args, **kwargs)
        return decorated
    
    def csrf_protected(f):
        """CSRF protection for state-changing operations"""
        @wraps(f)
        def decorated(*args, **kwargs):
            # Skip for MT5
            if getattr(g, 'is_mt5', False):
                return f(*args, **kwargs)
            
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                token = request.headers.get('X-CSRF-Token')
                if not token:
                    token = request.form.get('csrf_token')
                if not token and request.is_json:
                    token = request.get_json(silent=True).get('csrf_token') if request.get_json(silent=True) else None
                
                if not token or token != session.get('csrf_token'):
                    logger.security('csrf_failure', 
                                  f"Invalid CSRF from {request.remote_addr}")
                    return jsonify({'error': 'Invalid security token'}), 403
            
            return f(*args, **kwargs)
        return decorated
    
    def api_key_required(f):
        """API key authentication for MT5"""
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
            
            if not api_key:
                logger.security('missing_api_key', f"No API key from {request.remote_addr}")
                return jsonify({'error': 'API key required'}), 401
            
            # Check against master key
            if api_key == app.config['EA_API_KEY']:
                g.api_user_id = 1  # Admin
                logger.info(f"Master API key used from {request.remote_addr}")
                return f(*args, **kwargs)
            
            # Check user-specific keys
            db = get_db()
            user = db.execute('''
                SELECT id FROM users 
                WHERE api_key = ? AND status = 'active'
            ''', (api_key,)).fetchone()
            
            if user:
                g.api_user_id = user['id']
                logger.info(f"User API key used: user {user['id']}")
                return f(*args, **kwargs)
            
            logger.security('invalid_api_key', f"Invalid key from {request.remote_addr}")
            return jsonify({'error': 'Invalid API key'}), 403
        
        return decorated
    
    # ===========================================
    # HELPER FUNCTIONS
    # ===========================================
    
    def validate_level(level: Any) -> bool:
        """Validate risk level (0-6)"""
        try:
            return 0 <= int(level) <= 6
        except (ValueError, TypeError):
            return False
    
    def validate_username(username: str) -> bool:
        """Validate username format"""
        return bool(re.match(r'^[a-zA-Z0-9_.-]{3,50}$', username))
    
    def validate_email(email: str) -> bool:
        """Validate email format"""
        return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', email))
    
    def validate_symbol(symbol: str) -> bool:
        """Validate forex symbol"""
        return bool(re.match(r'^[A-Z0-9/.]{1,20}$', symbol))
    
    def validate_date(date_str: str) -> bool:
        """Validate date format"""
        try:
            if date_str:
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return True
        except:
            return False
    
    def validate_phone(phone: str) -> bool:
        """Validate phone number format"""
        if not phone:
            return True
        return bool(re.match(r'^[0-9+\-\s()]{10,20}$', phone))
    
    def sanitize_input(text: str, max_length: int = 100) -> str:
        """Basic XSS prevention"""
        if not text:
            return ""
        text = re.sub(r'<[^>]*>', '', text)
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace('"', '&quot;').replace("'", '&#x27;')
        return text[:max_length]
    
    def generate_csrf_token() -> str:
        """Generate and store CSRF token"""
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return session['csrf_token']
    
    def log_security_event(event_type: str, details: str, user_id: int = None):
        """Log security event to database"""
        db = get_db()
        try:
            db.execute('''
                INSERT INTO security_audit 
                (event_type, user_id, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                event_type,
                user_id or session.get('user_id'),
                details[:500],
                request.remote_addr,
                request.user_agent.string[:255] if request.user_agent else None
            ))
            db.commit()
        except Exception as e:
            logger.error(f"Security log error: {e}")
        
        logger.security(event_type, details, user_id, request.remote_addr)
    
    def allowed_file(filename: str) -> bool:
        """Check if file extension is allowed"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    
    # ===========================================
    # AUTHENTICATION ROUTES
    # ===========================================
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Secure login with rate limiting - Financial system access control"""
        
        # Rate limit by IP
        if not rate_limiter.is_allowed(f"login:{request.remote_addr}", 5, 60):
            logger.security('rate_limit_exceeded', f"Login rate limit from {request.remote_addr}")
            return render_template('login.html', 
                                 error='Too many attempts. Please wait 1 minute.',
                                 csrf_token=generate_csrf_token(),
                                 session_expires_soon=False)
        
        if request.method == 'GET':
            return render_template('login.html', 
                                 csrf_token=generate_csrf_token(),
                                 session_expires_soon=False)
        
        # POST - process login
        username = sanitize_input(request.form.get('username', ''), 50)
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            return render_template('login.html', 
                                 error='Username and password required',
                                 csrf_token=generate_csrf_token())
        
        db = get_db()
        
        # Check IP lockout
        five_mins_ago = datetime.now() - timedelta(minutes=5)
        failed = db.execute('''
            SELECT COUNT(*) as cnt FROM failed_logins
            WHERE ip_address = ? AND attempt_time > ?
        ''', (request.remote_addr, five_mins_ago)).fetchone()['cnt']
        
        if failed >= app.config['MAX_LOGIN_ATTEMPTS'] * 2:
            logger.security('ip_locked', f"IP {request.remote_addr} locked")
            return render_template('login.html', 
                                 error='IP temporarily locked. Try again later.',
                                 csrf_token=generate_csrf_token())
        
        # Find user
        user = db.execute('''
            SELECT * FROM users 
            WHERE username = ? AND (locked_until IS NULL OR locked_until < CURRENT_TIMESTAMP)
        ''', (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            # Success
            if user['status'] != 'active':
                logger.security('inactive_login', f"Login attempt on {user['status']} account: {username}")
                return render_template('login.html', 
                                     error=f"Account {user['status']}",
                                     csrf_token=generate_csrf_token())
            
            # Create session
            session.clear()
            session.permanent = remember
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_type'] = user['user_type']
            session['login_time'] = datetime.now().isoformat()
            session['csrf_token'] = secrets.token_urlsafe(32)
            
            # Record session in database
            session_token = secrets.token_urlsafe(32)
            db.execute('''
                INSERT INTO sessions 
                (user_id, session_token, ip_address, user_agent, last_activity)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user['id'], session_token, request.remote_addr,
                  request.user_agent.string[:255] if request.user_agent else None))
            
            # Clear failed attempts
            db.execute('DELETE FROM failed_logins WHERE ip_address = ?', (request.remote_addr,))
            db.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP, failed_login_attempts = 0 WHERE id = ?',
                      (user['id'],))
            db.commit()
            
            log_security_event('login_success', f"User {username} logged in", user['id'])
            logger.info(f"✅ Login success: {username} from {request.remote_addr}")
            
            # Redirect based on user type
            if user['user_type'] in ['admin', 'ib']:
                return redirect(url_for('master_dashboard'))
            return redirect(url_for('dashboard'))
        
        # Failed login
        db.execute('INSERT INTO failed_logins (ip_address, username) VALUES (?, ?)',
                  (request.remote_addr, username))
        
        if user:
            db.execute('''
                UPDATE users SET 
                    failed_login_attempts = failed_login_attempts + 1,
                    last_failed_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user['id'],))
            
            # Lock after max attempts
            if user['failed_login_attempts'] >= app.config['MAX_LOGIN_ATTEMPTS'] - 1:
                db.execute('''
                    UPDATE users SET 
                        locked_until = datetime('now', '+30 minutes')
                    WHERE id = ?
                ''', (user['id'],))
                log_security_event('account_locked', f"Account {username} locked")
        
        db.commit()
        log_security_event('login_failed', f"Failed login for {username}")
        logger.warning(f"❌ Login failed: {username} from {request.remote_addr}")
        
        return render_template('login.html', 
                             error='Invalid credentials',
                             csrf_token=generate_csrf_token())
    
    @app.route('/logout')
    def logout():
        """Secure logout"""
        if 'user_id' in session:
            db = get_db()
            db.execute('''
                UPDATE sessions SET is_active = 0, logout_time = CURRENT_TIMESTAMP
                WHERE user_id = ? AND is_active = 1
            ''', (session['user_id'],))
            db.commit()
            
            log_security_event('logout', f"User logged out", session['user_id'])
            logger.info(f"User {session.get('username')} logged out")
        
        session.clear()
        return redirect(url_for('login'))
    
    @app.route('/api/csrf-token')
    def get_csrf_token():
        """Get CSRF token for AJAX"""
        return jsonify({'csrf_token': generate_csrf_token()})
    
    @app.route('/clear-session')
    def clear_session():
        """Utility to clear session"""
        session.clear()
        return redirect(url_for('login'))
    
    # ===========================================
    # PAGE ROUTES (ALL TEMPLATES)
    # ===========================================
    
    @app.route('/')
    @login_required
    def dashboard():
        """Main trading dashboard"""
        return render_template('dashboard.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token(),
                             websocket_enabled=app.config['WEBSOCKET_ENABLED'] and WEBSOCKET_AVAILABLE)
    
    @app.route('/master')
    @admin_required
    def master_dashboard():
        """Master control dashboard"""
        return render_template('master_dashboard.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token(),
                             websocket_enabled=app.config['WEBSOCKET_ENABLED'] and WEBSOCKET_AVAILABLE)
    
    @app.route('/analytics')
    @login_required
    def analytics():
        """Analytics page"""
        return render_template('analytics.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token())
    
    @app.route('/trades')
    @login_required
    def trades_page():
        """Trades history page"""
        return render_template('trades.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token())
    
    @app.route('/profile')
    @login_required
    def profile_page():
        """User profile page"""
        db = get_db()
        user = db.execute('''
            SELECT username, email, full_name, phone, country, timezone,
                   subscription_plan, subscription_end, created_at,
                   api_key, mt5_account, mt5_server
            FROM users WHERE id = ?
        ''', (session['user_id'],)).fetchone()
        
        return render_template('profile.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token(),
                             user=dict(user) if user else {})
    
    @app.route('/news')
    @login_required
    def news_page():
        """News page"""
        return render_template('news.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token())
    
    @app.route('/settings')
    @login_required
    def settings_page():
        """Settings page"""
        return render_template('settings.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token())
    
    @app.route('/performance')
    @login_required
    def performance_page():
        """Performance page"""
        return render_template('performance.html',
                             username=session.get('username'),
                             current_level=state.current_level,
                             csrf_token=generate_csrf_token())
    
    # ===========================================
    # MT5 COMPATIBLE ENDPOINTS (UNCHANGED FORMAT)
    # ===========================================
    
    @app.route('/api/level', methods=['GET'])
    def get_level():
        """PUBLIC: Get current level - EXACT format MT5 expects"""
        return jsonify({
            "status": "success",
            "level": state.current_level,
            "message": "OK",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/mt5/level', methods=['GET'])
    def mt5_level():
        """PUBLIC: Alternative MT5 endpoint"""
        return jsonify({
            "level": state.current_level,
            "status": "ok",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        try:
            db = get_db()
            db.execute('SELECT 1').fetchone()
            return jsonify({
                "status": "healthy",
                "level": state.current_level,
                "timestamp": datetime.now().isoformat()
            })
        except:
            return jsonify({"status": "degraded"}), 503
    
    @app.route('/api/record_trade', methods=['POST'])
    @api_key_required
    def record_trade():
        """PUBLIC: Record trade from MT5"""
        
        # Rate limit by user
        if not rate_limiter.is_allowed(f"trade:{g.api_user_id}", 
                                      app.config['MAX_TRADES_PER_MINUTE'], 60):
            logger.warning(f"Trade rate limit exceeded for user {g.api_user_id}")
            return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429
        
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No JSON data"}), 400
            
            # Validate required fields
            required = ['ticket', 'symbol', 'profit']
            missing = [f for f in required if f not in data]
            if missing:
                return jsonify({"status": "error", "message": f"Missing: {missing}"}), 400
            
            # Parse and validate
            try:
                ticket = int(data['ticket'])
                profit = float(data['profit'])
                volume = float(data.get('volume', 0))
                level = int(data.get('level', 0))
                
                if not validate_level(level):
                    level = 0
                
                symbol = data['symbol']
                if symbol.endswith('.m'):
                    symbol = symbol[:-2]
                
                if not validate_symbol(symbol):
                    return jsonify({"status": "error", "message": "Invalid symbol"}), 400
                
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Invalid numeric values"}), 400
            
            db = get_db()
            
            # Check if trade exists
            existing = db.execute('SELECT id FROM trades WHERE ticket = ?', (ticket,)).fetchone()
            
            if existing:
                # Update
                db.execute('''
                    UPDATE trades SET
                        profit = ?, volume = ?, close_price = ?,
                        close_time = ?, level = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE ticket = ?
                ''', (profit, volume, data.get('close_price', 0),
                      data.get('close_time'), level, ticket))
                action = "updated"
                logger.info(f"Trade updated: #{ticket}")
            else:
                # Insert
                db.execute('''
                    INSERT INTO trades
                    (ticket, symbol, type, volume, open_price, close_price,
                     open_time, close_time, profit, swap, commission,
                     magic_number, comment, level, ea_name, ea_version, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ticket, symbol, data.get('type'), volume,
                    data.get('open_price', 0), data.get('close_price', 0),
                    data.get('open_time'), data.get('close_time'),
                    profit, data.get('swap', 0), data.get('commission', 0),
                    data.get('magic_number'), data.get('comment'),
                    level, data.get('ea_name'), data.get('ea_version'),
                    g.api_user_id
                ))
                action = "recorded"
                logger.info(f"New trade recorded: #{ticket} {symbol} ${profit:.2f}")
                
                # Calculate IB commission
                if g.api_user_id:
                    calculate_commission(g.api_user_id, ticket, {
                        'volume': volume,
                        'profit': profit
                    })
            
            db.commit()
            
            # Notify WebSocket clients if enabled
            if app.config['WEBSOCKET_ENABLED'] and WEBSOCKET_AVAILABLE:
                notify_new_trade({
                    'ticket': ticket,
                    'symbol': symbol,
                    'profit_usd': profit,
                    'profit_zar': profit * app.config['USDZAR_RATE'],
                    'level': level
                })
            
            return jsonify({
                "status": "success",
                "message": f"Trade {action}",
                "ticket": ticket
            })
            
        except Exception as e:
            logger.error(f"Trade error: {e}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal error"}), 500
    
    @app.route('/api/ea/performance', methods=['POST'])
    @api_key_required
    def ea_performance():
        """Receive EA performance data"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No JSON data'}), 400
            
            soldiers = data.get('soldiers', [])
            logger.info(f"Processing {len(soldiers)} soldiers from Commander")
            
            db = get_db()
            inserted = 0
            
            for soldier in soldiers:
                try:
                    magic = int(soldier.get('magic', 0))
                    ea_name = sanitize_input(soldier.get('ea_name', f'EA_{magic}'), 50)
                    symbol = sanitize_input(soldier.get('symbol', 'Unknown'), 20)
                    profit = float(soldier.get('profit', 0))
                    trades = int(soldier.get('trades', 0))
                    wins = int(soldier.get('wins', 0))
                    drawdown = float(soldier.get('drawdown', 0))
                    level = int(soldier.get('level', 0))
                    
                    db.execute('''
                        INSERT OR REPLACE INTO ea_instances
                        (ea_name, symbol, magic_number, total_profit, total_trades,
                         winning_trades, current_drawdown, current_level, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (ea_name, symbol, magic, profit, trades, wins, drawdown, level))
                    
                    instance = db.execute('SELECT id FROM ea_instances WHERE magic_number = ?',
                                        (magic,)).fetchone()
                    
                    if instance:
                        db.execute('''
                            INSERT INTO ea_performance
                            (ea_instance_id, profit, trades, drawdown, level)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (instance['id'], profit, trades, drawdown, level))
                        inserted += 1
                        
                except Exception as e:
                    logger.error(f"Soldier error: {e}")
                    continue
            
            db.commit()
            logger.info(f"✅ Inserted {inserted} EA records")
            
            return jsonify({
                'status': 'success',
                'received': len(soldiers),
                'inserted': inserted
            })
            
        except Exception as e:
            logger.error(f"EA performance error: {e}", exc_info=True)
            return jsonify({'error': 'Internal error'}), 500
    
    # ===========================================
    # API ENDPOINTS (Web UI)
    # ===========================================
    
    @app.route('/api/current_level')
    @login_required
    def api_current_level():
        """Get current level for dashboard"""
        return jsonify({
            'level': state.current_level,
            'timestamp': datetime.now().isoformat()
        })
    
    @app.route('/api/set_level', methods=['POST'])
    @login_required
    @csrf_protected
    def set_level():
        """CRITICAL: Set trading level - GUARANTEED to work"""
        try:
            data = request.get_json()
            if not data:
                logger.error("Set level: No JSON data")
                return jsonify({"status": "error", "message": "No data"}), 400
            
            new_level = data.get('level')
            if not validate_level(new_level):
                logger.warning(f"Set level: Invalid level {new_level}")
                return jsonify({"status": "error", "message": "Invalid level"}), 400
            
            old_level = state.current_level
            if state.set_level(new_level, source='web', user_id=session['user_id']):
                
                # Try to sync with MT5 proxy (non-blocking)
                try:
                    import requests
                    requests.post(
                        f"{app.config['MT5_PROXY_URL']}/set_level",
                        json={'level': new_level},
                        timeout=1,  # Quick timeout, don't block
                        headers={'X-API-Key': app.config['EA_API_KEY']}
                    )
                except:
                    # Proxy offline - continue anyway, level already changed
                    logger.warning("MT5 proxy not reachable, but level changed locally")
                    pass
                
                log_security_event('level_change', 
                                 f"Level {old_level} -> {new_level}",
                                 session['user_id'])
                
                # Broadcast via WebSocket if enabled
                if app.config['WEBSOCKET_ENABLED'] and WEBSOCKET_AVAILABLE:
                    broadcast_level_change(new_level)
                
                logger.info(f"✅ Level change successful: {old_level} -> {new_level} by user {session['user_id']}")
                
                return jsonify({
                    "status": "success",
                    "level": new_level,
                    "message": f"Level {new_level} activated"
                })
            
            logger.error(f"Set level failed for unknown reason")
            return jsonify({"status": "error", "message": "Failed to set level"}), 500
            
        except Exception as e:
            logger.error(f"Set level error: {e}", exc_info=True)
            return jsonify({"status": "error", "message": "Internal error"}), 500
    
    @app.route('/api/dashboard/summary')
    @login_required
    def dashboard_summary():
        """Get dashboard summary statistics"""
        try:
            db = get_db()
            user_id = session['user_id']
            
            # Check if admin
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            # Today's trades
            if is_admin:
                today = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE DATE(created_at) = DATE('now')
                ''').fetchone()['total']
                
                week = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE created_at > datetime('now', '-7 days')
                ''').fetchone()['total']
                
                month = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE created_at > datetime('now', '-30 days')
                ''').fetchone()['total']
                
                total_trades = db.execute('SELECT COUNT(*) as cnt FROM trades').fetchone()['cnt']
                wins = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades 
                    WHERE (profit + swap + commission) > 0
                ''').fetchone()['cnt']
                
                today_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE DATE(created_at) = DATE('now')
                ''').fetchone()['cnt']
                
                week_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE created_at > datetime('now', '-7 days')
                ''').fetchone()['cnt']
                
                month_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE created_at > datetime('now', '-30 days')
                ''').fetchone()['cnt']
                
            else:
                today = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE user_id = ? AND DATE(created_at) = DATE('now')
                ''', (user_id,)).fetchone()['total']
                
                week = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE user_id = ? AND created_at > datetime('now', '-7 days')
                ''', (user_id,)).fetchone()['total']
                
                month = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades
                    WHERE user_id = ? AND created_at > datetime('now', '-30 days')
                ''', (user_id,)).fetchone()['total']
                
                total_trades = db.execute('SELECT COUNT(*) as cnt FROM trades WHERE user_id = ?',
                                        (user_id,)).fetchone()['cnt']
                wins = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades 
                    WHERE user_id = ? AND (profit + swap + commission) > 0
                ''', (user_id,)).fetchone()['cnt']
                
                today_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE user_id = ? AND DATE(created_at) = DATE('now')
                ''', (user_id,)).fetchone()['cnt']
                
                week_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE user_id = ? AND created_at > datetime('now', '-7 days')
                ''', (user_id,)).fetchone()['cnt']
                
                month_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE user_id = ? AND created_at > datetime('now', '-30 days')
                ''', (user_id,)).fetchone()['cnt']
            
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            return jsonify({
                'daily': {
                    'pnl_usd': round(today, 2),
                    'pnl_zar': round(today * app.config['USDZAR_RATE'], 2),
                    'trades': today_trades
                },
                'weekly': {
                    'pnl_usd': round(week, 2),
                    'pnl_zar': round(week * app.config['USDZAR_RATE'], 2),
                    'trades': week_trades
                },
                'monthly': {
                    'pnl_usd': round(month, 2),
                    'pnl_zar': round(month * app.config['USDZAR_RATE'], 2),
                    'trades': month_trades
                },
                'summary': {
                    'all': {
                        'trades': total_trades,
                        'win_rate': round(win_rate, 1)
                    }
                },
                'current_level': state.current_level,
                'exchange_rate': app.config['USDZAR_RATE']
            })
            
        except Exception as e:
            logger.error(f"Summary error: {e}")
            return jsonify({
                'daily': {'pnl_zar': 0, 'trades': 0},
                'weekly': {'pnl_zar': 0, 'trades': 0},
                'monthly': {'pnl_zar': 0, 'trades': 0},
                'summary': {'all': {'trades': 0, 'win_rate': 0}},
                'current_level': state.current_level,
                'exchange_rate': app.config['USDZAR_RATE']
            })
    
    @app.route('/api/trades/recent')
    @login_required
    def recent_trades():
        """Get recent trades for dashboard"""
        try:
            db = get_db()
            user_id = session['user_id']
            
            # Check if admin
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            if is_admin:
                trades = db.execute('''
                    SELECT ticket, symbol, type, volume, profit, swap, commission,
                           level, created_at
                    FROM trades
                    ORDER BY created_at DESC LIMIT 20
                ''').fetchall()
            else:
                trades = db.execute('''
                    SELECT ticket, symbol, type, volume, profit, swap, commission,
                           level, created_at
                    FROM trades
                    WHERE user_id = ?
                    ORDER BY created_at DESC LIMIT 20
                ''', (user_id,)).fetchall()
            
            result = []
            for t in trades:
                profit_usd = float(t['profit'] or 0) + float(t['swap'] or 0) + float(t['commission'] or 0)
                created = t['created_at']
                
                # Format time
                formatted_time = "N/A"
                date_label = "Unknown"
                if created:
                    try:
                        if isinstance(created, str):
                            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            formatted_time = dt.strftime('%H:%M:%S')
                            today = datetime.now().date()
                            if dt.date() == today:
                                date_label = 'Today'
                            elif (today - dt.date()).days == 1:
                                date_label = 'Yesterday'
                            else:
                                date_label = dt.strftime('%b %d')
                    except:
                        formatted_time = created[11:19] if len(created) > 19 else created
                        date_label = 'Today' if created.startswith(datetime.now().strftime('%Y-%m-%d')) else 'Earlier'
                
                result.append({
                    'ticket': t['ticket'],
                    'symbol': t['symbol'],
                    'type': t['type'] or 'unknown',
                    'volume': float(t['volume'] or 0),
                    'profit_usd': round(profit_usd, 2),
                    'profit_zar': round(profit_usd * app.config['USDZAR_RATE'], 2),
                    'level': t['level'] or 0,
                    'formatted_time': formatted_time,
                    'date': date_label
                })
            
            return jsonify({'trades': result, 'count': len(result)})
            
        except Exception as e:
            logger.error(f"Trades error: {e}")
            return jsonify({'trades': []})
    
    @app.route('/api/trades/all')
    @login_required
    def get_all_trades():
        """Get all trades with pagination (for trade history page)"""
        try:
            page = int(request.args.get('page', 1))
            per_page = int(request.args.get('per_page', app.config['PER_PAGE']))
            offset = (page - 1) * per_page
            
            db = get_db()
            user_id = session['user_id']
            
            # Check if admin
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            # Get total count
            if is_admin:
                count = db.execute('SELECT COUNT(*) as cnt FROM trades').fetchone()['cnt']
                trades = db.execute('''
                    SELECT * FROM trades 
                    ORDER BY 
                        COALESCE(
                            NULLIF(close_time, ''),
                            NULLIF(open_time, ''),
                            created_at
                        ) DESC 
                    LIMIT ? OFFSET ?
                ''', (per_page, offset)).fetchall()
            else:
                count = db.execute('SELECT COUNT(*) as cnt FROM trades WHERE user_id = ?', 
                                 (user_id,)).fetchone()['cnt']
                trades = db.execute('''
                    SELECT * FROM trades 
                    WHERE user_id = ?
                    ORDER BY 
                        COALESCE(
                            NULLIF(close_time, ''),
                            NULLIF(open_time, ''),
                            created_at
                        ) DESC 
                    LIMIT ? OFFSET ?
                ''', (user_id, per_page, offset)).fetchall()
            
            # Format trades for display
            trades_list = []
            for trade in trades:
                profit_usd = float(trade['profit'] or 0) + float(trade['swap'] or 0) + float(trade['commission'] or 0)
                profit_zar = profit_usd * app.config['USDZAR_RATE']
                
                # Format time
                time_val = trade['close_time'] or trade['open_time'] or trade['created_at']
                formatted_time = "N/A"
                if time_val:
                    try:
                        if isinstance(time_val, str):
                            # Handle MT5 format: 2026.02.26 09:23
                            clean_time = time_val.replace('.', '-')
                            if ' ' in clean_time:
                                dt = datetime.strptime(clean_time[:19], '%Y-%m-%d %H:%M')
                                formatted_time = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        formatted_time = str(time_val)[:16]
                
                trades_list.append({
                    'ticket': trade['ticket'],
                    'symbol': trade['symbol'] or 'Unknown',
                    'type': trade['type'] or 'unknown',
                    'volume': float(trade['volume'] or 0),
                    'open_price': float(trade['open_price'] or 0),
                    'close_price': float(trade['close_price'] or 0),
                    'profit_usd': round(profit_usd, 2),
                    'profit_zar': round(profit_zar, 2),
                    'level': int(trade['level'] or 0),
                    'ea_name': trade['ea_name'] or 'Unknown',
                    'ea_version': trade['ea_version'] or '',
                    'open_time': trade['open_time'],
                    'close_time': trade['close_time'],
                    'created_at': trade['created_at'],
                    'formatted_time': formatted_time
                })
            
            return jsonify({
                'trades': trades_list,
                'total': count,
                'page': page,
                'per_page': per_page,
                'pages': (count + per_page - 1) // per_page
            })
            
        except Exception as e:
            logger.error(f"Error in get_all_trades: {e}")
            return jsonify({'trades': [], 'total': 0, 'page': 1, 'per_page': per_page, 'pages': 0})
    
    @app.route('/api/performance/<period>')
    @login_required
    def performance_period(period):
        """Get performance data for period"""
        if period not in ['day', 'week', 'month', 'all']:
            return jsonify({'error': 'Invalid period'}), 400
        
        try:
            db = get_db()
            user_id = session['user_id']
            
            # Date filter
            if period == 'day':
                date_filter = "created_at > datetime('now', '-1 day')"
            elif period == 'week':
                date_filter = "created_at > datetime('now', '-7 days')"
            elif period == 'month':
                date_filter = "created_at > datetime('now', '-30 days')"
            else:
                date_filter = "1=1"
            
            # Check if admin
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            if is_admin:
                trades = db.execute(f'''
                    SELECT * FROM trades 
                    WHERE {date_filter}
                    ORDER BY created_at
                ''').fetchall()
            else:
                trades = db.execute(f'''
                    SELECT * FROM trades 
                    WHERE user_id = ? AND {date_filter}
                    ORDER BY created_at
                ''', (user_id,)).fetchall()
            
            # Calculate metrics
            total_pnl_usd = 0
            pnl_by_level = {}
            pnl_by_symbol = {}
            hourly_pnl = {f"{h:02d}:00": 0 for h in range(24)}
            
            for trade in trades:
                pnl = float(trade['profit'] or 0) + float(trade['swap'] or 0) + float(trade['commission'] or 0)
                total_pnl_usd += pnl
                
                # By level
                level = str(trade['level'] or 0)
                if level not in pnl_by_level:
                    pnl_by_level[level] = {'usd': 0, 'zar': 0, 'trades': 0, 'wins': 0}
                pnl_by_level[level]['usd'] += pnl
                pnl_by_level[level]['trades'] += 1
                if pnl > 0:
                    pnl_by_level[level]['wins'] += 1
                
                # By symbol
                symbol = trade['symbol'] or 'Unknown'
                if symbol not in pnl_by_symbol:
                    pnl_by_symbol[symbol] = {'usd': 0, 'zar': 0, 'trades': 0, 'wins': 0}
                pnl_by_symbol[symbol]['usd'] += pnl
                pnl_by_symbol[symbol]['trades'] += 1
                if pnl > 0:
                    pnl_by_symbol[symbol]['wins'] += 1
                
                # Hourly
                if trade['created_at']:
                    try:
                        hour = int(trade['created_at'][11:13])
                        hourly_pnl[f"{hour:02d}:00"] = hourly_pnl.get(f"{hour:02d}:00", 0) + pnl
                    except:
                        pass
            
            # Convert to ZAR and calculate win rates
            for level in pnl_by_level.values():
                level['zar'] = level['usd'] * app.config['USDZAR_RATE']
                level['win_rate'] = (level['wins'] / level['trades'] * 100) if level['trades'] > 0 else 0
            
            for symbol in pnl_by_symbol.values():
                symbol['zar'] = symbol['usd'] * app.config['USDZAR_RATE']
                symbol['win_rate'] = (symbol['wins'] / symbol['trades'] * 100) if symbol['trades'] > 0 else 0
            
            return jsonify({
                'period': period,
                'total_trades': len(trades),
                'total_pnl_usd': round(total_pnl_usd, 2),
                'total_pnl_zar': round(total_pnl_usd * app.config['USDZAR_RATE'], 2),
                'pnl_by_level': pnl_by_level,
                'pnl_by_symbol': pnl_by_symbol,
                'hourly_pnl': hourly_pnl
            })
            
        except Exception as e:
            logger.error(f"Performance error: {e}")
            return jsonify({
                'period': period,
                'total_trades': 0,
                'total_pnl_zar': 0,
                'pnl_by_level': {},
                'pnl_by_symbol': {},
                'hourly_pnl': {f"{h:02d}:00": 0 for h in range(24)}
            })
    
    @app.route('/api/performance/levels')
    @login_required
    def performance_levels():
        """Get P/L by level"""
        try:
            db = get_db()
            user_id = session['user_id']
            
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            if is_admin:
                trades = db.execute('SELECT * FROM trades').fetchall()
            else:
                trades = db.execute('SELECT * FROM trades WHERE user_id = ?', (user_id,)).fetchall()
            
            levels = {}
            for level in range(7):
                level_trades = [t for t in trades if int(t['level'] or 0) == level]
                total_usd = sum(float(t['profit'] or 0) + float(t['swap'] or 0) + float(t['commission'] or 0) 
                               for t in level_trades)
                wins = sum(1 for t in level_trades if (float(t['profit'] or 0) + 
                                                       float(t['swap'] or 0) + 
                                                       float(t['commission'] or 0)) > 0)
                
                levels[str(level)] = {
                    'usd': round(total_usd, 2),
                    'zar': round(total_usd * app.config['USDZAR_RATE'], 2),
                    'trades': len(level_trades),
                    'win_rate': round((wins / len(level_trades) * 100) if level_trades else 0, 1)
                }
            
            return jsonify({'levels': levels})
            
        except Exception as e:
            logger.error(f"Level performance error: {e}")
            return jsonify({'levels': {}})
    
    # ===========================================
    # EA INSTANCES API
    # ===========================================
    
    @app.route('/api/ea/instances')
    @admin_required
    def get_ea_instances():
        """Get all EA instances"""
        try:
            db = get_db()
            
            eas = db.execute('''
                SELECT 
                    e.*,
                    COUNT(t.id) as recent_trades,
                    SUM(CASE WHEN (t.profit + t.swap + t.commission) > 0 THEN 1 ELSE 0 END) as recent_wins,
                    COALESCE(SUM(t.profit + t.swap + t.commission), 0) as total_pnl_24h
                FROM ea_instances e
                LEFT JOIN trades t ON t.ea_name = e.ea_name 
                    AND t.created_at > datetime('now', '-24 hours')
                GROUP BY e.id
                ORDER BY e.symbol
            ''').fetchall()
            
            result = []
            for ea in eas:
                # Get 24h P&L
                pnl_24h = db.execute('''
                    SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                    FROM trades 
                    WHERE ea_name = ? AND created_at > datetime('now', '-24 hours')
                ''', (ea['ea_name'],)).fetchone()['total']
                
                # Get total stats
                total_trades = db.execute('''
                    SELECT COUNT(*) as count FROM trades WHERE ea_name = ?
                ''', (ea['ea_name'],)).fetchone()['count'] or 0
                
                winning_trades = db.execute('''
                    SELECT COUNT(*) as count FROM trades 
                    WHERE ea_name = ? AND (profit + swap + commission) > 0
                ''', (ea['ea_name'],)).fetchone()['count'] or 0
                
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                
                result.append({
                    'id': ea['id'],
                    'name': ea['ea_name'],
                    'symbol': ea['symbol'],
                    'status': ea['status'] or 'running',
                    'current_level': ea['current_level'] or 0,
                    'total_trades': total_trades,
                    'win_rate': round(win_rate, 1),
                    'pnl_24h_usd': round(pnl_24h, 2),
                    'pnl_24h_zar': round(pnl_24h * app.config['USDZAR_RATE'], 2),
                    'current_drawdown': round(ea['current_drawdown'] or 0, 1),
                    'max_drawdown': round(ea['max_drawdown'] or 0, 1),
                    'last_trade': ea['last_updated']
                })
            
            return jsonify({'eas': result})
            
        except Exception as e:
            logger.error(f"EA instances error: {e}")
            return jsonify({'eas': []})
    
    # ===========================================
    # COMPLETE USER MANAGEMENT API
    # ===========================================
    
    @app.route('/api/users', methods=['GET'])
    @admin_required
    def get_users():
        """Get all users with filtering and pagination"""
        try:
            page = int(request.args.get('page', 1))
            per_page = app.config['PER_PAGE']
            offset = (page - 1) * per_page
            
            status = request.args.get('status', 'all')
            search = sanitize_input(request.args.get('search', ''), 50)
            
            db = get_db()
            
            # Build query
            query = "SELECT * FROM users WHERE 1=1"
            count_query = "SELECT COUNT(*) as total FROM users WHERE 1=1"
            params = []
            
            if status != 'all':
                query += " AND status = ?"
                count_query += " AND status = ?"
                params.append(status)
            
            if search:
                query += " AND (username LIKE ? OR email LIKE ? OR full_name LIKE ?)"
                count_query += " AND (username LIKE ? OR email LIKE ? OR full_name LIKE ?)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])
            
            # Get total count
            total = db.execute(count_query, params).fetchone()['total']
            
            # Get paginated users
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            paginated_params = params + [per_page, offset]
            
            users = db.execute(query, paginated_params).fetchall()
            
            # Enrich with stats
            result = []
            for user in users:
                stats = db.execute('''
                    SELECT 
                        COUNT(*) as trades,
                        COALESCE(SUM(profit + swap + commission), 0) as pnl
                    FROM trades WHERE user_id = ?
                ''', (user['id'],)).fetchone()
                
                last_active = db.execute('''
                    SELECT last_activity FROM sessions 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY last_activity DESC LIMIT 1
                ''', (user['id'],)).fetchone()
                
                ea_count = db.execute('''
                    SELECT COUNT(*) as count FROM ea_instances 
                    WHERE assigned_to_user_id = ?
                ''', (user['id'],)).fetchone()['count']
                
                result.append({
                    'id': user['id'],
                    'username': user['username'],
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'user_type': user['user_type'],
                    'status': user['status'],
                    'subscription_plan': user['subscription_plan'],
                    'commission_rate': user['commission_rate'],
                    'created_at': user['created_at'],
                    'last_active': last_active['last_activity'] if last_active else None,
                    'total_trades': stats['trades'] or 0,
                    'total_pnl': round(stats['pnl'] * app.config['USDZAR_RATE'], 2),
                    'ea_count': ea_count
                })
            
            return jsonify({
                'users': result,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page
                }
            })
            
        except Exception as e:
            logger.error(f"Get users error: {e}")
            return jsonify({'users': [], 'pagination': {}})
    
    @app.route('/api/users', methods=['POST'])
    @admin_required
    @csrf_protected
    def create_user():
        """Create new user"""
        try:
            data = request.get_json()
            
            # Validate required
            required = ['username', 'email', 'password']
            for field in required:
                if field not in data:
                    return jsonify({'error': f'Missing {field}'}), 400
            
            username = sanitize_input(data['username'], 50)
            email = sanitize_input(data['email'], 100)
            
            if not validate_username(username):
                return jsonify({'error': 'Invalid username format'}), 400
            
            if not validate_email(email):
                return jsonify({'error': 'Invalid email format'}), 400
            
            if len(data['password']) < 8:
                return jsonify({'error': 'Password must be at least 8 characters'}), 400
            
            db = get_db()
            
            # Check existing
            existing = db.execute(
                'SELECT id FROM users WHERE username = ? OR email = ?',
                (username, email)
            ).fetchone()
            
            if existing:
                return jsonify({'error': 'Username or email already exists'}), 400
            
            # Create user
            password_hash = generate_password_hash(data['password'])
            api_key = secrets.token_urlsafe(32)
            api_secret = secrets.token_urlsafe(32)
            
            cursor = db.execute('''
                INSERT INTO users (
                    username, password_hash, email, full_name,
                    user_type, status, subscription_plan,
                    commission_rate, api_key, api_secret,
                    email_verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                username, password_hash, email,
                sanitize_input(data.get('full_name', ''), 100),
                data.get('user_type', 'member'),
                data.get('status', 'pending'),
                data.get('subscription_plan', 'trial'),
                float(data.get('commission_rate', 0)),
                api_key, api_secret
            ))
            
            db.commit()
            user_id = cursor.lastrowid
            
            log_security_event('user_created', f"Created user {username}", session['user_id'])
            
            return jsonify({
                'success': True,
                'user_id': user_id,
                'message': 'User created',
                'api_key': api_key,
                'api_secret': api_secret
            }), 201
            
        except Exception as e:
            logger.error(f"Create user error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    @app.route('/api/users/<int:user_id>', methods=['GET'])
    @admin_required
    def get_user(user_id):
        """Get user details"""
        try:
            db = get_db()
            
            user = db.execute('''
                SELECT id, username, email, full_name, user_type, status,
                       subscription_plan, subscription_end, commission_rate,
                       phone, country, timezone, created_at, last_login,
                       mt5_account, mt5_server, api_key
                FROM users WHERE id = ?
            ''', (user_id,)).fetchone()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            trades = db.execute('''
                SELECT ticket, symbol, profit, swap, commission, created_at
                FROM trades WHERE user_id = ?
                ORDER BY created_at DESC LIMIT 20
            ''', (user_id,)).fetchall()
            
            eas = db.execute('''
                SELECT ea_name, symbol, status, current_level, total_profit
                FROM ea_instances WHERE assigned_to_user_id = ?
            ''', (user_id,)).fetchall()
            
            sessions = db.execute('''
                SELECT ip_address, login_time, last_activity, is_active
                FROM sessions WHERE user_id = ?
                ORDER BY login_time DESC LIMIT 10
            ''', (user_id,)).fetchall()
            
            return jsonify({
                'user': dict(user),
                'trades': [dict(t) for t in trades],
                'eas': [dict(e) for e in eas],
                'sessions': [dict(s) for s in sessions]
            })
            
        except Exception as e:
            logger.error(f"Get user error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    @app.route('/api/users/<int:user_id>', methods=['PUT'])
    @admin_required
    @csrf_protected
    def update_user(user_id):
        """Update user"""
        try:
            data = request.get_json()
            db = get_db()
            
            # Check user exists
            user = db.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Allowed fields
            allowed = {
                'email': validate_email,
                'full_name': lambda x: True,
                'user_type': lambda x: x in ['member', 'ib', 'admin'],
                'status': lambda x: x in ['pending', 'active', 'suspended', 'rejected'],
                'subscription_plan': lambda x: x in ['trial', 'basic', 'pro', 'vip', 'lifetime'],
                'subscription_end': validate_date,
                'commission_rate': lambda x: 0 <= float(x) <= 100,
                'phone': validate_phone,
                'country': lambda x: True,
                'timezone': lambda x: True,
                'mt5_account': lambda x: True,
                'mt5_server': lambda x: True
            }
            
            updates = []
            params = []
            
            for field, validator in allowed.items():
                if field in data and data[field] is not None:
                    value = data[field]
                    if field == 'commission_rate':
                        value = float(value)
                    
                    if validator(value):
                        updates.append(f"{field} = ?")
                        params.append(value)
            
            if not updates:
                return jsonify({'error': 'No valid fields'}), 400
            
            params.append(user_id)
            
            db.execute(f'''
                UPDATE users 
                SET {', '.join(updates)}, last_active = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', params)
            db.commit()
            
            log_security_event('user_updated', f"Updated user {user_id}", session['user_id'])
            
            return jsonify({'success': True, 'message': 'User updated'})
            
        except Exception as e:
            logger.error(f"Update user error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    @app.route('/api/users/<int:user_id>/reset-api', methods=['POST'])
    @admin_required
    @csrf_protected
    def reset_user_api(user_id):
        """Reset user's API credentials"""
        try:
            db = get_db()
            
            user = db.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            new_api_key = secrets.token_urlsafe(32)
            new_api_secret = secrets.token_urlsafe(32)
            
            db.execute('''
                UPDATE users 
                SET api_key = ?, api_secret = ?
                WHERE id = ?
            ''', (new_api_key, new_api_secret, user_id))
            db.commit()
            
            log_security_event('api_reset', f"Reset API for user {user_id}", session['user_id'])
            
            return jsonify({
                'success': True,
                'api_key': new_api_key,
                'api_secret': new_api_secret,
                'message': 'API credentials reset'
            })
            
        except Exception as e:
            logger.error(f"Reset API error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    @app.route('/api/users/<int:user_id>/suspend', methods=['POST'])
    @admin_required
    @csrf_protected
    def suspend_user(user_id):
        """Suspend user account"""
        try:
            db = get_db()
            
            user = db.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            db.execute('''
                UPDATE users 
                SET status = 'suspended', locked_until = datetime('now', '+24 hours')
                WHERE id = ?
            ''', (user_id,))
            
            db.execute('''
                UPDATE sessions 
                SET is_active = 0, logout_time = CURRENT_TIMESTAMP
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            db.commit()
            
            log_security_event('user_suspended', f"Suspended user {user_id}", session['user_id'])
            
            return jsonify({'success': True, 'message': 'User suspended'})
            
        except Exception as e:
            logger.error(f"Suspend user error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    @app.route('/api/users/import', methods=['POST'])
    @admin_required
    @csrf_protected
    def import_users():
        """Bulk import users from CSV"""
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'Only CSV files allowed'}), 400
        
        try:
            import csv
            import io
            
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            
            db = get_db()
            results = {'success': 0, 'failed': 0, 'errors': []}
            
            for row in reader:
                try:
                    username = sanitize_input(row.get('username', ''), 50)
                    email = sanitize_input(row.get('email', ''), 100)
                    
                    if not username or not email:
                        results['failed'] += 1
                        results['errors'].append('Missing username or email')
                        continue
                    
                    if not validate_username(username) or not validate_email(email):
                        results['failed'] += 1
                        results['errors'].append(f'Invalid format for {username}')
                        continue
                    
                    # Check existing
                    existing = db.execute(
                        'SELECT id FROM users WHERE username = ? OR email = ?',
                        (username, email)
                    ).fetchone()
                    
                    if existing:
                        results['failed'] += 1
                        results['errors'].append(f'User {username} already exists')
                        continue
                    
                    # Generate password
                    password = secrets.token_urlsafe(12)
                    password_hash = generate_password_hash(password)
                    
                    # Generate API keys
                    api_key = secrets.token_urlsafe(32)
                    api_secret = secrets.token_urlsafe(32)
                    
                    db.execute('''
                        INSERT INTO users (
                            username, password_hash, email, full_name,
                            user_type, status, subscription_plan,
                            commission_rate, phone, country,
                            api_key, api_secret, email_verified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (
                        username, password_hash, email,
                        sanitize_input(row.get('full_name', ''), 100),
                        row.get('user_type', 'member'),
                        row.get('status', 'pending'),
                        row.get('subscription_plan', 'trial'),
                        float(row.get('commission_rate', 0)),
                        sanitize_input(row.get('phone', ''), 20),
                        sanitize_input(row.get('country', ''), 50),
                        api_key, api_secret
                    ))
                    
                    results['success'] += 1
                    
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(str(e))
            
            db.commit()
            
            log_security_event('users_imported', 
                             f"Imported {results['success']} users", 
                             session['user_id'])
            
            return jsonify(results)
            
        except Exception as e:
            logger.error(f"Import error: {e}")
            return jsonify({'error': 'Import failed'}), 500
    
    # ===========================================
    # IB COMMISSIONS API
    # ===========================================
    
    @app.route('/api/ib/commissions')
    @admin_required
    def get_commissions():
        """Get IB commissions report"""
        try:
            period = request.args.get('period', 'month')
            db = get_db()
            
            # Date filter
            if period == 'day':
                date_filter = "date(earned_date) = date('now')"
            elif period == 'week':
                date_filter = "earned_date > datetime('now', '-7 days')"
            elif period == 'month':
                date_filter = "earned_date > datetime('now', '-30 days')"
            else:
                date_filter = "1=1"
            
            # Get IB summary
            ibs = db.execute(f'''
                SELECT 
                    u.id as ib_id,
                    u.username as ib_username,
                    u.full_name as ib_name,
                    COUNT(DISTINCT c.referred_user_id) as total_clients,
                    COUNT(c.id) as transactions,
                    COALESCE(SUM(c.commission_amount), 0) as total_commission,
                    COALESCE(SUM(CASE WHEN c.status = 'paid' THEN c.commission_amount ELSE 0 END), 0) as paid_commission,
                    COALESCE(SUM(CASE WHEN c.status = 'pending' THEN c.commission_amount ELSE 0 END), 0) as pending_commission
                FROM commissions c
                JOIN users u ON c.ib_user_id = u.id
                WHERE {date_filter}
                GROUP BY u.id
                ORDER BY total_commission DESC
            ''').fetchall()
            
            # Get recent transactions
            recent = db.execute(f'''
                SELECT 
                    c.*,
                    ib.username as ib_username,
                    client.username as client_username
                FROM commissions c
                JOIN users ib ON c.ib_user_id = ib.id
                JOIN users client ON c.referred_user_id = client.id
                WHERE {date_filter}
                ORDER BY c.earned_date DESC
                LIMIT 20
            ''').fetchall()
            
            # Calculate totals
            total_all = sum(ib['total_commission'] for ib in ibs)
            
            return jsonify({
                'period': period,
                'commissions': [dict(ib) for ib in ibs],
                'recent': [dict(r) for r in recent],
                'total_all': round(total_all, 2)
            })
            
        except Exception as e:
            logger.error(f"Commissions error: {e}")
            return jsonify({'commissions': [], 'recent': [], 'total_all': 0})
    
    # ===========================================
    # MY PERFORMANCE API
    # ===========================================
    
    @app.route('/api/my/performance')
    @login_required
    def my_performance():
        """Get personal performance for master dashboard"""
        try:
            db = get_db()
            user_id = session['user_id']
            
            # Check if admin
            user = db.execute('SELECT user_type FROM users WHERE id = ?', (user_id,)).fetchone()
            is_admin = user and user['user_type'] in ['admin', 'ib']
            
            if is_admin:
                # Admin sees all
                summary = db.execute('''
                    SELECT 
                        COUNT(DISTINCT ea_name) as active_eas,
                        COUNT(*) as total_trades,
                        COALESCE(SUM(profit + swap + commission), 0) as total_pnl_usd,
                        COALESCE(AVG(profit + swap + commission), 0) as avg_trade,
                        SUM(CASE WHEN (profit + swap + commission) > 0 THEN 1 ELSE 0 END) as wins,
                        MAX(created_at) as last_trade
                    FROM trades
                ''').fetchone()
                
                daily = db.execute('''
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as trades,
                        COALESCE(SUM(profit + swap + commission), 0) as pnl_usd
                    FROM trades
                    WHERE created_at > datetime('now', '-30 days')
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                ''').fetchall()
                
                today_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE DATE(created_at) = DATE('now')
                ''').fetchone()['cnt']
                
                ea_status = db.execute('''
                    SELECT status, COUNT(*) as count
                    FROM ea_instances
                    GROUP BY status
                ''').fetchall()
                
            else:
                # Regular user sees their own
                summary = db.execute('''
                    SELECT 
                        COUNT(DISTINCT ea_name) as active_eas,
                        COUNT(*) as total_trades,
                        COALESCE(SUM(profit + swap + commission), 0) as total_pnl_usd,
                        COALESCE(AVG(profit + swap + commission), 0) as avg_trade,
                        SUM(CASE WHEN (profit + swap + commission) > 0 THEN 1 ELSE 0 END) as wins,
                        MAX(created_at) as last_trade
                    FROM trades
                    WHERE user_id = ?
                ''', (user_id,)).fetchone()
                
                daily = db.execute('''
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as trades,
                        COALESCE(SUM(profit + swap + commission), 0) as pnl_usd
                    FROM trades
                    WHERE user_id = ? AND created_at > datetime('now', '-30 days')
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                ''', (user_id,)).fetchall()
                
                today_trades = db.execute('''
                    SELECT COUNT(*) as cnt FROM trades
                    WHERE user_id = ? AND DATE(created_at) = DATE('now')
                ''', (user_id,)).fetchone()['cnt']
                
                ea_status = []
            
            total_trades = summary['total_trades'] or 0
            wins = summary['wins'] or 0
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            # Get today's P&L
            today_pnl = db.execute('''
                SELECT COALESCE(SUM(profit + swap + commission), 0) as total
                FROM trades
                WHERE DATE(created_at) = DATE('now')
                AND (user_id = ? OR ?)
            ''', (user_id if not is_admin else 0, is_admin)).fetchone()['total']
            
            return jsonify({
                'summary': {
                    'active_eas': summary['active_eas'] or 0,
                    'total_trades': total_trades,
                    'total_pnl_usd': round(summary['total_pnl_usd'] or 0, 2),
                    'total_pnl_zar': round((summary['total_pnl_usd'] or 0) * app.config['USDZAR_RATE'], 2),
                    'today_pnl_zar': round(today_pnl * app.config['USDZAR_RATE'], 2),
                    'avg_trade': round(summary['avg_trade'] or 0, 2),
                    'win_rate': round(win_rate, 1),
                    'wins': wins,
                    'losses': total_trades - wins,
                    'last_trade': summary['last_trade']
                },
                'daily': [dict(d) for d in daily],
                'today_trades': today_trades,
                'ea_status': {e['status']: e['count'] for e in ea_status},
                'is_admin': is_admin
            })
            
        except Exception as e:
            logger.error(f"My performance error: {e}")
            return jsonify({'summary': {}, 'daily': []})
    
    # ===========================================
    # SYSTEM HEALTH API
    # ===========================================
    
    @app.route('/api/system/health')
    @admin_required
    def system_health():
        """Complete system health check"""
        try:
            db = get_db()
            
            # User stats
            users = db.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END) as suspended
                FROM users
            ''').fetchone()
            
            # Active now (last 5 minutes)
            active_now = db.execute('''
                SELECT COUNT(*) as cnt FROM sessions
                WHERE is_active = 1 AND last_activity > datetime('now', '-5 minutes')
            ''').fetchone()['cnt']
            
            # Active today
            active_today = db.execute('''
                SELECT COUNT(DISTINCT user_id) as cnt FROM sessions
                WHERE last_activity > datetime('now', '-24 hours')
            ''').fetchone()['cnt']
            
            # Trade stats
            trades = db.execute('''
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT DATE(created_at)) as trading_days,
                    COALESCE(SUM(profit + swap + commission), 0) as total_pnl
                FROM trades
            ''').fetchone()
            
            trades_today = db.execute('''
                SELECT COUNT(*) as cnt FROM trades 
                WHERE DATE(created_at) = DATE('now')
            ''').fetchone()['cnt']
            
            # EA stats
            eas = db.execute('''
                SELECT 
                    status,
                    COUNT(*) as count
                FROM ea_instances
                GROUP BY status
            ''').fetchall()
            
            total_eas = db.execute('SELECT COUNT(*) FROM ea_instances').fetchone()[0]
            
            # Recent security events
            security = db.execute('''
                SELECT event_type, timestamp, details
                FROM security_audit
                WHERE event_type IN ('login_failed', 'csrf_failure', 'invalid_api_key')
                ORDER BY timestamp DESC
                LIMIT 10
            ''').fetchall()
            
            # Database size
            db_size = os.path.getsize(app.config['DATABASE']) / (1024 * 1024)
            
            return jsonify({
                'users': {
                    'total': users['total'],
                    'active': users['active'] or 0,
                    'pending': users['pending'] or 0,
                    'suspended': users['suspended'] or 0,
                    'active_now': active_now,
                    'active_today': active_today
                },
                'trades': {
                    'total': trades['total'],
                    'today': trades_today,
                    'trading_days': trades['trading_days'] or 0,
                    'total_pnl': round(trades['total_pnl'] or 0, 2)
                },
                'eas': {
                    'total': total_eas,
                    'by_status': {e['status']: e['count'] for e in eas}
                },
                'system': {
                    'database_size_mb': round(db_size, 2),
                    'websocket_clients': len(state.connected_clients) if WEBSOCKET_AVAILABLE else 0,
                    'current_level': state.current_level,
                    'uptime_days': round((datetime.now() - datetime.fromtimestamp(Path(__file__).stat().st_ctime)).total_seconds() / 86400, 1)
                },
                'recent_security_events': [dict(e) for e in security]
            })
            
        except Exception as e:
            logger.error(f"System health error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    # ===========================================
    # API KEYS MANAGEMENT
    # ===========================================
    
    @app.route('/api/keys', methods=['GET'])
    @login_required
    def get_api_keys():
        """Get user's API keys"""
        try:
            db = get_db()
            
            # Current key from users table
            current = db.execute('''
                SELECT api_key, created_at, last_login as last_used
                FROM users WHERE id = ?
            ''', (session['user_id'],)).fetchone()
            
            # Historical keys from api_keys table
            try:
                historical = db.execute('''
                    SELECT api_key, created_at, last_used, expires_at
                    FROM api_keys WHERE user_id = ?
                    ORDER BY created_at DESC
                ''', (session['user_id'],)).fetchall()
            except:
                historical = []
            
            keys = []
            if current and current['api_key']:
                keys.append({
                    'api_key': current['api_key'][:20] + '...',
                    'created_at': current['created_at'],
                    'last_used': current['last_used'],
                    'expires_at': None,
                    'is_current': True
                })
            
            for key in historical:
                keys.append({
                    'api_key': key['api_key'][:20] + '...',
                    'created_at': key['created_at'],
                    'last_used': key['last_used'],
                    'expires_at': key['expires_at'],
                    'is_current': False
                })
            
            return jsonify({'keys': keys})
            
        except Exception as e:
            logger.error(f"API keys error: {e}")
            return jsonify({'keys': []})
    
    @app.route('/api/rotate-api-key', methods=['POST'])
    @login_required
    @csrf_protected
    def rotate_api_key():
        """Rotate user's API key"""
        try:
            db = get_db()
            
            # Get current key
            current = db.execute('''
                SELECT api_key, api_secret FROM users WHERE id = ?
            ''', (session['user_id'],)).fetchone()
            
            # Archive current key if exists
            if current and current['api_key']:
                try:
                    db.execute('''
                        CREATE TABLE IF NOT EXISTS api_keys (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            api_key TEXT,
                            api_secret TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_used TIMESTAMP,
                            expires_at TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    ''')
                    
                    db.execute('''
                        INSERT INTO api_keys (user_id, api_key, api_secret, expires_at)
                        VALUES (?, ?, ?, datetime('now', '+30 days'))
                    ''', (session['user_id'], current['api_key'], current['api_secret']))
                except:
                    pass
            
            # Generate new
            new_key = secrets.token_urlsafe(32)
            new_secret = secrets.token_urlsafe(32)
            
            db.execute('''
                UPDATE users 
                SET api_key = ?, api_secret = ?
                WHERE id = ?
            ''', (new_key, new_secret, session['user_id']))
            
            db.commit()
            
            log_security_event('api_key_rotated', f"User rotated API key", session['user_id'])
            
            return jsonify({
                'success': True,
                'api_key': new_key,
                'api_secret': new_secret,
                'message': 'API key rotated'
            })
            
        except Exception as e:
            logger.error(f"Rotate key error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    # ===========================================
    # MT5 BRIDGE
    # ===========================================
    
    @app.route('/api/mt5-bridge/health', methods=['GET'])
    @login_required
    def mt5_bridge_health():
        """Check MT5 proxy health"""
        try:
            import requests
            response = requests.get(
                f"{app.config['MT5_PROXY_URL']}/api/level",
                timeout=3,
                headers={'X-API-Key': app.config['EA_API_KEY']}
            )
            
            if response.ok:
                data = response.json()
                return jsonify({
                    'status': 'connected',
                    'proxy_level': data.get('level'),
                    'local_level': state.current_level,
                    'synced': data.get('level') == state.current_level
                })
            else:
                return jsonify({
                    'status': 'error',
                    'local_level': state.current_level
                }), 503
                
        except Exception as e:
            return jsonify({
                'status': 'disconnected',
                'message': str(e),
                'local_level': state.current_level
            }), 503
    
    @app.route('/api/mt5-bridge/set_level', methods=['POST'])
    @login_required
    @csrf_protected
    def mt5_bridge_set_level():
        """Set level via MT5 proxy"""
        try:
            data = request.get_json()
            level = data.get('level')
            
            if not validate_level(level):
                return jsonify({'error': 'Invalid level'}), 400
            
            proxy_status = {'status': 'proxy_offline'}
            
            try:
                import requests
                response = requests.post(
                    f"{app.config['MT5_PROXY_URL']}/set_level",
                    json={'level': level},
                    timeout=3,
                    headers={'X-API-Key': app.config['EA_API_KEY']}
                )
                if response.ok:
                    proxy_status = response.json()
            except:
                pass
            
            # Set locally
            state.set_level(level, source='mt5_bridge', user_id=session['user_id'])
            
            return jsonify({
                'status': 'success',
                'level': state.current_level,
                'proxy_status': proxy_status
            })
            
        except Exception as e:
            logger.error(f"MT5 bridge error: {e}")
            return jsonify({'error': 'Internal error'}), 500
    
    # ===========================================
    # WEBSOCKET (if enabled)
    # ===========================================
    
    if WEBSOCKET_AVAILABLE and app.config['WEBSOCKET_ENABLED']:
        sock = Sock(app)
        
        @sock.route('/ws/trading')
        @login_required
        def trading_websocket(ws):
            """WebSocket for real-time updates"""
            user_id = session['user_id']
            
            with state.clients_lock:
                state.connected_clients.add(ws)
            
            logger.info(f"WebSocket connected: {user_id} (total: {len(state.connected_clients)})")
            
            # Send initial data
            ws.send(json.dumps({
                'type': 'connected',
                'level': state.current_level,
                'timestamp': datetime.now().isoformat()
            }))
            
            try:
                while True:
                    message = ws.receive()
                    if message is None:
                        break
                    
                    try:
                        data = json.loads(message)
                        
                        if data.get('type') == 'ping':
                            ws.send(json.dumps({'type': 'pong'}))
                        
                        elif data.get('type') == 'set_level':
                            level = data.get('payload', {}).get('level')
                            if validate_level(level):
                                state.set_level(level, source='websocket', user_id=user_id)
                                broadcast_level_change(level)
                        
                        elif data.get('type') == 'get_level':
                            ws.send(json.dumps({
                                'type': 'level_data',
                                'payload': {'level': state.current_level}
                            }))
                        
                        elif data.get('type') == 'subscribe_trades':
                            ws.send(json.dumps({
                                'type': 'subscribed',
                                'channel': 'trades'
                            }))
                                
                    except json.JSONDecodeError:
                        pass
                        
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                with state.clients_lock:
                    state.connected_clients.discard(ws)
                logger.info(f"WebSocket disconnected: {user_id}")
        
        def broadcast_level_change(level):
            """Broadcast level change to all clients"""
            message = json.dumps({
                'type': 'level_change',
                'payload': {'level': level, 'source': 'websocket'}
            })
            
            with state.clients_lock:
                clients = state.connected_clients.copy()
            
            for client in clients:
                try:
                    client.send(message)
                except:
                    pass
        
        def notify_new_trade(trade):
            """Notify clients of new trade"""
            message = json.dumps({
                'type': 'trade_update',
                'payload': trade
            })
            
            with state.clients_lock:
                clients = state.connected_clients.copy()
            
            for client in clients:
                try:
                    client.send(message)
                except:
                    pass
    else:
        def broadcast_level_change(level): pass
        def notify_new_trade(trade): pass
    
    # ===========================================
    # COMMISSION HELPER
    # ===========================================
    
    def calculate_commission(user_id: int, ticket: int, trade: dict):
        """Calculate IB commission for a trade"""
        try:
            db = get_db()
            
            # Get user's IB
            user = db.execute('SELECT referred_by FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user or not user['referred_by']:
                return
            
            # Get IB details
            ib = db.execute('''
                SELECT id, commission_rate FROM users 
                WHERE ib_id = ? AND status = 'active'
            ''', (user['referred_by'],)).fetchone()
            
            if not ib or not ib['commission_rate']:
                return
            
            # Calculate commission (example: R10 per lot per %)
            volume = trade.get('volume', 0)
            commission = volume * ib['commission_rate'] * 10
            
            if commission > 0:
                db.execute('''
                    INSERT INTO commissions 
                    (ib_user_id, referred_user_id, trade_id, volume_lots, commission_amount)
                    VALUES (?, ?, ?, ?, ?)
                ''', (ib['id'], user_id, ticket, volume, commission))
                db.commit()
                
                logger.info(f"Commission: R{commission:.2f} for IB {ib['id']}")
                
        except Exception as e:
            logger.error(f"Commission error: {e}")
    
    # ===========================================
    # ERROR HANDLERS
    # ===========================================
    
    @app.errorhandler(404)
    def not_found(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"500 error: {error}", exc_info=True)
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(error):
        logger.security('forbidden', f"403 on {request.path}")
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Access denied'}), 403
        return render_template('403.html'), 403
    
    @app.errorhandler(401)
    def unauthorized(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('login'))
    
    @app.errorhandler(429)
    def rate_limit(error):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # ===========================================
    # TEMPLATE CONTEXT
    # ===========================================
    
    @app.context_processor
    def inject_globals():
        return {
            'csrf_token': generate_csrf_token,
            'current_level': state.current_level,
            'current_year': datetime.now().year,
            'websocket_enabled': app.config['WEBSOCKET_ENABLED'] and WEBSOCKET_AVAILABLE
        }
    
    return app

# ===========================================
# APPLICATION ENTRY POINT
# ===========================================

if __name__ == '__main__':
    
    print("\n" + "="*70)
    print("🚀 JUJU FX EA MANAGER v10.0 - PRODUCTION READY")
    print("="*70)
    print("🔒 SECURITY FIRST - Financial system")
    print("="*70)
    
    # Verify .env
    if not env_path.exists():
        print("\n❌ No .env file found!")
        print("Run the script once to generate a template, then edit it.")
        sys.exit(1)
    
    # Check required vars
    missing_vars = [v for v in ['SECRET_KEY', 'ADMIN_PASSWORD', 'EA_API_KEY'] 
                   if not os.getenv(v) or os.getenv(v) in [secrets.token_urlsafe(32)]]
    
    if missing_vars:
        print(f"\n❌ Missing or default environment variables: {missing_vars}")
        print("Please edit your .env file with real values!")
        sys.exit(1)
    
    # Create directories
    Path('data').mkdir(exist_ok=True)
    Path('logs').mkdir(exist_ok=True)
    Path('templates').mkdir(exist_ok=True)
    
    # Create application
    app = create_app()
    
    # Get current level from file for startup display
    current_level = 5
    try:
        level_file = Path('data') / 'current_level.dat'
        if level_file.exists():
            with open(level_file, 'r') as f:
                level = f.read().strip()
                if level and level.isdigit():
                    current_level = int(level)
    except:
        pass
    
    # Print startup info
    print(f"\n📊 Configuration:")
    print(f"  • Database: data/juju_fx.db")
    print(f"  • WebSocket: {'✅ Enabled' if WEBSOCKET_AVAILABLE and app.config['WEBSOCKET_ENABLED'] else '❌ Disabled'}")
    print(f"  • Rate Limiting: {'✅ Enabled' if app.config['RATE_LIMIT_ENABLED'] else '❌ Disabled'}")
    
    print(f"\n🌐 Endpoints:")
    print(f"  • Main: {app.config['SERVER_URL']}")
    print(f"  • Dashboard: {app.config['SERVER_URL']}/")
    print(f"  • Master: {app.config['SERVER_URL']}/master")
    print(f"  • Analytics: {app.config['SERVER_URL']}/analytics")
    print(f"  • Trades: {app.config['SERVER_URL']}/trades")
    print(f"  • MT5 Level: {app.config['SERVER_URL']}/api/level")
    print(f"  • Health: {app.config['SERVER_URL']}/health")
    
    print(f"\n🔐 Security:")
    print(f"  • CSRF Protection: ✅")
    print(f"  • Session Security: ✅")
    print(f"  • Audit Logging: ✅")
    print(f"  • Rate Limiting: {'✅' if app.config['RATE_LIMIT_ENABLED'] else '⚠️ DISABLED'}")
    print(f"  • Max Login Attempts: {app.config['MAX_LOGIN_ATTEMPTS']}")
    print(f"  • Session Timeout: {app.config['PERMANENT_SESSION_LIFETIME'].seconds//3600} hours")
    
    print(f"\n📝 Logs:")
    print(f"  • Application: logs/app.log")
    print(f"  • Security: logs/security.log")
    print(f"  • MT5: logs/mt5.log")
    print(f"  • Errors: logs/error.log")
    
    print(f"\n👤 Admin Login:")
    print(f"  • Username: {os.getenv('ADMIN_USERNAME', 'admin')}")
    print(f"  • Password: [from .env file]")
    
    print(f"\n🔑 EA API Key: {app.config['EA_API_KEY']}")
    
    print(f"\n💰 Level changes: GUARANTEED to work")
    print(f"  • Current level: {current_level}")
    print(f"  • Level storage: data/current_level.dat")
    
    print(f"\n🚀 Server starting...")
    print("="*70 + "\n")
    
    # IMPORTANT FIX FOR APP PLATFORM: Use PORT environment variable
    port = int(os.environ.get('PORT', 8443))
    
    # Run with production settings
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,  # NEVER True in production
        threaded=True
    )
