import os
import ssl
import certifi
import subprocess
import sys

def fix_python_ssl():
    print("="*50)
    print("SSL Certificate Repair Utility")
    print("="*50)
    
    # 1. Update certifi
    print("[1/3] Updating certifi package...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "certifi"])
    except:
        pass
    
    # 2. Set Environment Variables
    cert_path = certifi.where()
    print(f"[2/3] Found certifi at: {cert_path}")
    
    # 3. Test Connection
    print("[3/3] Testing connection to Yahoo Finance...")
    try:
        import requests
        # Set environment variables for this process
        os.environ['SSL_CERT_FILE'] = cert_path
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
        
        r = requests.get("https://finance.yahoo.com", timeout=10)
        if r.status_code == 200:
            print("OK: Connection Successful!")
        else:
            print(f"WARN: Connection returned status: {r.status_code}")
    except Exception as e:
        print(f"ERROR: Connection Failed: {e}")
        print("\nTIP: If you still see errors, run this in your terminal:")
        print(f'setx SSL_CERT_FILE "{cert_path}"')
        print(f'setx REQUESTS_CA_BUNDLE "{cert_path}"')

if __name__ == "__main__":
    fix_python_ssl()
