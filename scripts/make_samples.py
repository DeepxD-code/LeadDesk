"""Generates the fictional sample data shipped in sample_data/ (run once; output is committed).

sample_data/sops/   3 SOPs: a Word SOP, a PDF SOP, and a Word error-code guide
sample_data/vault/  10 fictional HR documents, 4 of them scans (images / image-only PDF)
All names, numbers and IDs are invented. Replace with the IMS-supplied files when available.
"""
import os
import random

import docx
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
SOP = os.path.join(ROOT, "sops")
VAULT = os.path.join(ROOT, "vault")
os.makedirs(SOP, exist_ok=True)
os.makedirs(VAULT, exist_ok=True)
random.seed(7)

# ============================================================== SOP 1: Claims & Payments (DOCX)
CLAIMS = [
    ("1. Purpose and scope", [
        "This SOP covers claims intake, refunds, duplicate payments and payment holds for the Claims Processing desk. "
        "It applies to both shifts (Morning 06:00-14:30 and Evening 14:00-22:30)."]),
    ("2. Claims intake", [
        "Every claim must have a claim form, a copy of the invoice and a signed declaration before it is keyed in.",
        "If a claim document is missing a signature, do not process it. Mark the case Pending - Docs, send template "
        "MSG-04 (Missing Signature Request) to the client and set a follow-up for 2 working days.",
        "Claims marked High priority must be completed within 4 working hours; Normal claims within 1 working day."]),
    ("3. Refunds", [
        "Refunds are raised in the Refund Register and need approval before release. Never release a refund you raised yourself."]),
    ("3.1 Refund approval limits", [
        "Up to ₹2,000: the processor may approve after a peer check.",
        "₹2,001 to ₹10,000: approval by the Team Lead.",
        "Above ₹10,000: approval by the Operations Manager. Refunds above ₹1,00,000 additionally need sign-off from the Finance Controller.",
        "Attach the approval email to the refund record before release."]),
    ("4. Duplicate payments", [
        "A duplicate payment is the same invoice paid twice to the same payee. Check invoice number, amount and payee before raising it.",
        "Use form DP-07 (Duplicate Payment Reversal Form). Fill in both payment reference numbers, attach both bank "
        "statements and send DP-07 to the Payments Control mailbox.",
        "Payments Control reverses the second payment within 3 working days. Track the case in the Recovery Tracker."]),
    ("5. Payment holds", [
        "Place a payment on hold when the payee bank details changed in the last 30 days, or when the amount differs from the purchase order by more than 5%.",
        "Release a hold only after call-back verification with the payee on the phone number already on file."]),
    ("6. Escalation matrix", [
        "Level 1: Team Lead - process questions, deadlines at risk, workload.",
        "Level 2: Operations Manager - client complaints, refunds above ₹10,000, SLA breach.",
        "Level 3: Head of Delivery - data breach, fraud suspicion, regulatory issues. Fraud suspicion must be reported within 1 hour."]),
]

# ============================================================== SOP 2: Data entry & reconciliation (PDF)
RECON = [
    ("1. SCOPE", ["Applies to Data Entry and Reconciliation tasks for all client accounts handled by the team."]),
    ("2. Shift handover", [
        "The outgoing shift writes a handover note in the team tracker 15 minutes before shift end, listing open items, "
        "items waiting on the client and anything due in the next shift.",
        "Open items older than 2 days must be flagged to the Team Lead in the handover."]),
    ("3. Data entry quality checks", [
        "All amounts above ₹50,000 are double-keyed: a second person enters the amount independently and the system compares both entries.",
        "Dates are entered as DD-MM-YYYY. PAN and GSTIN fields are copied, never retyped.",
        "Target accuracy is 99.5%. A sample of 5% of each person's entries is audited daily."]),
    ("4. Daily reconciliation", [
        "The daily reconciliation cut-off is 6:00 PM IST. Bank statements received after the cut-off are reconciled the next working day.",
        "Match ledger entries to bank statement lines by reference number first, then by amount and date.",
        "Differences of ₹1 or less caused by rounding may be auto-cleared and noted in the rounding log."]),
    ("5. Mismatch handling", [
        "Unmatched items older than 3 working days are moved to the Suspense Report and emailed to the client accountant every Friday.",
        "If a mismatch is above ₹25,000, inform the Team Lead the same day."]),
    ("6. Document checking", [
        "For every new vendor, check: PAN card copy, cancelled cheque, GST certificate and signed vendor form VF-01.",
        "A document is rejected if it is unreadable, expired or the name does not match the vendor master."]),
    ("7. Deadlines and overtime", [
        "Client deadlines are fixed in the daily plan. If you cannot meet a deadline, escalate the task in the dashboard at least 2 hours before it is due.",
        "Overtime needs prior approval from the Team Lead and is capped at 2 hours per day."]),
]

