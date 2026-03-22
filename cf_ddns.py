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
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv

def setup_logging(retention_days):
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_dir = "logs"
    log_file = os.path.join(log_dir, "cf_ddns.log")
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Daily rotation, keep 'retention_days' files
    handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=retention_days
    )
    handler.setFormatter(log_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.addHandler(console_handler)

def main():
    # Load configuration from .env file if it exists
    load_dotenv()
    
    # Load configuration from environment
    api_token = os.getenv("CF_API_TOKEN")
    zone_name = os.getenv("CF_ZONE_NAME")
    # Parse record names as lists
    record_names = [r.strip() for r in os.getenv("CF_RECORD_NAME", "").split(",") if r.strip()]
    aaaa_record_names = [r.strip() for r in os.getenv("CF_AAAA_RECORD_NAME", "").split(",") if r.strip()]
    proxied = os.getenv("CF_PROXIED", "false").lower() == "true"
    dry_run = os.getenv("CF_DRY_RUN", "false").lower() == "true"
    retry_count = int(os.getenv("CF_RETRY_COUNT", "3"))
    retry_delay = int(os.getenv("CF_RETRY_DELAY", "10"))
    retention_days = int(os.getenv("CF_LOG_RETENTION_DAYS", "7"))

    setup_logging(retention_days)

    if dry_run:
        logging.info("--- DRY RUN MODE ENABLED ---")

    if not all([api_token, zone_name, record_names]):
        logging.error("CF_API_TOKEN, CF_ZONE_NAME, and CF_RECORD_NAME must be set.")
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
                logging.warning(f"Failed to fetch {'IPv6' if ipv6 else 'IPv4'}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        return None

    with httpx.Client(base_url="https://api.cloudflare.com/client/v4") as client:
        # 1. Get current public IPs
        public_ipv4 = get_public_ip(ipv6=False)
        public_ipv6 = get_public_ip(ipv6=True) if aaaa_record_names else None

        if not public_ipv4:
            logging.error("Could not fetch public IPv4 address.")
            sys.exit(1)
        
        logging.info(f"Current IPv4: {public_ipv4}")
        if aaaa_record_names:
            if public_ipv6:
                logging.info(f"Current IPv6: {public_ipv6}")
            else:
                logging.warning("AAAA records configured but could not fetch public IPv6.")

        # 2. Get Zone ID
        zone_resp = client.get("/zones", params={"name": zone_name}, headers=headers).json()
        if not zone_resp.get("success") or not zone_resp.get("result"):
            logging.error(f"Could not find zone {zone_name}.")
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
                    logging.info(f"{ip_type} record {name} is already up to date ({content}).")
                    return

                if dry_run:
                    logging.info(f"[DRY RUN] Would update {ip_type} record {name} to {content}...")
                    return

                logging.info(f"Updating {ip_type} record {name} to {content}...")
                resp = client.put(
                    f"/zones/{zone_id}/dns_records/{record['id']}",
                    headers=headers,
                    json={"type": ip_type, "name": name, "content": content, "proxied": proxied, "ttl": 1}
                ).json()
            else:
                if dry_run:
                    logging.info(f"[DRY RUN] Would create {ip_type} record {name} -> {content}...")
                    return

                logging.info(f"Creating {ip_type} record {name} -> {content}...")
                resp = client.post(
                    f"/zones/{zone_id}/dns_records",
                    headers=headers,
                    json={"type": ip_type, "name": name, "content": content, "proxied": proxied, "ttl": 1}
                ).json()

            if resp.get("success"):
                logging.info(f"Successfully processed {ip_type} record {name}.")
            else:
                logging.error(f"Failed to process {name}: {resp.get('errors')}")

        # Process records
        for name in record_names:
            update_or_create(name, "A", public_ipv4)
        
        if aaaa_record_names and public_ipv6:
            for name in aaaa_record_names:
                update_or_create(name, "AAAA", public_ipv6)

if __name__ == "__main__":
    main()
