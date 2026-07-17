# AI Job Hunter 🤖💼

AI Job Hunter is a complete, production-ready, and fully local automation system designed to find entry-level software engineering openings (0-2 years, matching a specific resume) in India or Remote, calculate ATS suitability scores using local LLMs, and compile a daily tracking spreadsheet. 

Run everything on your local machine using Docker, keeping all code, resume data, database logs, and API requests 100% private and free.

---

## 🛠 Tech Stack
- **Orchestration**: Docker Compose
- **Pipeline Workflow**: n8n (Community Edition)
- **Scraping & API Integrations**: Python 3, Playwright, BeautifulSoup, Greenhouse & Lever public APIs
- **Database**: PostgreSQL 16
- **Database GUI**: Adminer
- **Local AI & ATS Scoring**: Ollama (`gemma2:2b` or `llama3`)
- **Excel Spreadsheet Builder**: OpenPyXL

---

## 📂 Project Structure
```text
job-hunter-ai/
├── database/
│   ├── init-db.sql       # Database schema creation script
│   ├── backup.sh         # Shell script to backup PostgreSQL database
│   └── restore.sh        # Shell script to restore PostgreSQL database
├── docker/
│   ├── Dockerfile.worker # Playwright & Python FastAPI worker build file
│   └── ollama-init.sh    # Wait script that auto-pulls LLM model on startup
├── resumes/
│   └── resume.pdf        # Place your resume PDF here
├── reports/
│   └── Jobs_YYYY_MM_DD.xlsx # Output daily Excel files saved here
├── scripts/
│   ├── requirements.txt  # Python packages
│   ├── main.py           # FastAPI Web Application entrypoint
│   ├── database.py       # SQLAlchemy ORM model mappings
│   ├── logger.py         # File rotating logger & DB auditor
│   ├── resume_parser.py  # Text parser extracting skills & keywords using Ollama
│   ├── company_scraper.py# Multi-threaded Playwright & API scraper
│   ├── ats_matcher.py    # LLM evaluator mapping ATS matching levels
│   ├── excel_generator.py# OpenPyXL stylized workbook generator
│   ├── duplicate_detector.py # Job hash check preventing multiple entries
│   ├── telegram.py       # Telegram alerts dispatcher
│   ├── whatsapp.py       # Twilio Sandbox & UltraMsg WhatsApp dispatcher
│   ├── email_sender.py   # Daily reports email delivery script
│   └── test_modules.py   # Test suite for unit execution checking
├── workflows/
│   └── job_hunter_workflow.json # n8n workflow export file
├── docker-compose.yml    # Main Docker service blueprint
├── .env                  # Environment configurations and secret tokens
└── README.md             # This document
```

---

## ⚙️ Quick Start Installation

Follow these steps to set up and run AI Job Hunter:

### Step 1: Clone and Configure Environment
1. Copy your resume PDF (named `resume.pdf`) into the `resumes/` directory.
2. Edit the `.env` file in the root directory to customize parameters (keywords, locations, and notification keys):
   ```env
   # PostgreSQL Settings
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=jobhunter_secure_password_123
   POSTGRES_DB=job_hunter

   # Ollama Model choice
   OLLAMA_MODEL=gemma2:2b

   # Scraper filters (comma-separated lists)
   JOB_KEYWORDS=Backend Developer,Software Engineer,Java Developer,Spring Boot Developer
   JOB_LOCATIONS=Bangalore,Hyderabad,Pune,Noida,Gurugram,Remote

   # Telegram Bot (Optional)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   ```

### Step 2: Build & Start Services
Run the following command to build the containers and launch services in background mode:
```bash
docker compose up --build -d
```
Docker will start:
1. **db**: PostgreSQL instance listening on port `5432` (persistent).
2. **adminer**: Database browser GUI on `http://localhost:8080`.
3. **ollama**: LLM engine running on `http://localhost:11434`.
4. **ollama-init**: Helper that checks and automatically pulls the model (e.g., `gemma2:2b`) inside Ollama, then shuts down.
5. **python-worker**: FastAPI server and Interactive Web Dashboard running on `http://localhost:8000`.
6. **n8n**: Workflow automation running on `http://localhost:5678`.