# ============================================================== SOP 3: Error code guide (DOCX)
ERRORS = [
    ("E-101", "Session expired", "Log in again. Unsaved entries are lost; re-key from the source document.", "None"),
    ("E-207", "Mandatory field missing", "The highlighted field is empty. Fill it from the source document and resubmit.", "None"),
    ("E-311", "Invalid IFSC code", "Check the IFSC against the cancelled cheque. If they match, the bank master may be outdated - raise a ticket to Master Data.", "Master Data team"),
    ("402", "Payment authorisation declined (mandate limit exceeded)",
     "Do not retry the payment. Put the payment on hold, check the mandate limit in the Payee Mandate screen, and email "
     "the client to increase the mandate or split the payment. If not resolved within 4 working hours, escalate to the Team Lead.",
     "Team Lead after 4 hours"),
    ("404", "Record not found", "The reference number does not exist. Check for typing errors and for the correct client account.", "None"),
    ("409", "Duplicate record", "A record with the same invoice number exists. Do not create it again; check whether it is a duplicate payment (see Claims SOP section 4, form DP-07).", "Team Lead if a payment was already made"),
    ("422", "Validation failed - amount mismatch", "Invoice amount and claim amount differ. Compare with the source; if the source is correct, add a note and send to the Team Lead.", "Team Lead"),
    ("503", "Bank gateway unavailable", "Wait 15 minutes and retry once. If it fails again, log it in the Incident Register and inform IT Support.", "IT Support"),
]


def make_claims_docx():
    d = docx.Document()
    d.core_properties.title = "Claims and Payments SOP"
    d.add_heading("Claims and Payments SOP", 0)
    d.add_paragraph("Version 3.2 - Owner: Operations Excellence - Fictional sample for LeadDesk demo")
    for head, paras in CLAIMS:
        d.add_heading(head, level=2 if head.startswith("3.1") else 1)
        for p in paras:
            d.add_paragraph(p)
    d.save(os.path.join(SOP, "Claims_and_Payments_SOP.docx"))


def make_recon_pdf():
    styles = getSampleStyleSheet()
    path = os.path.join(SOP, "Data_Entry_and_Reconciliation_SOP.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, title="Data Entry and Reconciliation SOP")
    # Use a font that has the rupee sign; fall back to "Rs." if not available.
    story = [Paragraph("DATA ENTRY AND RECONCILIATION SOP", styles["Title"]),
             Paragraph("Version 2.0 - fictional sample for LeadDesk demo", styles["Normal"]), Spacer(1, 12)]
    for head, paras in RECON:
        story.append(Paragraph(head, styles["Heading2"]))
        for p in paras:
            story.append(Paragraph(p.replace("₹", "Rs. "), styles["Normal"]))
            story.append(Spacer(1, 4))
    doc.build(story)


def make_errors_docx():
    d = docx.Document()
    d.core_properties.title = "Error Code Guide"
    d.add_heading("Error Code Guide", 0)
    d.add_paragraph("What to do when the processing system shows an error. Fictional sample for LeadDesk demo.")
    for code, meaning, action, esc in ERRORS:
        d.add_heading(f"Error {code} - {meaning}", level=1)
        d.add_paragraph(f"Meaning: {meaning}.")
        d.add_paragraph(f"What to do: {action}")
        d.add_paragraph(f"Escalate to: {esc}.")
    d.save(os.path.join(SOP, "Error_Code_Guide.docx"))


# ============================================================== Vault documents (fictional)

def font(size, bold=False):
    for name in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def scan(lines, path, title=None, size=(1240, 1754), rotate=1.2, quality=72, card=False):
    """Render text like a phone photo / scanner image: slight rotation, noise, blur, JPEG artefacts."""
    img = Image.new("L", size, 248)
    dr = ImageDraw.Draw(img)
    y = 90
    if title:
        dr.text((90, y), title, font=font(46 if not card else 40, True), fill=20); y += 90
    for ln in lines:
        dr.text((90, y), ln, font=font(30 if not card else 32), fill=30)
        y += 50 if ln else 30
    if card:
        dr.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=60, width=4)
        dr.rectangle([size[0] - 300, 130, size[0] - 80, 400], outline=90, width=3)
        dr.text((size[0] - 260, 250), "PHOTO", font=font(34), fill=120)
    noise = Image.effect_noise(size, 18)
    img = Image.blend(img, noise, 0.08).filter(ImageFilter.GaussianBlur(0.6))
    img = img.rotate(rotate, expand=True, fillcolor=210)
    if path.endswith(".pdf"):
        img.convert("RGB").save(path, "PDF", resolution=150)
    else:
        img.convert("RGB").save(path, quality=quality)


def typed_pdf(path, title, paras):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, title=title)
    story = [Paragraph(title, styles["Title"])]
    for p in paras:
        story += [Paragraph(p, styles["Normal"]), Spacer(1, 8)]
    doc.build(story)


def typed_docx(path, title, paras):
    d = docx.Document()
    d.add_heading(title, 0)
    for p in paras:
        d.add_paragraph(p)
    d.save(path)


