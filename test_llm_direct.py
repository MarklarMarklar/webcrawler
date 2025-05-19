#!/usr/bin/env python3
"""
Simple diagnostic script to directly test the LLM API connection
"""
import requests
import json
import sys
import time
import socket
import subprocess

API_URL = "http://172.31.64.1:1234/v1"
LONGER_TIMEOUT = 60  # Much longer timeout for WSL-Windows connections

def check_network_route():
    """Check network route to the API server"""
    host = API_URL.replace("http://", "").replace("https://", "").split("/")[0]
    if ":" in host:
        host, port = host.split(":")
    else:
        port = "1234"
    
    print(f"\n=== Checking network route to {host}:{port} ===")
    
    # Try to ping the host
    try:
        print(f"Pinging {host}...")
        ping_cmd = ["ping", "-c", "4", host]
        result = subprocess.run(ping_cmd, capture_output=True, text=True)
        print(result.stdout)
        
        if "0 received" in result.stdout:
            print(f"❌ Could not ping {host}")
        else:
            print(f"✅ Ping to {host} succeeded")
    except Exception as e:
        print(f"❌ Ping error: {e}")
    
    # Try a socket connection
    try:
        print(f"\nTrying direct socket connection to {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, int(port)))
        if result == 0:
            print(f"✅ Socket connection successful")
        else:
            print(f"❌ Socket connection failed with error code {result}")
        sock.close()
    except Exception as e:
        print(f"❌ Socket error: {e}")

def test_models_endpoint():
    """Test the models endpoint to check basic connectivity"""
    print(f"\n=== Testing connection to {API_URL}/models ===")
    try:
        # Use a much longer timeout for WSL-to-Windows connections
        response = requests.get(f"{API_URL}/models", timeout=LONGER_TIMEOUT)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("✅ Connection successful!")
            try:
                data = response.json()
                models = data.get("data", [])
                print(f"Available models: {[m.get('id') for m in models]}")
                print("\nRaw response:")
                print(json.dumps(data, indent=2))
                return True
            except Exception as e:
                print(f"❌ Error parsing response: {e}")
                print(f"Response text: {response.text[:500]}")
                return False
        else:
            print(f"❌ Received error status code: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_chat_completion():
    """Test the chat completion endpoint with a basic prompt"""
    print(f"\n=== Testing {API_URL}/chat/completions endpoint ===")
    try:
        payload = {
            "model": "local-model",  # LM Studio uses this generic name
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in JSON format."}
            ],
            "temperature": 0.1,
            "max_tokens": 100
        }
        
        print("Sending request with payload:")
        print(json.dumps(payload, indent=2))
        
        start_time = time.time()
        response = requests.post(
            f"{API_URL}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=LONGER_TIMEOUT  # Much longer timeout for WSL
        )
        elapsed = time.time() - start_time
        
        print(f"Status code: {response.status_code} (took {elapsed:.2f} seconds)")
        
        if response.status_code == 200:
            print("✅ Chat completion successful!")
            try:
                data = response.json()
                if "choices" in data and data["choices"]:
                    message = data["choices"][0]["message"]["content"]
                    print("\nModel response:")
                    print(message)
                else:
                    print("❌ No choices in response")
                
                print("\nRaw response:")
                print(json.dumps(data, indent=2))
                return True
            except Exception as e:
                print(f"❌ Error parsing response: {e}")
                print(f"Response text: {response.text[:500]}")
                return False
        else:
            print(f"❌ Received error status code: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def diagnose_problems():
    """Suggest fixes based on test results"""
    print("\n=== Diagnostic Summary ===")
    
    if models_ok and chat_ok:
        print("✅ ALL TESTS PASSED! Your LLM connection is working correctly.")
        print("\nIf your web app is still using mock mode, check:")
        print("1. The URL in the web app matches exactly: " + API_URL)
        print("2. Modify timeouts in your application code:")
        print("   - In llm_api.py, increase all timeouts to 30 seconds")
        print("   - In the test_connection method, use a longer timeout")
        print("3. Enable debug logging in llm_api.py")
    elif models_ok and not chat_ok:
        print("⚠️ PARTIAL SUCCESS: Models endpoint works but chat completion fails")
        print("\nPossible issues:")
        print("1. The model may not be loaded correctly in LM Studio")
        print("2. The model might be too large for the current request")
        print("3. Try adjusting temperature or max_tokens")
        print("4. Check if there are any errors in the LM Studio console")
    else:
        print("❌ CONNECTION FAILED: Cannot connect to the LLM API")
        print("\nPossible WSL-Windows connectivity issues:")
        print("1. WSL might be using a different network than Windows")
        print("2. Windows Firewall might be blocking the connection")
        print("3. Try these specific fixes:")
        print("   a. In Windows Firewall, allow LM Studio to accept incoming connections")
        print("   b. Try running LM Studio as Administrator")
        print("   c. Modify /etc/resolv.conf in WSL to use Windows DNS")
        print("   d. Try changing to port 8080 or another port in LM Studio")
        print("   e. Manually add a route in WSL: `sudo ip route add 172.31.64.1 via $(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')`")

if __name__ == "__main__":
    # Allow custom API URL from command line
    if len(sys.argv) > 1:
        API_URL = sys.argv[1]
        if not API_URL.startswith("http"):
            API_URL = f"http://{API_URL}"
        if API_URL.endswith("/"):
            API_URL = API_URL[:-1]
    
    print("\n=== LLM API Diagnostic Tool ===")
    print(f"Testing API URL: {API_URL}")
    
    # First check network connectivity
    check_network_route()
    
    models_ok = test_models_endpoint()
    chat_ok = test_chat_completion()
    
    diagnose_problems() 