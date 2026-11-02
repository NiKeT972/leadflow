"""Demo business profiles: what each business offers (the knowledge base the reply drafter may use) and
sample enquiries to run through the workflow.

All three businesses are fictional, and so are the people in the sample enquiries.
The reply drafter may only quote facts (prices, hours, offers) that appear in the profile; check_reply enforces it.
"""

PROFILES = {
    "ca": {
        "id": "ca",
        "name": "Desai & Rao Chartered Accountants",
        "kind": "CA firm",
        "city": "Andheri East, Mumbai",
        "signature": "Team Desai & Rao\nDesai & Rao Chartered Accountants, Andheri East",
        "hours": "Mon–Sat, 10 am – 7 pm",
        "next_step": "a free 15-minute call with one of our partners",
        "min_deal": 2500,  # below this a lead is low value for the firm
        "services": [
            {"name": "Income tax return (ITR) filing", "price": "₹1,500 – ₹4,000 per return",
             "value": 2500, "keywords": ["itr", "income tax", "tax return", "return filing", "salary", "form 16", "refund"]},
            {"name": "GST registration", "price": "₹2,500 one-time",
             "value": 2500, "keywords": ["gst registration", "gst number", "gstin", "register for gst", "new gst"]},
            {"name": "Monthly GST return filing", "price": "₹1,500 per month",
             "value": 18000, "keywords": ["gst return", "gstr", "gst filing", "monthly gst", "gst compliance", "har mahine", "every month"]},
            {"name": "Private limited company registration", "price": "₹12,000 – ₹18,000 including government fees",
             "value": 15000, "keywords": ["incorporat", "pvt ltd", "private limited", "company registration", "register a company", "startup", "llp"]},
            {"name": "Bookkeeping and accounting", "price": "from ₹5,000 per month",
             "value": 60000, "keywords": ["bookkeeping", "accounting", "accounts", "tally", "zoho books", "books of accounts"]},
            {"name": "Statutory and tax audit", "price": "from ₹25,000",
             "value": 25000, "keywords": ["audit", "tax audit", "statutory audit", "44ab"]},
        ],
        "faq": [
            {"q": "documents", "keywords": ["document", "papers", "what do i need", "kya chahiye"],
             "a": "For ITR filing we need PAN, Aadhaar, Form 16 or income details, bank statements and investment proofs."},
            {"q": "deadline", "keywords": ["deadline", "last date", "due date", "late fee", "penalty"],
             "a": "We'll confirm the exact due date for your case on the call, since it depends on the return type."},
            {"q": "online", "keywords": ["online", "remote", "visit", "office", "come"],
             "a": "Everything can be done online; you're also welcome to visit our Andheri East office."},
        ],
        "support_hint": "existing client",
    },
    "dental": {
        "id": "dental",
        "name": "SmileCraft Dental Clinic",
        "kind": "dental clinic",
        "city": "Thane West",
        "signature": "Front desk, SmileCraft Dental Clinic, Thane West",
        "hours": "Mon–Sat, 10 am – 8 pm; Sunday 10 am – 1 pm",
        "next_step": "a consultation slot with our dentist",
        "min_deal": 500,
        "services": [
            {"name": "Consultation and check-up", "price": "₹500", "value": 500,
             "keywords": ["consult", "check-up", "checkup", "check up", "appointment", "pain", "toothache", "dard"]},
            {"name": "Scaling and cleaning", "price": "₹1,500", "value": 1500,
             "keywords": ["cleaning", "scaling", "stains", "tartar", "plaque"]},
            {"name": "Fillings", "price": "₹1,200 – ₹2,500 per tooth", "value": 1800,
             "keywords": ["filling", "cavity", "cavities", "hole"]},
            {"name": "Root canal treatment", "price": "₹6,000 – ₹9,000 per tooth", "value": 7500,
             "keywords": ["root canal", "rct"]},
            {"name": "Braces and aligners", "price": "₹35,000 – ₹70,000 for the full treatment", "value": 50000,
             "keywords": ["braces", "aligner", "aligners", "crooked", "gap", "orthodont"]},
            {"name": "Teeth whitening", "price": "₹8,000", "value": 8000,
             "keywords": ["whitening", "whiten", "yellow", "bleach"]},
        ],
        "faq": [
            {"q": "emergency", "keywords": ["emergency", "bleeding", "swelling", "broken", "severe", "unbearable"],
             "a": "If you have severe pain, swelling or bleeding, please call the clinic directly so we can see you the same day."},
            {"q": "insurance", "keywords": ["insurance", "cashless", "mediclaim", "emi"],
             "a": "We accept cards and UPI, and offer no-cost EMI on treatments above ₹10,000."},
        ],
        "support_hint": "existing patient",
        "guardrail": "Never diagnose or promise a treatment outcome; the dentist decides after an examination.",
    },
    "coaching": {
        "id": "coaching",
        "name": "BrightPath Coaching Classes",
        "kind": "coaching institute",
        "city": "Dadar West, Mumbai",
        "signature": "Admissions desk, BrightPath Coaching Classes, Dadar West",
        "hours": "Mon–Sat, 9 am – 7 pm",
        "next_step": "a free demo class this Saturday",
        "min_deal": 15000,
        "services": [
            {"name": "JEE Main + Advanced (2-year programme)", "price": "₹1,40,000 for 2 years", "value": 140000,
             "keywords": ["jee", "iit", "engineering entrance", "pcm"]},
            {"name": "NEET (2-year programme)", "price": "₹1,30,000 for 2 years", "value": 130000,
             "keywords": ["neet", "medical entrance", "mbbs", "pcb"]},
            {"name": "Class 10 board coaching (SSC/CBSE)", "price": "₹45,000 per year", "value": 45000,
             "keywords": ["class 10", "10th", "ssc", "cbse", "board exam", "boards"]},
            {"name": "MHT-CET crash course", "price": "₹18,000", "value": 18000,
             "keywords": ["cet", "mht-cet", "mhtcet", "crash course"]},
        ],
        "faq": [
            {"q": "batch", "keywords": ["batch", "timing", "start", "when", "schedule", "weekend"],
             "a": "New batches start every month, with weekday evening and weekend options."},
            {"q": "fees", "keywords": ["installment", "instalment", "emi", "discount", "scholarship"],
             "a": "Fees can be paid in 3 instalments, and we hold a scholarship test on the first Sunday of every month."},
        ],
        "support_hint": "current student",
    },
}

