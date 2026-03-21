# Cloudflare DDNS Updater (Python + UV)

A simple Python script to keep your Cloudflare A records in sync with your public IP.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) installed on your system.
- A Cloudflare API Token with `Zone.DNS` edit permissions.

## Configuration

The script can be configured via environment variables or a `.env` file. 

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` with your Cloudflare credentials.

| Variable | Description | Default |
|----------|-------------|---------|
| `CF_API_TOKEN` | Your Cloudflare API Token | **Required** |
| `CF_ZONE_NAME` | The root domain (e.g., `example.com`) | **Required** |
| `CF_RECORD_NAME` | The FQDN to update (e.g., `home.example.com`) | **Required** |
| `CF_PROXIED` | Use Cloudflare Proxy (Orange Cloud) | `false` |
| `CF_CREATE_IF_NOT_EXISTS` | Create the record if it doesn't exist | `false` |

## Usage

You can run the script directly with `uv`:

```bash
uv run cf_ddns.py
```

## Scheduling with Cron

To automate this every 5 minutes, add a line to your `crontab -e`:

```cron
*/5 * * * * export CF_API_TOKEN="your_token"; export CF_ZONE_NAME="example.com"; export CF_RECORD_NAME="ddns.example.com"; /usr/local/bin/uv run /path/to/cf_ddns.py >> /tmp/cf_ddns.log 2>&1
```

*Note: Use the full path to `uv` (usually `/usr/local/bin/uv` or `~/.cargo/bin/uv`). You can find it by running `which uv`.*
