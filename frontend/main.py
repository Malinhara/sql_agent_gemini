import streamlit as st  # type: ignore
import requests
from admin import show_admin_panel  # Ensure this module is implemented

# FastAPI URL
FASTAPI_URL = "http://127.0.0.1:8000"

# Initialize session state variables
if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_db" not in st.session_state:
    st.session_state.selected_db = None

if "selected_table" not in st.session_state:
    st.session_state.selected_table = None

if "show_table" not in st.session_state:
    st.session_state.show_table = False

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "databases" not in st.session_state:
    st.session_state.databases = []



# Sidebar for navigation
st.sidebar.title("Navigation")
app_mode = st.sidebar.selectbox("Choose a page", ["Home - Chatbot", "Admin Panel"])

# Sidebar for database selection
st.sidebar.subheader("Select Database")

# Refresh button for databases and tables

if st.sidebar.button("Refresh Data"):
    try:
        # Fetch databases
        response = requests.get(f"{FASTAPI_URL}/list-databases")
        if response.status_code == 200:
            st.session_state.databases = response.json().get("databases", [])
            st.session_state.tables = []  # Clear cached tables when databases refresh
            st.session_state.selected_db = None  # Reset selected database
            st.session_state.selected_table = None  # Reset selected table
            st.sidebar.success("Databases refreshed successfully.")
        else:
            st.sidebar.error("Failed to fetch databases.")
            # Clear all session state data if refresh fails
            st.session_state.databases = []
            st.session_state.tables = []
            st.session_state.selected_db = None
            st.session_state.selected_table = None
    except Exception as e:
        st.sidebar.error(f"Error fetching databases: {e}")
        # Clear all session state data if there is an error
        st.session_state.databases = []
        st.session_state.tables = []
        st.session_state.selected_db = None
        st.session_state.selected_table = None

# Sidebar for database selection - Only show if databases exist
if st.session_state.databases:
    selected_database = st.sidebar.selectbox(
        "Choose Database", st.session_state.databases,
        index=st.session_state.databases.index(st.session_state.selected_db) if st.session_state.selected_db in st.session_state.databases else 0
    )
    st.session_state.selected_db = selected_database

    # Fetch tables for the selected database when a new database is selected
    if st.session_state.selected_db:
        if not st.session_state.tables or st.session_state.selected_db != st.session_state.cached_db:
            try:
                response = requests.get(
                    f"{FASTAPI_URL}/list-tables/",
                    params={"database": st.session_state.selected_db}
                )
                if response.status_code == 200:
                    st.session_state.tables = response.json().get("tables", [])
                    st.session_state.cached_db = st.session_state.selected_db  # Cache the database
                else:
                    st.sidebar.error("Failed to fetch tables.")
                    # Clear session state if tables fail to load
                    st.session_state.tables = []
                    st.session_state.selected_table = None
            except Exception as e:
                st.sidebar.error(f"Error fetching tables: {e}")
                # Clear session state if there's an error fetching tables
                st.session_state.tables = []
                st.session_state.selected_table = None

    # Show table selection if tables are fetched
    if st.session_state.tables:
        selected_table = st.sidebar.selectbox(
            "Selected Db Tables", st.session_state.tables,
            index=st.session_state.tables.index(st.session_state.selected_table) if st.session_state.selected_table in st.session_state.tables else 0
        )
        st.session_state.selected_table = selected_table
    else:
        st.sidebar.warning("No tables available in the selected database.")
else:
    st.sidebar.warning("No databases available. Please refresh.")
    # If no databases, clear any selected table and reset states
    st.session_state.selected_db = None
    st.session_state.selected_table = None

# Don't display the database and table selection if no valid data is present
if not st.session_state.databases or not st.session_state.selected_db or not st.session_state.tables:
    # Don't show tables or data when no valid data is fetched
    st.session_state.selected_db = None
    st.session_state.selected_table = None



# Home - Chatbot Page
MAX_CHAT_HISTORY = 20

# Display chat messages from trimmed history
if app_mode == "Home - Chatbot":
    st.title("Natural Language to SQL")

    # Retain the latest messages based on the MAX_CHAT_HISTORY constant
    trimmed_history = st.session_state.messages[-MAX_CHAT_HISTORY:]  # Limit history size
    for message in trimmed_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    user_input = st.chat_input("Type your question here...")

    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Display user message in the chat
        with st.chat_message("user"):
            st.markdown(user_input)

        # Send request to FastAPI and display "thinking..." response
        with st.chat_message("assistant"):
            # Ensure message_placeholder is created only once and persists until the new response is available
            message_placeholder = st.empty()  # Placeholder for assistant's response

            # Display a loading message while waiting for the response
            message_placeholder.markdown("**Assistant is thinking...**")

            # Initialize bot response
            bot_response = ""  # Initialize bot response

            try:
                # Prepare payload for FastAPI
                payload = {"query": user_input, "database": st.session_state.selected_db}
                response = requests.post(f"{FASTAPI_URL}/convert-nl-to-sql-and-execute-with-validation/", json=payload)

                if response.status_code == 200:
                    response_data = response.json()

                    # Extract the bot response, SQL query, and execution result from the backend
                    bot_response = response_data.get("response", "Sorry, I couldn't understand.")
                    sql_query = response_data.get("sql_query", "No SQL query was generated.")
                    execution_result = response_data.get("execution_result", "No result returned from the database.")

                    # Format the response for markdown display
                    formatted_response = f"""
                    **Bot Response:**
                    {bot_response}

                    **Generated SQL Query:**
                    ```sql
                    {sql_query}
                    ```

                    **Execution Result:**
                    ```json
                    {execution_result}
                    ```
                    """
                    # Show formatted response in the chat
                    message_placeholder.markdown(formatted_response)

                    # Save assistant's response and trim chat history
                    st.session_state.messages.append({"role": "assistant", "content": formatted_response})

                    # Trim the chat history to maintain the latest messages up to the MAX_CHAT_HISTORY limit
                    st.session_state.messages = st.session_state.messages[-MAX_CHAT_HISTORY:]
                else:
                    # Handle non-200 HTTP responses
                    error_message = f"Error: {response.status_code} - {response.reason}"
                    message_placeholder.markdown(error_message)

            except Exception as e:
                bot_response = f"Error: {e}"
                st.error(bot_response)

            # Save assistant's response and trim chat history
            st.session_state.messages.append({"role": "assistant", "content": bot_response})

            # Trim the chat history to maintain the latest messages up to the MAX_CHAT_HISTORY limit
            st.session_state.messages = st.session_state.messages[-MAX_CHAT_HISTORY:]


# Admin Panel
elif app_mode == "Admin Panel":
    st.title("Admin Panel")
    show_admin_panel()
