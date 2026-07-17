import os
import requests
from scripts.logger import log_info, log_error

WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "none").lower()
WHATSAPP_TO_NUMBER = os.getenv("WHATSAPP_TO_NUMBER", "")

def format_whatsapp_message(summary_data: dict) -> str:
    """
    Formats the summary report for WhatsApp message styling.
    """
    today_str = summary_data.get("date", "")
    total_jobs = summary_data.get("total_jobs", 0)
    high_prio = summary_data.get("high_priority", 0)
    highest_ats = summary_data.get("highest_ats", 0)
    highest_ats_company = summary_data.get("highest_ats_company", "N/A")
    highest_ats_title = summary_data.get("highest_ats_title", "N/A")
    excel_path = summary_data.get("excel_path", "")
    top_companies = ", ".join(summary_data.get("top_companies", [])) if summary_data.get("top_companies") else "None"

    # WhatsApp uses asterisks * for bold
    message = (
        f"*🤖 AI Job Hunter Daily Report ({today_str})*\n"
        f"----------------------------------\n"
        f"*🔍 New Jobs Found:* {total_jobs}\n"
        f"*🔥 High Match Jobs (ATS >= 80):* {high_prio}\n"
        f"*⚡ Top Companies:* {top_companies}\n\n"
        f"*🏆 Highest ATS Match:* {highest_ats}%\n"
        f"└ {highest_ats_title} at {highest_ats_company}\n\n"
        f"*📂 Excel Report Location:*\n"
        f"{excel_path}\n"
        f"----------------------------------"
    )
    return message

def send_whatsapp_via_ultramsg(message: str) -> bool:
    """
    Sends WhatsApp message via UltraMsg API.
    """
    instance_id = os.getenv("WHATSAPP_ULTRAMSG_INSTANCE_ID", "")
    token = os.getenv("WHATSAPP_ULTRAMSG_TOKEN", "")
    
    if not instance_id or not token or not WHATSAPP_TO_NUMBER:
        log_error("UltraMsg configurations missing. Check instance_id, token, or number.", "WhatsApp")
        return False
        
    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {
        "token": token,
        "to": WHATSAPP_TO_NUMBER,
        "body": message,
        "priority": 10
    }
    
    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        log_info("WhatsApp notification sent via UltraMsg.", "WhatsApp")
        return True
    except Exception as e:
        log_error(f"UltraMsg send failed: {e}", "WhatsApp")
        return False

def send_whatsapp_via_twilio(message: str) -> bool:
    """
    Sends WhatsApp message via Twilio Sandbox.
    """
    account_sid = os.getenv("WHATSAPP_TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("WHATSAPP_TWILIO_AUTH_TOKEN", "")
    from_number = "whatsapp:+14155238886" # Standard Twilio Sandbox Number
    
    if not account_sid or not auth_token or not WHATSAPP_TO_NUMBER:
        log_error("Twilio configurations missing. Check account_sid, auth_token, or to_number.", "WhatsApp")
        return False
        
    # Ensure correct formatting: must start with 'whatsapp:' prefix
    to_formatted = WHATSAPP_TO_NUMBER
    if not to_formatted.startswith("whatsapp:"):
        to_formatted = f"whatsapp:{to_formatted}"
        
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {
        "From": from_number,
        "To": to_formatted,
        "Body": message
    }
    
    try:
        response = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=15)
        response.raise_for_status()
        log_info("WhatsApp notification sent via Twilio.", "WhatsApp")
        return True
    except Exception as e:
        log_error(f"Twilio WhatsApp send failed: {e}", "WhatsApp")
        return False

def send_whatsapp_summary(summary_data: dict) -> bool:
    """
    Dispatches WhatsApp message based on provider configured.
    """
    if WHATSAPP_PROVIDER == "none" or not WHATSAPP_PROVIDER:
        log_info("WhatsApp notification provider set to none. Skipping WhatsApp alert.", "WhatsApp")
        return False
        
    message = format_whatsapp_message(summary_data)
    
    if WHATSAPP_PROVIDER == "ultramsg":
        return send_whatsapp_via_ultramsg(message)
    elif WHATSAPP_PROVIDER == "twilio":
        return send_whatsapp_via_twilio(message)
    else:
        log_error(f"Unsupported WhatsApp provider: '{WHATSAPP_PROVIDER}'", "WhatsApp")
        return False