def make_vault():
    # Typed documents (6)
    typed_pdf(os.path.join(VAULT, "EMP0001_offer_letter.pdf"), "Offer Letter", [
        "Northwind Back-Office Services Pvt. Ltd. (fictional)", "Date: 02-01-2025",
        "Dear Riya Sharma (Employee ID EMP0001),",
        "We are pleased to offer you the position of Process Associate - Claims Processing. Your annual cost to company (CTC) "
        "will be Rs. 3,60,000. Your date of joining is 15-01-2025 at our Ahmedabad delivery centre.",
        "This offer is subject to verification of your documents. Please sign and return a copy of this letter.",
        "Sincerely, Head - Human Resources"])
    typed_docx(os.path.join(VAULT, "EMP0002_appraisal_2025.docx"), "Annual Performance Appraisal 2025", [
        "Employee: Arjun Mehta (EMP0002) - Department: Operations", "Review period: April 2024 to March 2025",
        "Overall rating: 4 out of 5 - Exceeds expectations.",
        "Strengths: accuracy in reconciliation, mentoring new joiners. Goals for next year: lead the evening shift handover.",
        "Increment recommended: 9%."])
    typed_pdf(os.path.join(VAULT, "EMP0120_offer_letter.pdf"), "Offer Letter", [
        "Northwind Back-Office Services Pvt. Ltd. (fictional)", "Dear Kabir Nair (Employee ID EMP0120),",
        "We are pleased to offer you the role of Senior Accountant in the Finance department with an annual CTC of Rs. 9,40,000. "
        "Date of joining: 01-03-2025.", "Sincerely, Human Resources"])
    typed_docx(os.path.join(VAULT, "EMP0121_appraisal.docx"), "Performance Review", [
        "Employee: Meera Iyer (EMP0121) - Finance", "Review period: FY 2024-25. Overall rating: 3 out of 5 - Meets expectations.",
        "Self-assessment and manager comments attached. Goals for next year: close month-end books one day earlier."])
    typed_pdf(os.path.join(VAULT, "EMP0003_warning_letter.pdf"), "Warning Letter", [
        "To: Sahil Verma (EMP0003), Operations", "This letter records repeated late log-ins on the morning shift in October. "
        "Further instances may lead to disciplinary action.", "Human Resources (fictional sample)"])
    typed_docx(os.path.join(VAULT, "EMP0210_offer_letter.docx"), "Offer Letter", [
        "Dear Tanvi Desai (Employee ID EMP0210),", "We are pleased to offer you the position of Sales Executive. "
        "Annual CTC Rs. 5,20,000 plus variable pay. Date of joining 10-02-2025.", "Human Resources (fictional)"])
    # Scanned documents (4)
    scan(["Northwind Back-Office Services Pvt. Ltd. (fictional)", "", "Date: 20-12-2024", "",
          "Dear Riya Sharma, Employee ID EMP0001", "",
          "Further to our offer letter, we confirm a one-time relocation", "bonus of Rs. 50,000 payable with your first salary,",
          "to support your move from Surat to Ahmedabad.", "", "This amount is recoverable if you leave within",
          "12 months of your date of joining.", "", "Signed: Head - Human Resources", "",
          "Accepted by: Riya Sharma  (signature)"],
         os.path.join(VAULT, "EMP0001_relocation_offer_addendum_scan.jpg"), title="OFFER LETTER - ADDENDUM")
    scan(["SPECIMEN - NOT A REAL DOCUMENT", "", "Name: Riya Sharma", "Employee ID: EMP0001",
          "Date of Birth: 14-08-1999", "Identity No: SMPL 4821 7730 0915", "Address: 12 Lake View Road,",
          "Ahmedabad, Gujarat"], os.path.join(VAULT, "EMP0001_id_proof_scan.png"),
         title="IDENTITY CARD (SAMPLE)", size=(1300, 820), rotate=-1.5, card=True)
    scan(["Employee: Kabir Nair    Employee ID: EMP0120", "Department: Finance", "Review period: FY 2024-25", "",
          "Overall rating: 5 out of 5 - Outstanding", "", "Manager comments: Kabir automated the vendor",
          "reconciliation and cut month-end closing time by two days.", "", "Increment recommended: 12%",
          "", "Signed: Finance Controller"], os.path.join(VAULT, "EMP0120_appraisal_scan.pdf"),
         title="PERFORMANCE APPRAISAL", rotate=0.8)
    scan(["SPECIMEN - NOT A REAL DOCUMENT", "", "Name: Arjun Mehta", "Employee ID: EMP0002",
          "Passport No: S0000000 (sample)", "Date of Birth: 03-02-1997", "Place of issue: Ahmedabad"],
         os.path.join(VAULT, "EMP0002_passport_scan.jpg"), title="PASSPORT - ID PROOF (SAMPLE)",
         size=(1300, 820), rotate=1.8, card=True)


if __name__ == "__main__":
    make_claims_docx(); make_recon_pdf(); make_errors_docx(); make_vault()
    for d in (SOP, VAULT):
        for f in sorted(os.listdir(d)):
            print(os.path.join(os.path.basename(d), f), os.path.getsize(os.path.join(d, f)))
