import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import fitz
import base64
import io

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

    prompt = f"""
You are reviewing a UK residential lease for a freehold/ground rent acquisition team.

Extract ONLY the following:

1. Ground rent
2. Review frequency
3. Review mechanism
4. Next review date if calculable
5. Who insures
6. Insurance payment position:
   - landlord/freeholder pays and recharges tenant
   - tenant insures directly
   - insurance rent payable
   - unclear
7. Whether an insurance admin fee, management fee or commission can be charged/retained
8. Evidence page/clause references
9. Confidence
10. Human review required

Return JSON only in exactly this structure:

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

Rules:
- If not found, write "Not found".
- If unclear, write "Unclear".
- Be conservative.
- Include page references wherever possible.

Filename: {filename}
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
