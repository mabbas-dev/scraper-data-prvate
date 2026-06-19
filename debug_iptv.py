import requests
import json
import socket

def check_dns(domain):
    try:
        ip = socket.gethostbyname(domain)
        print(f"[*] DNS Resolution for {domain}: {ip}")
        return ip
    except Exception as e:
        print(f"[!] DNS Failed for {domain}: {e}")
        return None

def test_url(url, description):
    print(f"\n--- Testing: {description} ---")
    print(f"URL: {url}")
    
    # We will use Perryhouse01 / Perryhouse02 to test
    params = {"username": "Perryhouse01", "password": "Perryhouse02"}
    
    # Standard headers that mimic a real browser to bypass Cloudflare
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        # Don't follow redirects automatically, just in case Cloudflare throws a challenge
        resp = requests.get(url, params=params, headers=headers, timeout=15, allow_redirects=False)
        print(f"Status Code: {resp.status_code}")
        print("Headers Returned:")
        for k, v in resp.headers.items():
            if k.lower() in ['server', 'cf-ray', 'content-type', 'location']:
                print(f"  {k}: {v}")
                
        # Look for Cloudflare indicators
        server = resp.headers.get('Server', '').lower()
        if 'cloudflare' in server:
            print("[!] Cloudflare detected on this route.")
            
        content = resp.text
        
        # Check what the actual content is
        if resp.status_code == 200:
            try:
                data = json.loads(content)
                if 'user_info' in data:
                    print(f"[SUCCESS] Valid Auth! Status: {data['user_info'].get('status')}")
                else:
                    print("[WARNING] JSON returned but no user_info.")
            except:
                print("[WARNING] 200 OK but content is not JSON:")
                print(content[:200])
        elif resp.status_code == 419:
            print("[BLOCKED] 419 Error! This usually means the IPTV panel's internal firewall or anti-bot mechanism blocked the request.")
            if "xtream" in content.lower() or "xui" in content.lower():
                print(" -> Panel identity found in error page.")
        elif resp.status_code == 403:
            print("[BLOCKED] 403 Forbidden. Cloudflare or server rejected the connection.")
        elif resp.status_code in [301, 302, 307, 308]:
            print(f"[REDIRECT] Redirected to: {resp.headers.get('Location')}")
        else:
            print(f"Content snippet: {content[:200]}")
            
    except requests.exceptions.Timeout:
        print("[!] Timeout. The server did not respond in 15 seconds.")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    domains_to_test = [
        "omandigital.cfd",
        "omanprimary.cfd",
        "omansecondary.cfd",
        "omanpromarketing.cfd",
        "fastshare1.com"
    ]
    
    print("=== DNS CHECK ===")
    for d in domains_to_test:
        check_dns(d)
        
    print("\n=== HTTP API TESTS ===")
    
    # 1. Test direct IP (Port 80)
    test_url("http://95.134.201.96/player_api.php", "Direct IP (Port 80)")
    
    # 2. Test direct IP (Port 8080)
    test_url("http://95.134.201.96:8080/player_api.php", "Direct IP (Port 8080)")
    
    # 3. Test user's Cloudflare domains (Port 80)
    for d in domains_to_test:
        test_url(f"http://{d}/player_api.php", f"Domain {d} (Port 80)")
        
    # 4. Test user's Cloudflare domains (Port 8080)
    for d in domains_to_test:
        test_url(f"http://{d}:8080/player_api.php", f"Domain {d} (Port 8080)")
