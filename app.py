import os
import io
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
import PyPDF2
import docx
from dotenv import load_dotenv
from selenium.webdriver.support.ui import WebDriverWait

from scripts.EmailAutomation    import setup_email_driver, send_email as send_email_batch
from scripts.LinkedInAutomation import (
    _js_close_overlay,
    setup_driver,
    login_to_linkedin,
    construct_search_url,
    select_people_tab,
    open_first_profile,
    send_message_on_profile,
)
from scripts.email_id_finder    import get_domain_from_organization, find_email
from scripts.message_generator  import generate_outreach

load_dotenv()
st.set_page_config(page_title=" JOB BOT", page_icon=":robot_face:", layout="wide")
st.title("JOB BOT")

# ───────────────── Session Defaults ─────────────────
for key in ("linkedin_message", "email_message", "email_subject"):
    st.session_state.setdefault(key, "")

# ───────────────── Sidebar Credentials ─────────────────
st.sidebar.header("Your Credentials")
linkedin_email    = st.sidebar.text_input("LinkedIn Username")
linkedin_password = st.sidebar.text_input("LinkedIn Password", type="password")
gmail_email       = st.sidebar.text_input("Gmail Email")
gmail_password    = st.sidebar.text_input("Gmail Password", type="password")

# ───────────────── Recipient Information ─────────────────
st.header("Recipient Information")
recipient_name = st.text_input("Recipient Full Name")
organization   = st.text_input("Organization")
position       = st.text_input("Position (Optional)")

# ───────────────── Generate Outreach ─────────────────
# We'll still let them preview one example up front, but for CSV we
# will regenerate per-row anyway.
st.header("Generate Outreach Message (Preview)")
resume_file = st.file_uploader("Upload Résumé", type=["pdf","docx","txt"])
jd_mode     = st.radio("Provide Job Description", ["Upload file","Paste text"])
if jd_mode == "Upload file":
    jd_file = st.file_uploader("Upload Job Description", type=["pdf","docx","txt"])
    jd_text = ""
else:
    jd_file = None
    jd_text = st.text_area("Paste Job Description")
extra_note = st.text_area("Additional note / instructions (optional)")
max_chars  = st.number_input(
    "Maximum characters for message (0 = unlimited)",
    min_value=0, value=0, step=50
)

def parse_to_text(uploaded):
    if not uploaded:
        return ""
    raw = uploaded.getvalue()
    suf = Path(uploaded.name).suffix.lower()
    if suf == ".pdf":
        reader = PyPDF2.PdfReader(io.BytesIO(raw))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if suf in {".docx", ".doc"}:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
            tmp.write(raw); tmp.flush()
            text = "\n".join(p.text for p in docx.Document(tmp.name).paragraphs)
        os.unlink(tmp.name)
        return text
    return raw.decode("utf-8", errors="ignore")

if st.button("✨ Generate Preview Message"):
    if not resume_file:
        st.error("Please upload your résumé.")
    elif not (jd_file or jd_text.strip()):
        st.error("Please provide a job description.")
    else:
        with st.spinner("Generating outreach message…"):
            resume_txt = parse_to_text(resume_file)
            jd_txt     = parse_to_text(jd_file) if jd_file else jd_text

            # preview for whatever fields are filled in
            subj, msg = generate_outreach(
                resume_txt=resume_txt,
                jd_txt=jd_txt,
                recipient=recipient_name or "Hiring Manager",
                company=organization or "",
                top_k=10,
                max_chars=max_chars,
                extra=extra_note,
            )

            # strip any "Subject:" prefix
            if msg.lower().startswith("subject:"):
                lines = msg.splitlines()
                subj  = lines[0].split(":",1)[1].strip()
                msg   = "\n".join(lines[1:]).strip()

            st.session_state["email_subject"]    = subj
            st.session_state["linkedin_message"] = msg
            st.session_state["email_message"]    = msg

        st.success("Preview generated! Tweak it or upload a CSV to batch–below.")

# ───────────────── Message Details ─────────────────
st.header("Message Details")
st.text_area("LinkedIn Message (Preview)", key="linkedin_message", height=200)
st.text_input("Email Subject (Preview)",    key="email_subject")
st.text_area("Email Message (Preview)",    key="email_message", height=200)

# ───────────────── Bulk CSV Uploads ─────────────────
st.sidebar.header("Bulk Upload (Optional)")
linkedin_csv = st.sidebar.file_uploader(
    "CSV for LinkedIn",
    type=["csv"],
    help="Columns: name,organization,position",
    key="linkedin_csv"
)
email_csv    = st.sidebar.file_uploader(
    "CSV for Email",
    type=["csv"],
    help="Columns: name,organization",
    key="email_csv"
)

