import os
import streamlit as st  # type: ignore
import requests  # To make HTTP requests to FastAPI

# URL of the FastAPI backend
FASTAPI_URL = "http://127.0.0.1:8000"  # Change if your FastAPI server runs elsewhere


# Streamlit UI for MySQL Connection Setup
def show_admin_panel():
    st.title("Connections Setup")

    # Create two columns for layout: one for Database and one for GPT Settings
    col1, col2 = st.columns(2)

    with col1:
        # Database Details
        st.subheader("Enter Database Details")
        host = st.text_input("Host", "localhost")
        port = st.text_input("Port", 3306)
        user = st.text_input("Username", "root")
        password = st.text_input("Password", type="password")
        # database = st.text_input("Database Name (Add any db in your server - this part only to verify the connection)", "example_db")
    
    with col2:
        # GPT Settings
        st.subheader("Enter GPT Settings")
        gpt_api_key = st.text_input("GPT API Key", type="password")
        temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.04)
        model_options = ["gpt-3.5-turbo", "gpt-4", "gpt-4o-mini","gemini-1.5-flash"]
        model = st.selectbox("Select GPT Model", model_options)

    # Check if all fields are filled
    all_fields_filled = all([host, port, user, password, gpt_api_key])

    # Save database and GPT details together
    if all_fields_filled and st.button("Save Database and GPT Details"):
        payload = {
            "database": {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
            },
            "gpt": {
                "gpt_api_key": gpt_api_key,
                "temperature": temperature,
                "model": model
            }
        }

        # Send data to FastAPI backend to save both database and GPT details
        response = requests.post(f"{FASTAPI_URL}/save-config-details", json=payload)

        if response.status_code == 200:
            st.success("Database and GPT details saved successfully!")
        else:
            st.error("Failed to save database and GPT details.")
    elif not all_fields_filled:
        # Show a message if not all fields are filled
        st.warning("Please fill out all fields before submitting.")
