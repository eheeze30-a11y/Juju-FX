# config.py
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here-change-in-production'
    DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), '../data/ea_manager.db')
    USDZAR_RATE = 18.5
    PER_PAGE = 50
    SESSION_COOKIE_SECURE = True  # Only send over HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    
    # News API configuration (get keys from respective services)
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
    FOREX_FACTOR_ENABLED = True
    
class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development

class ProductionConfig(Config):
    DEBUG = False