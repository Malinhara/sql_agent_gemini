from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_community.utilities.sql_database import SQLDatabase
from langchain.chains import create_sql_query_chain
from sqlalchemy import create_engine, text
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from operator import itemgetter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
import os
import json

# Initialize FastAPI app
app = FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Allow specific origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# Models for request and response
class QueryHistory(BaseModel):
    query: str
    database: str  # User specifies the database name here

class DatabaseDetails(BaseModel):
    host: str
    port: int
    user: str
    password: str

class GPTSettings(BaseModel):
    gpt_api_key: str
    temperature: float
    model: str
    
class Settings(BaseModel):
    database: DatabaseDetails
    gpt: GPTSettings
    
    


class QueryResponse(BaseModel):
    answer: str

# Configuration
CONFIG_FILE_PATH = "config/config.json"

# Global variables for configuration
DATABASE_DETAILS = {}
GPT_SETTINGS = {}
DB_CONNECTIONS = {}

# Helper function to load configuration
def load_config():
    global DATABASE_DETAILS, GPT_SETTINGS
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r") as file:
            config = json.load(file)
            DATABASE_DETAILS = config.get("database", {})
            GPT_SETTINGS = config.get("gpt", {})

# Load configuration on startup
load_config()

# Database connection function
def get_database(database: str):
    if database not in DB_CONNECTIONS:
        try:
            # Use the SQL Server URI for connection
            connection_string = f"mssql+pyodbc://{DATABASE_DETAILS['user']}:{DATABASE_DETAILS['password']}@{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
            
            # Create and store connection in the global dictionary
            DB_CONNECTIONS[database] = SQLDatabase.from_uri(connection_string)
        
        except SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
    
    return DB_CONNECTIONS[database]


# GPT Initialization
api_key = GPT_SETTINGS.get("gpt_api_key", "")
llm = ChatGoogleGenerativeAI(
    model=GPT_SETTINGS.get("model", "chat-bison"),
    temperature=GPT_SETTINGS.get("temperature", 0),
    api_key=api_key,
    streaming=False,
)

# Answer Rephrasing Pipeline
answer_prompt = PromptTemplate.from_template(
    """Given the following user question, corresponding SQL query, and SQL result, answer the user question.

    Question: {question}
    SQL Query: {query}
    SQL Result: {result}
    Answer: """
)
rephrase_answer = answer_prompt | llm | StrOutputParser()

@app.post("/ask", response_model=QueryResponse)
def ask_question(query_data: QueryHistory):
    """Handle a natural language query against the specified database."""
    try:
        # Connect to the specified database
        db = get_database(query_data.database)
        print(db)

        # Initialize query generator and executor
        generate_query = create_sql_query_chain(llm, db)
        execute_query = QuerySQLDataBaseTool(db=db)

        # Generate SQL query from the natural language question
        query = generate_query.invoke({"question": query_data.query})

        # Execute the generated SQL query
        result = execute_query.invoke(query)

        # Generate a natural language answer
        answer = rephrase_answer.invoke({
            "question": query_data.query,
            "query": query,
            "result": result
        })

        return QueryResponse(
            answer=answer
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")



@app.post("/save-config-details")
async def save_config_details(settings: Settings):
    try:
        global DATABASE_DETAILS, GPT_SETTINGS
        DATABASE_DETAILS = settings.database.dict()
        GPT_SETTINGS = settings.gpt.dict()

        # Ensure the config directory exists
        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)

        # Save both database and GPT details to the config file
        with open(CONFIG_FILE_PATH, "w") as file:
            json.dump({"database": DATABASE_DETAILS, "gpt": GPT_SETTINGS}, file, indent=4)

        return {"message": "Database and GPT details saved successfully!"}
    except Exception as e:
        print("Error occurred while saving config details:", str(e))
        raise HTTPException(status_code=500, detail=f"Error saving config details: {str(e)}")


@app.get("/list-databases")
async def list_databases():
    try:
        # Ensure DATABASE_DETAILS are properly loaded
        if not DATABASE_DETAILS:
            raise HTTPException(status_code=500, detail="Database details not configured.")

        # Check if an existing connection is available
        connection_key = f"{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}"
        if connection_key not in DB_CONNECTIONS:
            # Create a connection string for MSSQL using pyodbc
            connection_string = (
                f"mssql+pyodbc://{DATABASE_DETAILS['user']}:{DATABASE_DETAILS['password']}@"
                f"{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}/master?driver=ODBC+Driver+17+for+SQL+Server"
            )
            DB_CONNECTIONS[connection_key] = create_engine(connection_string)

        # Reuse the existing connection or newly created connection
        engine = DB_CONNECTIONS[connection_key]

        # Connect to the database and query the list of user databases
        with engine.connect() as conn:
            query = """
                SELECT name 
                FROM sys.databases
                WHERE state_desc = 'ONLINE' 
                  AND database_id > 4 -- Exclude system databases like master, tempdb, etc.
            """
            result = conn.execute(text(query))
            databases = [row[0] for row in result]  # Extracting the database names

        return {"databases": databases}
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching databases: {str(e)}")
    
# this fun helps to list database, list tables and view table data   
def get_engine(database: str):
    connection_key = f"{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}/{database}"
    if connection_key not in DB_CONNECTIONS:
        connection_string = (
            f"mssql+pyodbc://{DATABASE_DETAILS['user']}:{DATABASE_DETAILS['password']}@"
            f"{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
        )
        DB_CONNECTIONS[connection_key] = create_engine(connection_string)
    return DB_CONNECTIONS[connection_key]



@app.get("/list-tables/")
async def list_tables(database: str):
    try:
        if not database:
            raise HTTPException(status_code=400, detail="Database name is required.")

        engine = get_engine(database)

        with engine.connect() as conn:
            query = """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE';
            """
            result = conn.execute(text(query))
            tables = [{"schema": row[0], "table_name": row[1]} for row in result]

        return {"tables": tables}

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tables: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing the request: {str(e)}")
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