# Sample enquiries per business. They cover every route through the graph:
# hot / warm / cold sales leads, support, partnership, job application, Hinglish and spam.
SAMPLES = {
    "ca": [
        {"id": "ca1", "channel": "email", "from_name": "Rohan Kulkarni", "from_email": "rohan.k@example.com",
         "subject": "Need to register a Pvt Ltd company urgently",
         "body": "Hi, I'm starting a D2C skincare brand with a co-founder and we need to register a private limited company "
                 "this week, since our first investor wants to wire money by the 15th. We'd also need GST registration and "
                 "someone to handle monthly GST returns after that. Budget is around ₹20,000 for the setup. "
                 "Can someone call me? 98201 45678.\n\nThanks,\nRohan Kulkarni"},
        {"id": "ca2", "channel": "web form", "from_name": "Sneha Iyer", "from_email": "sneha.iyer@example.com",
         "subject": "ITR filing",
         "body": "Hello, I'm a salaried employee and also earned some freelance income this year. I need help filing my ITR. "
                 "What documents do I need and what are your charges?"},
        {"id": "ca3", "channel": "whatsapp", "from_name": "Imran Shaikh", "from_email": "",
         "subject": "GST",
         "body": "bhai mera kapde ka shop hai dadar me, GST registration karwana hai aur har mahine return bhi file karna hai. "
                 "kitna charge hoga? jaldi batao, 9867012345"},
        {"id": "ca4", "channel": "email", "from_name": "Meera Joshi", "from_email": "meera@joshidesigns.example.com",
         "subject": "Re: Q2 GST return – invoice mismatch",
         "body": "Hi team, I'm an existing client. The GSTR-2B for last month shows two invoices from my supplier that "
                 "don't match my books. Can you check before you file this month's return? Thanks, Meera"},
        {"id": "ca5", "channel": "email", "from_name": "Growth Hacks Agency", "from_email": "seo@rank-fast.example.com",
         "subject": "Get your website on Google page 1 GUARANTEED!!!",
         "body": "Dear Sir/Madam, we offer guaranteed page 1 ranking, 5000 backlinks and cheap SEO services. "
                 "Click here to claim 70% discount: http://rank-fast.example.com/offer. Limited time offer!!!"},
        {"id": "ca6", "channel": "email", "from_name": "Kunal Mehta", "from_email": "kunal.mehta@example.com",
         "subject": "Article assistant position",
         "body": "Respected Sir, I have cleared CA Intermediate both groups and I'm looking for articleship at your firm. "
                 "I have attached my resume. Please let me know if there is an opening."},
    ],
    "dental": [
        {"id": "d1", "channel": "web form", "from_name": "Ananya Rao", "from_email": "ananya.rao@example.com",
         "subject": "Braces for my daughter",
         "body": "Hi, my 13-year-old daughter has crooked front teeth and her school dentist suggested braces. "
                 "We'd like to start before her summer vacation. What are the options and the cost? You can reach me on 9820098200."},
        {"id": "d2", "channel": "whatsapp", "from_name": "Vikram Patil", "from_email": "",
         "subject": "Tooth pain",
         "body": "kal raat se daant me bahut dard hai and slight swelling also. can I come today evening? urgent please"},
        {"id": "d3", "channel": "email", "from_name": "Priya Nair", "from_email": "priya.nair@example.com",
         "subject": "Cleaning appointment",
         "body": "Hello, I'd like to book a cleaning sometime next week, preferably on Saturday morning. How much does scaling cost?"},
        {"id": "d4", "channel": "email", "from_name": "Dental Supplies Direct", "from_email": "sales@dentsupply.example.com",
         "subject": "Partnership for dental consumables",
         "body": "Dear Doctor, we are a Mumbai-based distributor of dental consumables and would like to partner with your clinic "
                 "for monthly supplies at 15% below MRP. Can we schedule a meeting?"},
        {"id": "d5", "channel": "email", "from_name": "Winner Desk", "from_email": "claims@lucky-draw.example.com",
         "subject": "You have WON ₹25,00,000 lottery",
         "body": "Congratulations! Your email has won a lucky draw of ₹25,00,000. Send your bank details and a processing fee "
                 "to claim your prize now. Click here: http://lucky-draw.example.com"},
    ],
    "coaching": [
        {"id": "c1", "channel": "web form", "from_name": "Suresh Gupta", "from_email": "suresh.gupta@example.com",
         "subject": "JEE coaching for my son",
         "body": "My son is in class 11 (state board) and wants to prepare for JEE. We want to join a batch starting this month. "
                 "Please share fees, instalment options and timings. Phone 9819912345."},
        {"id": "c2", "channel": "whatsapp", "from_name": "Pooja", "from_email": "",
         "subject": "10th boards",
         "body": "hi, 10th ke liye maths science ki coaching chahiye. weekend batch hai kya? fees kitni hai"},
        {"id": "c3", "channel": "email", "from_name": "Arjun Desai", "from_email": "arjun.d@example.com",
         "subject": "Missed class recordings",
         "body": "Hi, I'm a current student in the NEET morning batch. I missed two chemistry lectures last week because I was sick. "
                 "Can I get the recordings or notes?"},
        {"id": "c4", "channel": "email", "from_name": "Nisha Kapoor", "from_email": "nisha.k@example.com",
         "subject": "Physics faculty application",
         "body": "Dear Sir/Madam, I have an M.Sc. in Physics and 4 years of experience teaching JEE physics. "
                 "I would like to apply for a faculty position at BrightPath."},
        {"id": "c5", "channel": "email", "from_name": "Crypto Profits", "from_email": "vip@crypto-x.example.com",
         "subject": "Earn 300% returns in 30 days",
         "body": "Invest in our crypto trading bot and earn 300% guaranteed returns. Join our Telegram VIP group now. "
                 "Click here http://crypto-x.example.com. Limited seats!!!"},
    ],
}


def get_profile(pid: str) -> dict:
    return PROFILES.get(pid) or PROFILES["ca"]


def kb_text(p: dict) -> str:
    """The knowledge base as plain text: the only facts a reply may quote."""
    lines = [f"Business: {p['name']} ({p['kind']}), {p['city']}", f"Hours: {p['hours']}", f"Next step we offer: {p['next_step']}"]
    lines += [f"Service: {s['name']} - {s['price']}" for s in p["services"]]
    lines += [f"FAQ ({f['q']}): {f['a']}" for f in p["faq"]]
    if p.get("guardrail"):
        lines.append(f"Rule: {p['guardrail']}")
    return "\n".join(lines)
