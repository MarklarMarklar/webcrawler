#!/usr/bin/env python3
"""
Helper script to find the correct Windows host IP from WSL
and test connectivity to the LM Studio server
"""
import socket
import requests
import subprocess
import logging
import time
import os
import sys

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PORT = 1234
DEFAULT_ENDPOINT = "/v1/models"
TIMEOUT = 3  # seconds

def get_wsl_host_ip():
    """
    Get the IP address of the Windows host from within WSL
    Usually it's the IP address of eth0's default gateway
    """
    try:
        # Method 1: Read /etc/resolv.conf
        with open('/etc/resolv.conf', 'r') as file:
            for line in file:
                if line.startswith('nameserver'):
                    ip = line.split()[1].strip()
                    logger.info(f"Found nameserver IP from resolv.conf: {ip}")
                    return ip
    except Exception as e:
        logger.warning(f"Could not read resolv.conf: {e}")
    
    try:
        # Method 2: Use the default route
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        default_gateway = result.stdout.split('via')[1].split()[0].strip()
        logger.info(f"Found default gateway: {default_gateway}")
        return default_gateway
    except Exception as e:
        logger.warning(f"Could not determine default gateway: {e}")
    
    try:
        # Method 3: hostname -I (get all IPs and use the first one)
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=True)
        ips = result.stdout.strip().split()
        if ips:
            logger.info(f"Using first IP from hostname -I: {ips[0]}")
            return ips[0]
    except Exception as e:
        logger.warning(f"Could not get IPs from hostname: {e}")
    
    # Fallback to a standard WSL 2 IP
    logger.warning("Using fallback IP 172.31.64.1")
    return "172.31.64.1"

def get_potential_host_ips():
    """Return a list of potential Windows host IPs"""
    potential_ips = []
    
    # Try the WSL host IP
    wsl_ip = get_wsl_host_ip()
    if wsl_ip:
        potential_ips.append(wsl_ip)
    
    # Add common WSL2 host IPs
    common_ips = ["172.31.64.1", "172.17.0.1", "192.168.1.1"]
    for ip in common_ips:
        if ip not in potential_ips:
            potential_ips.append(ip)
    
    # Add localhost and loopback
    potential_ips.extend(["127.0.0.1", "localhost"])
    
    # Add host.docker.internal
    potential_ips.append("host.docker.internal")
    
    return potential_ips

def test_lm_studio_connection(host, port=DEFAULT_PORT, endpoint=DEFAULT_ENDPOINT, timeout=TIMEOUT):
    """Test connection to LM Studio server at the given host and port"""
    url = f"http://{host}:{port}{endpoint}"
    logger.info(f"Testing connection to {url}")
    
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            logger.info(f"✓ Successfully connected to LM Studio at {url}")
            try:
                models = response.json().get('data', [])
                if models:
                    logger.info(f"Found {len(models)} models: {[m.get('id') for m in models]}")
                return True, url, models
            except Exception as e:
                logger.warning(f"Connected but could not parse response: {e}")
                return True, url, []
        else:
            logger.warning(f"× Connection failed with status code: {response.status_code}")
            return False, url, None
    except requests.exceptions.ConnectionError:
        logger.warning(f"× Connection refused to {url}")
        return False, url, None
    except requests.exceptions.Timeout:
        logger.warning(f"× Connection timeout to {url}")
        return False, url, None
    except Exception as e:
        logger.warning(f"× Error connecting to {url}: {e}")
        return False, url, None

def find_working_lm_studio_connection():
    """Try all potential host IPs and find a working LM Studio connection"""
    potential_ips = get_potential_host_ips()
    logger.info(f"Testing potential LM Studio hosts: {potential_ips}")
    
    for host in potential_ips:
        success, url, models = test_lm_studio_connection(host)
        if success:
            return url
    
    logger.error("Could not find a working LM Studio connection")
    return None

def create_api_url_with_fallback():
    """Create the base URL for LM Studio API with fallback mechanisms"""
    # First check for environment variable
    api_url = os.environ.get("LM_STUDIO_API_URL")
    if api_url:
        logger.info(f"Using API URL from environment: {api_url}")
        return api_url
    
    # Try to find a working connection
    url = find_working_lm_studio_connection()
    if url:
        # Convert URL to base format (without endpoint)
        base_url = url.replace(DEFAULT_ENDPOINT, "")
        logger.info(f"Found working API URL: {base_url}")
        return base_url
    
    # Fallback to default
    logger.warning("Using default API URL")
    return f"http://172.31.64.1:{DEFAULT_PORT}/v1"  

if __name__ == "__main__":
    print("\n=== LM Studio Connection Finder ===\n")
    
    host_ip = get_wsl_host_ip()
    print(f"WSL Host IP: {host_ip}")
    
    print("\nTesting potential connections:")
    working_url = find_working_lm_studio_connection()
    
    if working_url:
        print(f"\n✅ Found working LM Studio connection: {working_url}")
        print(f"\nAdd this to your .env file:")
        print(f"LM_STUDIO_API_URL={working_url.replace(DEFAULT_ENDPOINT, '')}")
    else:
        print("\n❌ Could not find a working LM Studio connection.")
        print("\nMake sure LM Studio is running with the API server enabled.")
        print("You might need to:")
        print("1. Allow network connections in LM Studio settings")
        print("2. Restart LM Studio")
        print("3. Try running with admin privileges")
    
    print("\nPress Enter to exit...")
    input() 