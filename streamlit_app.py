import streamlit as st
import pandas as pd
from pypdf import PdfReader
from openai import OpenAI
import json

st.set_page_config(page_title="Lease Rent Review Agent", layout="wide")

st.title("Lease Rent Review Agent")

client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

def extract_text_from_pdf(file):
    reader = PdfReader(file)

    text = ""

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()

        if page_text:
            text += f"\n\n--- PAGE {page_num} ---\n{page_text}"

    return text[:120000]

def analyse_lease(filename, text):

    prompt = f"""
You are reviewing a UK lease.

Extract:

1. Ground rent amount
2. Rent review frequency
3. Rent review mechanism
4. Next review date if calculable
5. Evidence clause or page reference
6. Confidence (High, Medium, Low)
7. Human review required (Yes or No)

Return JSON only.

Filename:
{filename}

Lease text:
{text}
"""

    response = client.responses.create(
        model="gpt-4.1",
        input=prompt
    )

    return json.loads(response.output_text)

uploaded_files = st.file_uploader(
    "Upload lease PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:

    if st.button("Extract Rent Review Information"):

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

        st.subheader("Results")

        st.dataframe(
            df,
            use_container_width=True
        )

        excel_file = "lease_results.xlsx"

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
