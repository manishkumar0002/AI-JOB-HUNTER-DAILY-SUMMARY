import os
import requests
from scripts.logger import log_info, log_error

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram_summary(summary_data: dict) -> bool:
    """
    Sends a formatted summary report to Telegram using the Bot API.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log_info("Telegram credentials not configured. Skipping Telegram notification.", "Telegram")
        return False

    today_str = summary_data.get("date", "")
    total_jobs = summary_data.get("total_jobs", 0)
    high_prio = summary_data.get("high_priority", 0)
    highest_ats = summary_data.get("highest_ats", 0)
    highest_ats_company = summary_data.get("highest_ats_company", "N/A")
    highest_ats_title = summary_data.get("highest_ats_title", "N/A")
    excel_path = summary_data.get("excel_path", "")
    
    # Extract top companies
    top_companies = ", ".join(summary_data.get("top_companies", [])) if summary_data.get("top_companies") else "None"

    message = (
        f"🤖 *AI Job Hunter Daily Report* ({today_str})\n"
        f"==================================\n"
        f"🔍 *New Jobs Found:* {total_jobs}\n"
        f"🔥 *High Match Jobs (ATS >= 80):* {high_prio}\n"
        f"⚡ *Top Companies:* {top_companies}\n\n"
        f"🏆 *Highest ATS Match:* {highest_ats}% \n"
        f"└  _{highest_ats_title}_ at _{highest_ats_company}_\n\n"
        f"📂 *Excel Report Location:*\n"
        f"`{excel_path}`\n"
        f"=================================="
    )

    url = f"https://api.telegram.com/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        log_info("Telegram notification sent successfully.", "Telegram")
        return True
    except Exception as e:
        log_error(f"Failed to send Telegram notification: {e}", "Telegram")
        return False