# ───────────────── LinkedIn Automation ─────────────────
if st.button("🔗 Automate LinkedIn"):
    base_msg = st.session_state["linkedin_message"]
    if not base_msg:
        st.error("Please generate a preview message first.")
        st.stop()
    if not (linkedin_email and linkedin_password):
        st.error("Fill in your LinkedIn credentials in the sidebar.")
    elif not linkedin_csv and not (recipient_name and organization):
        st.error("Provide either a single recipient or upload a CSV.")
    else:
        with st.spinner("Automating LinkedIn…"):
            driver = setup_driver()
            wait   = WebDriverWait(driver, 20)
            try:
                # 1) log in once
                login_to_linkedin(driver, wait, linkedin_email, linkedin_password)

                # 2) build recipients list
                if linkedin_csv:
                    df = pd.read_csv(linkedin_csv)
                    recipients = df.to_dict(orient="records")
                else:
                    recipients = [{
                        "name": recipient_name,
                        "organization": organization,
                        "position": position
                    }]

                # 3) loop and generate/send per-person
                resume_txt = parse_to_text(resume_file) if resume_file else ""
                jd_txt      = parse_to_text(jd_file) if jd_file else jd_text
                for rec in recipients:
                    nm  = rec.get("name")
                    org = rec.get("organization")
                    pos = rec.get("position", "")

                    # personalize: replace "Hiring Manager" if present
                    msg = base_msg
                    msg = msg.replace("Hiring Manager", nm) if nm else msg

                    driver.get(construct_search_url(nm, org, pos))
                    select_people_tab(driver, wait)
                    profile_url = open_first_profile(driver, wait)
                    if not profile_url:
                        st.warning(f"❌ Profile not found for {nm} at {org}")
                        continue

                    send_message_on_profile(driver, wait, msg)
                    st.success(f"✅ Message sent to {nm} at {org}")

                    #close the overlay if it’s still open
                    # closed = _js_close_overlay(driver, wait)
                    # if not closed:
                    #     st.warning("⚠️ Close button not found—overlay may still be open.")

            except Exception as e:
                st.error(f"LinkedIn automation error: {e}")
            finally:
                driver.quit()

# ───────────────── Email Automation ─────────────────
if st.button("📧 Automate Email"):
    subj     = st.session_state["email_subject"]
    base_msg = st.session_state["email_message"]

    if not base_msg:
        st.error("Please generate a preview message first.")
        st.stop()

    if not (gmail_email and gmail_password):
        st.error("Fill in your Gmail credentials in the sidebar.")
        st.stop()

    if not email_csv and not (recipient_name and organization):
        st.error("Provide either a single recipient or upload a CSV.")
        st.stop()

    with st.spinner("Automating Email…"):
        # Build recipients list
        if email_csv:
            df = pd.read_csv(email_csv)
            # tolerate either 'domain' or 'Domain' column
            df.columns = [c.lower().strip() for c in df.columns]
            if "domain" not in df.columns:
                st.error("CSV must contain a 'domain' column.")
                st.stop()
            recipients = df.to_dict(orient="records")
        else:
            recipients = [{
                "name": recipient_name,
                "domain": organization
            }]

        # 1) launch & login once (headless)
        driver, wait = setup_email_driver(
            gmail_email,
            gmail_password
        )

        # 2) loop, personalise & send per-person
        resume_txt = parse_to_text(resume_file) if resume_file else ""
        jd_txt      = parse_to_text(jd_file) if jd_file else jd_text

        for rec in recipients:
            nm     = rec.get("name", "").strip()
            dom_in = rec.get("domain", "").strip()
            domain = get_domain_from_organization(dom_in)
            if not domain:
                st.warning(f"❌ Domain not found for {dom_in}")
                continue

            email_addr = find_email(nm, domain)
            if not email_addr:
                st.warning(f"❌ E-mail not found for {nm}")
                continue
            st.success(f"✅ Email found for {nm}: <{email_addr}>")
            # personalise the template per row
            msg = base_msg
            if nm:
                msg = msg.replace("Hiring Manager", nm)

            try:
                send_email_batch(
                    driver, wait,
                    receiver_email=email_addr,
                    subject=subj,
                    message_body=msg,
                )
                st.success(f"✅ Email sent to {nm} <{email_addr}>")
            except Exception as e:
                st.error(f"Error sending to {nm}: {e}")

        # 3) only quit when all rows are done
        driver.quit()
