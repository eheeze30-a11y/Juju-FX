# test_mt5_fixed.py - Test MT5 connection
import requests
import json
import time

def test_all_endpoints():
    print("🔧 Testing MT5 Connection Points")
    print("=" * 60)
    
    endpoints = [
        ("HTTPS /api/level", "https://localhost:8443/api/level"),
        ("HTTPS /mt5/level", "https://localhost:8443/mt5/level"),
        ("HTTPS /health", "https://localhost:8443/health"),
        ("HTTP /api/level", "http://localhost:8080/api/level"),
        ("HTTP /health", "http://localhost:8080/health"),
    ]
    
    for name, url in endpoints:
        print(f"\n🔗 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if url.startswith('https'):
                response = requests.get(url, verify=False, timeout=5)
            else:
                response = requests.get(url, timeout=5)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response: {json.dumps(data, indent=2)[:100]}...")
                    print(f"   ✅ SUCCESS")
                except json.JSONDecodeError:
                    print(f"   Response: {response.text[:100]}")
                    print(f"   ⚠️ Not JSON format")
            else:
                print(f"   ❌ FAILED - Status {response.status_code}")
                
        except requests.exceptions.SSLError as e:
            print(f"   ❌ SSL Error: {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ Connection Error: {e}")
        except requests.exceptions.Timeout as e:
            print(f"   ❌ Timeout: {e}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("📋 MT5 Setup Instructions:")
    print("1. In MT5: Tools → Options → Expert Advisors")
    print("2. Check: 'Allow WebRequest for listed URL:'")
    print("3. Add these URLs:")
    print("   - https://localhost:8443")
    print("   - http://localhost:8080  (fallback)")
    print("4. Click OK and restart MT5")
    print("5. In EA Controller, use URL: https://localhost:8443/api/level")
    print("=" * 60)

def test_mt5_controller_simulation():
    """Simulate what MT5 controller does"""
    print("\n🤖 Simulating MT5 Controller Behavior")
    print("=" * 60)
    
    # Simulate MT5 checking level every 5 seconds
    print("Simulating MT5 polling every 5 seconds...")
    print("Press Ctrl+C to stop\n")
    
    for i in range(3):
        try:
            print(f"\nPoll #{i+1}:")
            response = requests.get("https://localhost:8443/api/level", verify=False, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Got level: {data.get('level')}")
                print(f"  Message: {data.get('message')}")
            else:
                print(f"  ❌ Failed: Status {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            
            # Try HTTP fallback
            try:
                print("  🔄 Trying HTTP fallback...")
                response = requests.get("http://localhost:8080/api/level", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    print(f"  ✅ HTTP Fallback level: {data.get('level')}")
            except:
                print("  ❌ HTTP fallback also failed")
        
        if i < 2:
            time.sleep(5)

if __name__ == '__main__':
    # Suppress SSL warnings
    requests.packages.urllib3.disable_warnings()
    
    test_all_endpoints()
    test_mt5_controller_simulation()