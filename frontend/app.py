"""A small Streamlit page where you can ask the policy chatbot a question."""

import streamlit as st

st.set_page_config(page_title="Nordljus policy assistant", layout="wide")
st.title("Nordljus policy assistant")
st.caption("Ask about the policies of Nordljus Consulting AB, a made up company for this project.")

with st.form("ask"):
    question = st.text_area("Your question", placeholder="Ask about a Nordljus policy...")
    asked = st.form_submit_button("Ask")

if asked and not question.strip():
    st.warning("Write a question first.")
