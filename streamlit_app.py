import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import fitz
import base64
from datetime import date, datetime

st.set_page_config(page_title="Lease Review Agent", layout="wide")

st.title("Lease Review Agent")
st.write("Extracts rent review and insurance information from lease PDFs.")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def clean_json(text):
    text = text.strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


def selected_page_numbers(total_pages):
    pages = set()

    # front pages usually contain parties, rent definitions and property info
    for i in range(0, min(8, total_pages)):
        pages.add(i)

    # middle pages often contain insurance/tenant covenants
    for i in range(14, min(23, total_pages)):
        pages.add(i)

    # back pages often contain rent review schedules
    for i in range(max(0, total_pages - 10), total_pages):
        pages.add(i)

    return sorted(pages)


def pdf_pages_to_images(file):
    file_bytes = file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    images = []

    for page_number in selected_page_numbers(len(doc)):
        page = doc[page_number]
        pix = page.get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        images.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{img_base64}"
        })

    return images


def parse_date(value):
    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d-%m-%Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            pass

    return None


def extract_year_gap(review_frequency, review_mechanism):
    text = f"{review_frequency} {review_mechanism}".lower()

    if "ten" in text or "10" in text or "tenth" in text:
        return 10
    if "twenty five" in text or "25" in text:
        return 25
    if "five" in text or "5" in text:
        return 5
    if "annual" in text or "yearly" in text or "each year" in text:
        return 1

    return None


def calculate_next_future_review(first_review_date, review_frequency, review_mechanism):
    first_date = parse_date(first_review_date)

    if not first_date:
        return "Unclear"

    gap = extract_year_gap(review_frequency, review_mechanism)

    if not gap:
        return "Unclear"

    today = date.today()
    next_date = first_date

    while next_date <= today:
        try:
            next_date = next_date.replace(year=next_date.year + gap)
        except ValueError:
            next_date = next_date.replace(month=2, day=28, year=next_date.year + gap)

    return next_date.strftime("%d %B %Y")


def analyse_lease(filename, images):
    today = date.today().isoformat()

    prompt = f"""
You are reviewing a UK residential lease for a freehold and ground rent acquisition team.

Today is {today}.

Extract ONLY the following information.

Return JSON only in exactly this structure:

{{
  "ground_rent": "",
  "first_review_date": "",
  "review_frequency": "",
  "review_mechanism": "",
  "next_future_review_date": "",
  "who_insures": "",
  "insurance_payment_position": "",
  "insurance_admin_fee_available": "",
  "insurance_commission_allowed": "",
  "evidence": "",
  "confidence": "",
  "human_review_required": ""
}}

Important:
- first_review_date is the first rent review date in the lease.
- next_future_review_date must be AFTER today's date.
- Example: if first_review_date is 1 January 2026, review_frequency is every 10 years, and today is after 1 January 2026, then next_future_review_date is 1 January 2036.
- Do not repeat a past review date as the next_future_review_date.
- For insurance_admin_fee_available, look for wording allowing admin fees, management fees, charges, expenses, costs, commission, or similar sums in connection with insurance or insurance recharges.
- If the lease only allows recovery of insurance premium but no admin/management fee, say "No express admin fee found".
- If the tenant insures directly but the landlord can insure after default and recover the cost, say that clearly.

Rules:
- If not found write "Not found".
- If unclear write "Unclear".
- Be conservative.
- Include page references and clause references wherever possible.
- If uncertain set human_review_required to Yes.

Filename:
{filename}
"""

    content = [{"type": "input_text", "text": prompt}] + images

    response = client.responses.create(
        model="gpt-4.1",
        input=[
            {
                "role": "user",
                "content": content
            }
        ]
    )

    output = clean_json(response.output_text)
    result = json.loads(output)

    result["next_future_review_date"] = calculate_next_future_review(
        result.get("first_review_date", ""),
        result.get("review_frequency", ""),
        result.get("review_mechanism", "")
    )

    return result


uploaded_files = st.file_uploader(
    "Upload lease PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Extract Lease Information"):
        results = []

        for file in uploaded_files:
            with st.spinner(f"Reviewing {file.name}..."):
                try:
                    images = pdf_pages_to_images(file)
                    result = analyse_lease(file.name, images)
                    result["file"] = file.name
                    results.append(result)

                except Exception as e:
                    results.append({
                        "file": file.name,
                        "error": str(e),
                        "human_review_required": "Yes"
                    })

        df = pd.DataFrame(results)

        cols = ["file"] + [c for c in df.columns if c != "file"]
        df = df[cols]

        st.subheader("Results")
        st.dataframe(df, use_container_width=True)

        excel_file = "lease_review_results.xlsx"
        df.to_excel(excel_file, index=False)

        with open(excel_file, "rb") as f:
            st.download_button(
                "Download Excel",
                f,
                file_name=excel_file
            )
