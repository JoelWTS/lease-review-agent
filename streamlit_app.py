import streamlit as st
import pandas as pd
from pypdf import PdfReader
from openai import OpenAI
import json
import re

st.set_page_config(page_title="Lease Review Agent", layout="wide")

st.title("Lease Review Agent")
st.write("Extracts rent review and insurance information from lease PDFs.")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def extract_text_from_pdf(file):
    reader = PdfReader(file)

    text = ""

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        text += f"\n\n--- PAGE {page_num} ---\n{page_text}"

    return text[:120000]


def clean_json(text):
    text = text.strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


def analyse_lease(filename, text):

    prompt = f"""
You are reviewing a UK residential lease for a freehold/ground rent acquisition team.

Your task is to extract ONLY the following information.

Rules:
- Return JSON only.
- If not found, write "Not found".
- If unclear, write "Unclear".
- Include page numbers or clause references wherever possible.
- Be conservative.
- If uncertain, set human_review_required to Yes.

Return JSON in EXACTLY this format:

{{
  "ground_rent": "",
  "review_frequency": "",
  "review_mechanism": "",
  "next_review_date": "",

  "who_insures": "",

  "insurance_payment_position": "",

  "insurance_admin_fee_available": "",

  "insurance_commission_allowed": "",

  "evidence": "",

  "confidence": "",

  "human_review_required": ""
}}

Definitions:

ground_rent
= annual ground rent payable.

review_frequency
= how often the rent is reviewed.

review_mechanism
= RPI, CPI, doubling, fixed increase, market value, etc.

next_review_date
= next rent review date if calculable.

who_insures
= landlord/freeholder, management company, tenant, etc.

insurance_payment_position
= whether landlord pays and recharges, tenant pays directly, insurance rent payable etc.

insurance_admin_fee_available
= whether the lease allows administration fees, management fees or similar charges in relation to insurance recoveries.

insurance_commission_allowed
= whether the landlord is entitled to retain insurance commissions or commissions are expressly permitted.

evidence
= clause references and page references supporting the answers.

Filename:
{filename}

Lease text:
{text}
"""

    response = client.responses.create(
        model="gpt-4.1",
        input=prompt
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

                    text = extract_text_from_pdf(file)

                    result = analyse_lease(
                        file.name,
                        text
                    )

                    result["file"] = file.name

                    results.append(result)

                except Exception as e:

                    results.append(
                        {
                            "file": file.name,
                            "error": str(e),
                            "human_review_required": "Yes"
                        }
                    )

        df = pd.DataFrame(results)

        cols = ["file"] + [c for c in df.columns if c != "file"]
        df = df[cols]

        st.subheader("Results")

        st.dataframe(
            df,
            use_container_width=True
        )

        excel_file = "lease_review_results.xlsx"

        df.to_excel(
            excel_file,
            index=False
        )

        with open(excel_file, "rb") as f:

            st.download_button(
                "Download Excel",
                f,
                file_name=excel_file
            )
