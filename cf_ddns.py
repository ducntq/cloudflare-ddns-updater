# /// script
# dependencies = [
#   "httpx",
#   "python-dotenv",
# ]
# ///

import os
import sys
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
    create_if_not_exists = os.getenv("CF_CREATE_IF_NOT_EXISTS", "false").lower() == "true"

    if not all([api_token, zone_name, record_name]):
        print("Error: CF_API_TOKEN, CF_ZONE_NAME, and CF_RECORD_NAME must be set.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url="https://api.cloudflare.com/client/v4") as client:
        # 1. Get current public IP
        try:
            response = httpx.get("https://api.ipify.org?format=json", timeout=10.0)
            response.raise_for_status()
            public_ip = response.json()["ip"]
            print(f"Current public IP: {public_ip}")
        except Exception as e:
            print(f"Error fetching public IP from ipify: {e}")
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
        if not record:
            if create_if_not_exists:
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
            else:
                print(f"Error: Record {record_name} does not exist and CF_CREATE_IF_NOT_EXISTS is false.")
                sys.exit(1)
        else:
            current_ip = record["content"]
            record_id = record["id"]

            if current_ip == public_ip:
                print(f"IP has not changed ({public_ip}). No update needed.")
            else:
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

if __name__ == "__main__":
    main()
