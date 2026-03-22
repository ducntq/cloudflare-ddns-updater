# /// script
# dependencies = [
#   "httpx",
#   "python-dotenv",
# ]
# ///

import os
import sys
import time
import httpx
from dotenv import load_dotenv

def main():
    # Load configuration from .env file if it exists
    load_dotenv()
    
    # Load configuration from environment
    api_token = os.getenv("CF_API_TOKEN")
    zone_name = os.getenv("CF_ZONE_NAME")
    record_name = os.getenv("CF_RECORD_NAME")
    aaaa_record_name = os.getenv("CF_AAAA_RECORD_NAME")
    proxied = os.getenv("CF_PROXIED", "false").lower() == "true"
    retry_count = int(os.getenv("CF_RETRY_COUNT", "3"))
    retry_delay = int(os.getenv("CF_RETRY_DELAY", "10"))

    if not all([api_token, zone_name, record_name]):
        print("Error: CF_API_TOKEN, CF_ZONE_NAME, and CF_RECORD_NAME must be set.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    def get_public_ip(ipv6=False):
        ip_services = [
            {"url": "https://api64.ipify.org?format=json", "key": "ip"},
            {"url": "https://api.myip.com", "key": "ip"},
            {"url": "https://ipinfo.io/json", "key": "ip"},
        ]
        if ipv6:
            ip_services = [
                {"url": "https://api6.ipify.org?format=json", "key": "ip"},
                {"url": "https://v6.ident.me/.json", "key": "address"},
                {"url": "https://ipv6.icanhazip.com", "key": None}, # Plain text
            ]
        
        for attempt in range(retry_count + 1):
            for service in ip_services:
                try:
                    response = httpx.get(service["url"], timeout=10.0)
                    response.raise_for_status()
                    if service["key"]:
                        ip = response.json()[service["key"]]
                    else:
                        ip = response.text.strip()
                    
                    # Basic validation to ensure we got the right IP type
                    if ipv6 and ":" not in ip: continue
                    if not ipv6 and "." not in ip: continue
                        
                    return ip
                except Exception as e:
                    pass
            
            if attempt < retry_count:
                print(f"Failed to fetch {'IPv6' if ipv6 else 'IPv4'}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        return None

    with httpx.Client(base_url="https://api.cloudflare.com/client/v4") as client:
        # 1. Get current public IPs
        public_ipv4 = get_public_ip(ipv6=False)
        public_ipv6 = get_public_ip(ipv6=True) if aaaa_record_name else None

        if not public_ipv4:
            print("Error: Could not fetch public IPv4 address.")
            sys.exit(1)
        
        print(f"Current IPv4: {public_ipv4}")
        if aaaa_record_name:
            if public_ipv6:
                print(f"Current IPv6: {public_ipv6}")
            else:
                print("Warning: AAAA record configured but could not fetch public IPv6.")

        # 2. Get Zone ID
        zone_resp = client.get("/zones", params={"name": zone_name}, headers=headers).json()
        if not zone_resp.get("success") or not zone_resp.get("result"):
            print(f"Error: Could not find zone {zone_name}.")
            sys.exit(1)
        zone_id = zone_resp["result"][0]["id"]

        def update_or_create(name, ip_type, content):
            if not content: return

            # 3. Get existing record
            record_resp = client.get(
                f"/zones/{zone_id}/dns_records",
                params={"type": ip_type, "name": name},
                headers=headers
            ).json()
            
            records = record_resp.get("result", [])
            record = records[0] if records else None

            # 4. Update or Create
            if record:
                if record["content"] == content:
                    print(f"{ip_type} record {name} is already up to date ({content}).")
                    return

                print(f"Updating {ip_type} record {name} to {content}...")
                resp = client.put(
                    f"/zones/{zone_id}/dns_records/{record['id']}",
                    headers=headers,
                    json={"type": ip_type, "name": name, "content": content, "proxied": proxied, "ttl": 1}
                ).json()
            else:
                print(f"Creating {ip_type} record {name} -> {content}...")
                resp = client.post(
                    f"/zones/{zone_id}/dns_records",
                    headers=headers,
                    json={"type": ip_type, "name": name, "content": content, "proxied": proxied, "ttl": 1}
                ).json()

            if not resp.get("success"):
                print(f"Failed to process {name}: {resp.get('errors')}")

        # Process records
        update_or_create(record_name, "A", public_ipv4)
        if aaaa_record_name and public_ipv6:
            update_or_create(aaaa_record_name, "AAAA", public_ipv6)

if __name__ == "__main__":
    main()