👉 **Interactive Dashboard UI**: Open `http://localhost:8000` in your web browser to view your matched jobs, search/filter listings, update application statuses in real-time, read descriptions, edit notes, and trigger the scraper manually.

### Step 3: Verify Container Health
Wait a couple of minutes for Ollama to finish pulling the model, then check container status:
```bash
docker compose ps
```
You can view application logs by running:
```bash
docker compose logs -f python-worker
```

### Step 4: Import n8n Workflow
1. Open **n8n** in your web browser: `http://localhost:5678`.
2. Follow initial setup prompts to create an account.
3. Click on the left-side **Workflows** tab, choose **Add Workflow** -> **Import from File**.
4. Select `workflows/job_hunter_workflow.json` from this repository.
5. Make sure the HTTP requests show `http://python-worker:8000/...` (since they communicate over the docker network, `python-worker` hostname resolves automatically).
6. Toggle the **Active** slider in the top right to enable the daily Cron scheduler.

---

## 🏃 Test Run & Verification

Before waiting for the daily cron scheduler, you can manually run tests to verify individual Python modules:
1. Run local tests:
   ```bash
   docker compose exec python-worker python scripts/test_modules.py
   ```
2. Trigger the entire pipeline execution manually:
   - Go to your imported n8n workflow and click **Execute Workflow** in the bottom bar, OR
   - Send an HTTP request to the pipeline runner endpoint:
     ```bash
     curl -X POST http://localhost:8000/pipeline/run
     ```
This will parse your resume, search for matching jobs, compute ATS scores, save to PostgreSQL, output `reports/Jobs_YYYY_MM_DD.xlsx`, and send your configured notifications.

---

## 📊 Daily Excel Tracking and Manual Application

The output spreadsheet `reports/Jobs_YYYY_MM_DD.xlsx` is designed as your command center:
1. Open the file inside Microsoft Excel, Google Sheets, or LibreOffice.
2. The columns are sorted by **ATS Score** descending, showcasing the best matches at the top.
3. High ATS scores (`>=80`) are highlighted in **Light Green**, low matches (`<50`) in **Light Red**.
4. Under the **Apply Link** column, click the hyperlink to open the original Greenhouse/Lever/LinkedIn job page directly in your browser.
5. Under the **Apply Email / Contact** column, click the email address (formatted as a clickable `mailto:` link) to draft a direct email to the recruiter.
6. Under the **Status** column, manually change the status (e.g. from `Not Applied` to `Applied` or `Interview Scheduled`) to track your responses.

---

## 💾 Database Backup & Restore

### Backup
Dumps the current schema structure and records to `database/backup_YYYY_MM_DD_HHMMSS.sql`:
```bash
./database/backup.sh
```

### Restore
Restores schema tables and job history from a specified backup script:
```bash
./database/restore.sh ./database/backup_xxxx_xx_xx.sql
```

---

## 🔧 Troubleshooting

#### Ollama connection timeout
If Ollama takes a long time to pull the model during startup, check download progress using:
```bash
docker exec -it job-hunter-ollama ollama list
```
If your laptop does not have a dedicated GPU, downloading and running LLMs will rely on the CPU. The light `gemma2:2b` model is optimized for CPU operations and should respond within 10-15 seconds per job match.

#### Google Search limits/CAPTCHAs
If Google Search blocks requests with a CAPTCHA page:
- Configure the `LINKEDIN_COOKIE` (`li_at`) inside `.env` to enable direct authenticated scraping of LinkedIn Jobs, bypassing google dorks.
- Check the `logs/app.log` file to audit scraper requests.
