import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from scripts.logger import log_info, log_error

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

def send_email_report(summary_data: dict) -> bool:
    """
    Emails the daily job summary HTML and attaches the generated Excel report.
    """
    if not EMAIL_ENABLED:
        log_info("Email notifications disabled. Skipping email report.", "EmailSender")
        return False

    if not SMTP_USER or not SMTP_PASSWORD or not EMAIL_TO:
        log_error("SMTP configuration or destination email missing. Skipping email report.", "EmailSender")
        return False

    today_str = summary_data.get("date", "")
    total_jobs = summary_data.get("total_jobs", 0)
    high_prio = summary_data.get("high_priority", 0)
    highest_ats = summary_data.get("highest_ats", 0)
    highest_ats_company = summary_data.get("highest_ats_company", "N/A")
    highest_ats_title = summary_data.get("highest_ats_title", "N/A")
    excel_path = summary_data.get("excel_path", "")
    top_companies = ", ".join(summary_data.get("top_companies", [])) if summary_data.get("top_companies") else "None"

    # Email Subject
    subject = f"AI Job Hunter Daily Report - {today_str} ({total_jobs} New Openings)"

    # HTML Body
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6;">
        <h2 style="color: #1F4E78; border-bottom: 2px solid #1F4E78; padding-bottom: 8px;">🤖 AI Job Hunter Daily Summary</h2>
        <p>Hello,</p>
        <p>Here is your daily automated digest of software engineering openings matching your resume profile for <strong>{today_str}</strong>.</p>
        
        <table style="border-collapse: collapse; width: 100%; max-width: 600px; margin-bottom: 20px;">
          <tr style="background-color: #f2f2f2;">
            <th style="border: 1px solid #dddddd; text-align: left; padding: 8px; width: 50%;">Metric</th>
            <th style="border: 1px solid #dddddd; text-align: left; padding: 8px;">Detail</th>
          </tr>
          <tr>
            <td style="border: 1px solid #dddddd; padding: 8px;"><strong>Total Openings Found</strong></td>
            <td style="border: 1px solid #dddddd; padding: 8px; color: #0056b3;"><strong>{total_jobs}</strong></td>
          </tr>
          <tr>
            <td style="border: 1px solid #dddddd; padding: 8px;"><strong>High Match Openings (ATS >= 80)</strong></td>
            <td style="border: 1px solid #dddddd; padding: 8px; color: #28a745;"><strong>{high_prio}</strong></td>
          </tr>
          <tr>
            <td style="border: 1px solid #dddddd; padding: 8px;"><strong>Top Companies Hiring</strong></td>
            <td style="border: 1px solid #dddddd; padding: 8px;">{top_companies}</td>
          </tr>
          <tr style="background-color: #fafafa;">
            <td style="border: 1px solid #dddddd; padding: 8px;"><strong>Highest ATS Match</strong></td>
            <td style="border: 1px solid #dddddd; padding: 8px;">
              <span style="background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 4px; font-weight: bold;">
                {highest_ats}% Match
              </span><br>
              {highest_ats_title} at <strong>{highest_ats_company}</strong>
            </td>
          </tr>
        </table>
        
        <p>The complete Excel report containing direct application URLs and contact email addresses has been compiled and is attached to this email.</p>
        <p><strong>Attachment:</strong> <code>{os.path.basename(excel_path)}</code></p>
        
        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
        <p style="font-size: 11px; color: #888888;">This is an automated report generated locally on your machine by AI Job Hunter.</p>
      </body>
    </html>
    """

    # Setup MIME Message
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = EMAIL_TO
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    # Attach Excel file
    if excel_path and os.path.exists(excel_path):
        try:
            with open(excel_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {os.path.basename(excel_path)}"
            )
            msg.attach(part)
        except Exception as attach_err:
            log_error(f"Failed to attach Excel file to email: {attach_err}", "EmailSender")

    # Connect to SMTP server and send
    try:
        log_info(f"Connecting to SMTP server {SMTP_HOST}:{SMTP_PORT}...", "EmailSender")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls() # Enable security
        server.login(SMTP_USER, SMTP_PASSWORD)
        
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        server.quit()
        
        log_info("Email report sent successfully.", "EmailSender")
        return True
    except Exception as e:
        log_error(f"Failed to send email report: {e}", "EmailSender")
        return False
