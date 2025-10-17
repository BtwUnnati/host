import imaplib, email, os, time, re
from dotenv import load_dotenv

load_dotenv()
EMAIL = os.getenv("IMAP_EMAIL")
PASSWORD = os.getenv("IMAP_PASSWORD")
SERVER = os.getenv("IMAP_SERVER")

def check_new_payments():
    mail = imaplib.IMAP4_SSL(SERVER)
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")
    _, data = mail.search(None, 'UNSEEN')
    for num in data[0].split():
        _, msg_data = mail.fetch(num, "(RFC822)")
        raw = email.message_from_bytes(msg_data[0][1])
        subj = raw["subject"]
        if "received" in subj.lower() or "credit" in subj.lower():
            amt = re.findall(r"₹\s?(\d+)", subj)
            if amt:
                print(f"💰 Payment received: ₹{amt[0]}")
    mail.logout()

if __name__ == "__main__":
    while True:
        check_new_payments()
        time.sleep(60)
