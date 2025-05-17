import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
import google.generativeai as genai

# --- CONFIG ---
genai.configure(api_key="AIzaSyDshX83nZWolqTXvpf1--fU2VvCfOexucQ")  # Use environment variable
model = genai.GenerativeModel("models/gemini-1.5-flash")

st.set_page_config(page_title="UPI Financial Analyzer", layout="wide")
st.title("📊 UPI Personal Financial Analyzer with Gemini")

# --- FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload your UPI PDF file", type=["pdf"])

if uploaded_file:
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            raw_text = "\n".join([page.extract_text() for page in pdf.pages])

        # --- EXTRACT TRANSACTIONS ---
        transactions = re.split(r'Google Pay\s*Paid', raw_text)[1:]
        structured_data = []

        for txn in transactions:
            txn = 'Paid' + txn
            match_payment = re.search(r'Paid ₹([\d,.]+) to (.*?) using', txn)
            match_datetime = re.search(r'(\d{1,2} \w+ 2025), (\d{2}:\d{2}:\d{2})', txn)
            match_description = re.search(r'(Paid ₹[\d,.]+ to .*?using.*)', txn)

            if match_payment and match_datetime:
                amount = float(match_payment.group(1).replace(',', ''))
                receiver = match_payment.group(2).strip()
                date = match_datetime.group(1)
                time = match_datetime.group(2)
                description = match_description.group(1).strip() if match_description else ""

                structured_data.append({
                    "Date": date,
                    "Time": time,
                    "Amount": amount,
                    "Receiver": receiver,
                    "Description": description
                })

        df = pd.DataFrame(structured_data)
        df['Date'] = pd.to_datetime(df['Date'], format='%d %b %Y', errors='coerce')
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df['Description'] = df['Description'].str.lower().str.strip()

        # --- CATEGORY TAGGING ---
        def categorize(desc):
            if any(x in desc for x in ["zepto", "grocery", "dmart", "big bazaar"]): return "Groceries"
            if any(x in desc for x in ["zomato", "swiggy", "food", "delivery"]): return "Food Delivery"
            if any(x in desc for x in ["netflix", "hotstar", "spotify"]): return "Entertainment"
            if any(x in desc for x in ["flipkart", "amazon", "myntra"]): return "Shopping"
            if any(x in desc for x in ["electricity", "gas", "water", "bill"]): return "Utilities"
            return "Others"

        df['Category'] = df['Description'].apply(categorize)

        # --- ANALYSIS ---
        st.success("Transactions successfully extracted from PDF!")
        st.dataframe(df.head())

        category_summary = df.groupby('Category')['Amount'].sum().reset_index()
        top_spending = category_summary.sort_values(by='Amount', ascending=False).head(3)
        wasteful_txns = df[df['Amount'] < 100][['Date', 'Receiver', 'Amount']]
        df['Month'] = df['Date'].dt.to_period('M')
        monthly_trend = df.groupby('Month')['Amount'].sum().reset_index()

        # --- DISPLAY ---
        st.subheader("Spending Summary")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Spent", f"₹{df['Amount'].sum():,.2f}")
            st.dataframe(category_summary)
        with col2:
            st.write("**Top Spending Categories**")
            st.dataframe(top_spending)

        st.subheader("Wasteful Transactions (< ₹100)")
        st.dataframe(wasteful_txns)

        st.subheader("Monthly Spending Trend")
        st.line_chart(monthly_trend.set_index('Month'))

        # --- BUILD PROMPT ---
        summary_data = {
            'total_spending_by_category': category_summary.to_dict(orient='records'),
            'top_spending_categories': top_spending.to_dict(orient='records'),
            'wasteful_spending': wasteful_txns.to_dict(orient='records'),
            'monthly_spending': monthly_trend.to_dict(orient='records')
        }

        prompt = f"""
You are a financial assistant. Analyze the following user's spending data and give personalized financial advice:

Total Spending by Category:
{summary_data['total_spending_by_category']}

Top Spending Categories:
{summary_data['top_spending_categories']}

Wasteful Spending (under ₹100):
{summary_data['wasteful_spending']}

Monthly Spending Trend:
{summary_data['monthly_spending']}

Your Task:
- Suggest a realistic monthly budget.
- Recommend ways to reduce wasteful spending.
- Highlight areas where spending can be optimized.
- Offer tips for better savings and financial discipline.
"""

        if st.button("Generate Financial Advice with Gemini"):
            with st.spinner("Generating advice..."):
                try:
                    response = model.generate_content(prompt)
                    st.success("Advice Generated!")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"Error: {e}")

    except Exception as e:
        st.error(f"Error processing the PDF file: {e}")
else:
    st.info("Please upload a UPI PDF to get started.")
