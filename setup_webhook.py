"""
One-time script to register your Telegram Bot webhook with Vercel.

Usage:
    python setup_webhook.py <BOT_TOKEN> <VERCEL_URL>

Example:
    python setup_webhook.py 7123456:AAHxxx https://bitbaby-price-bot.vercel.app

Or just open this URL in your browser:
    https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR_VERCEL_URL>/api/webhook
"""

import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def main():
    if len(sys.argv) < 3:
        print("Usage: python setup_webhook.py <BOT_TOKEN> <VERCEL_URL>")
        print("")
        print("Or simply open this URL in your browser:")
        print("  https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<VERCEL_URL>/api/webhook")
        return

    token = sys.argv[1]
    vercel_url = sys.argv[2].rstrip("/")
    webhook_url = f"{vercel_url}/api/webhook"

    # Print browser fallback first
    browser_url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
    print(f"\n📋 If this script fails, open this URL in your browser:\n{browser_url}\n")

    if not HAS_REQUESTS:
        print("⚠️  'requests' not installed. Use the browser URL above instead.")
        print("    Or run: pip install requests")
        return

    # Set webhook
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    resp = requests.post(api_url, data={"url": webhook_url})
    result = resp.json()

    if result.get("ok"):
        print(f"✅ Webhook set successfully!")
        print(f"   URL: {webhook_url}")
    else:
        print(f"❌ Failed: {result.get('description', 'Unknown error')}")

    # Verify
    info_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    info = requests.get(info_url).json()
    print(f"\n📡 Webhook info:")
    print(f"   URL: {info.get('result', {}).get('url', 'N/A')}")
    print(f"   Pending updates: {info.get('result', {}).get('pending_update_count', 0)}")


if __name__ == "__main__":
    main()
