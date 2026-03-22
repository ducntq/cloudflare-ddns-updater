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

    with httpx.Client(base_url="https://api.cloudflare.com/client/v4") as client:
        # 1. Get current public IP
        ip_services = [
            {"url": "https://api.ipify.org?format=json", "key": "ip"},
            {"url": "https://api.myip.com", "key": "ip"},
            {"url": "https://ipinfo.io/json", "key": "ip"},
        ]
        
        public_ip = None
        success = False
        
        for attempt in range(retry_count + 1):
            for service in ip_services:
                try:
                    response = httpx.get(service["url"], timeout=10.0)
                    response.raise_for_status()
                    public_ip = response.json()[service["key"]]
                    print(f"Current public IP: {public_ip} (via {service['url']})")
                    success = True
                    break
                except Exception as e:
                    print(f"Warning: Failed to fetch IP from {service['url']}: {e}")
            
            if success:
                break
                
            if attempt < retry_count:
                print(f"All IP services failed. Retrying in {retry_delay}s (attempt {attempt + 1}/{retry_count + 1})...")
                time.sleep(retry_delay)
            else:
                print(f"Error: Could not fetch public IP after {retry_count + 1} attempts across all services.")
                sys.exit(1)

        # 2. Get Zone ID
        zone_resp = client.get(f"/zones", params={"name": zone_name}, headers=headers).json()
        if not zone_resp.get("success") or not zone_resp.get("result"):
            print(f"Error: Could not find zone {zone_name}. Check your token and zone name.")
            sys.exit(1)
        zone_id = zone_resp["result"][0]["id"]

        # 3. Get existing DNS record
        record_resp = client.get(
            f"/zones/{zone_id}/dns_records",
            params={"type": "A", "name": record_name},
            headers=headers
        ).json()
        
        records = record_resp.get("result", [])
        record = records[0] if records else None

        # 4. Update or Create
        if record:
            current_ip = record["content"]
            record_id = record["id"]

            if current_ip == public_ip:
                print(f"IP has not changed ({public_ip}). No update needed.")
                sys.exit(0)

            print(f"Updating {record_name} from {current_ip} to {public_ip}...")
            update_resp = client.put(
                f"/zones/{zone_id}/dns_records/{record_id}",
                headers=headers,
                json={
                    "type": "A",
                    "name": record_name,
                    "content": public_ip,
                    "proxied": proxied,
                    "ttl": 1
                }
            ).json()
            if update_resp.get("success"):
                print(f"Successfully updated {record_name} to {public_ip}")
            else:
                print(f"Failed to update: {update_resp.get('errors')}")
                sys.exit(1)
        else:
            print(f"Record {record_name} not found. Creating...")
            create_resp = client.post(
                f"/zones/{zone_id}/dns_records",
                headers=headers,
                json={
                    "type": "A",
                    "name": record_name,
                    "content": public_ip,
                    "proxied": proxied,
                    "ttl": 1  # Automatic
                }
            ).json()
            if create_resp.get("success"):
                print(f"Successfully created {record_name} -> {public_ip}")
            else:
                print(f"Failed to create: {create_resp.get('errors')}")
                sys.exit(1)

if __name__ == "__main__":
    main()
