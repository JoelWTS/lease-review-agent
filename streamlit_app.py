import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import fitz
import base64
from datetime import date

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


def pdf_pages_to_images(file, max_pages=40):
    file_bytes = file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []

    for page_number in range(min(len(doc), max_pages)):
        page = doc[page_number]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        images.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{img_base64}"
        })

    return images


def analyse_lease(filename, images):
    today = date.today().isoformat()

    prompt = f"""
You are reviewing a UK residential lease for a freehold/ground rent acquisition team.

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

Definitions:
- ground_rent = annual rent payable under the lease.
- first_review_date = the first rent review date in the lease.
- review_frequency = how often rent is reviewed after the first review.
- review_mechanism = RPI, CPI, doubling, fixed uplift, open market, etc.
- next_future_review_date = the next review date after today's date. If the first review date has passed, calculate the next one using the review frequency.
- who_insures = tenant, landlord/freeholder, management company, etc.
- insurance_payment_position = tenant insures directly OR landlord insures and recharges OR insurance rent payable OR unclear.
- insurance_admin_fee_available = whether landlord/freeholder can add an admin/management fee to insurance recharges.
- insurance_commission_allowed = whether landlord/freeholder can retain insurance commission.

Rules:
- If not found, write "Not found".
- If unclear, write "Unclear".
- Include page/clause references.
- Be conservative.
- If uncertain, human_review_required = Yes.

Filename: {filename}
"""

    content = [{"type": "input_text", "text": prompt}] + images

    response = client.responses.create(
        model="gpt-4.1",
        input=[{"role": "user", "content": content}]
    )

    output = clean_json(response.output_text)
    return json.loads(output)


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
