# JOBOT: AI-Powered LinkedIn & Email Outreach Platform

Explore Jobot live at: https://inconnect.streamlit.app/

Jobot is a production-grade platform that streamlines your outreach workflow by combining Retrieval-Augmented Generation (RAG) with automated delivery on LinkedIn and Gmail. From bulk CSV imports to AI-crafted message previews, Jobot turns tedious networking into a one-click, high-impact campaign.

---

## Key Capabilities

- 🔐 **Secure Credentials**  
  Collect and validate LinkedIn & Gmail login details in-memory with end-to-end encryption.

- 📥 **Flexible Recipient Import**  
  Manually add individual contacts or upload CSVs of names, organizations, and positions—headers auto-normalized for you.

- 🤖 **AI-Driven Message Generation**  
  Parse your résumé and job description, retrieve relevant context via embeddings (all-MiniLM-L6-v2 + ChromaDB), and draft personalized subject lines & bodies with tiny-GPT2.

- 🔗 **LinkedIn Automation**  
  Launch a stealth, headless browser to search profiles by name/org/role and send your tailored messages—all with built-in retries and JS fallbacks.

- 📧 **Gmail Automation**  
  Discover professional email addresses via Hunter.io (or fallback heuristics), compose in Gmail’s web UI, and send via Selenium automation.

- 📊 **Live Feedback & Logging**  
  Track per-recipient success or failure, watch a real-time progress bar, and review encrypted, rotating logs for full auditability.

---

## Project Structure

```plaintext
JOBOT/
├── app.py                      # Streamlit entrypoint & UI orchestration      
├── requirements.txt            # Python dependencies
├── scripts/                    # Core automation & RAG modules
│   ├── email_id_finder.py      # Find email id through hunter.io API
│   ├── message_generator.py    # Chunking, embedding, ChromaDB index & retrieval, tiny-GPT2 prompt construction & generation
│   ├── linkedin_automation.py  # Selenium-based LinkedIn messaging with fallbacks
│   └── email_automation.py     # Hunter.io lookup & Gmail automation
└── README.md                   # Product overview & setup guide
```

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/malavikasubramanian/BDMLS_FINALCODE_PROJECT_JOB-BOT.git
cd JOBOT

```
### 2. Install dependencies

```bash
pip install -r requirements.txt
```
### 3. Set up environment variables
Create a `.env` file in the root directory and add your credentials:

```plaintext
# .env file
HUNTER_API_KEY=your_hunter_api_key
GMAIL_EMAIL=your_gmail_email
GMAIL_PASSWORD=your_gmail_password
```
### 4. Run the application

```bash
streamlit run app.py
```

