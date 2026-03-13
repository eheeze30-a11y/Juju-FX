# test_mt5_connection.py
import requests
import json

def test_connection():
    print("Testing MT5 Connection...")
    print("=" * 50)
    
    # Test HTTPS
    try:
        print("1. Testing HTTPS (8443)...")
        response = requests.get('https://localhost:8443/api/level', verify=False, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        print("   ✅ HTTPS CONNECTED")
    except Exception as e:
        print(f"   ❌ HTTPS Failed: {e}")
    
    print("\n2. Testing HTTP (8080)...")
    try:
        response = requests.get('http://localhost:8080/api/level', timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        print("   ✅ HTTP CONNECTED")
    except Exception as e:
        print(f"   ❌ HTTP Failed: {e}")
    
    print("\n3. Checking server health...")
    try:
        response = requests.get('https://localhost:8443/health', verify=False, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Health: {response.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
    
    print("=" * 50)
    print("\nFor MT5, make sure:")
    print("1. WebRequest is enabled in MT5 Options")
    print("2. 'https://localhost:8443' is in allowed URLs")
    print("3. MT5 is running as Administrator")

if __name__ == '__main__':
    test_connection()