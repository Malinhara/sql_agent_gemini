import os
import json
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain.agents.agent_types import AgentType
from langchain.prompts import PromptTemplate
from typing import Optional
from langchain_community.utilities import SQLDatabase
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# FastAPI instance
app = FastAPI()

# CORS Middleware configuration from environment variable
origins_env = os.getenv("ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins='http://localhost:8501',  # Uses the origins list loaded from the environment variable
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Pydantic models for request validation
class QueryHistory(BaseModel):
    query: str
    database: str  # User specifies the database name here
    history: Optional[list[dict]] = []

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

# Config file path
CONFIG_FILE_PATH = "config/config.json"

# Global variable to hold database and GPT settings
DATABASE_DETAILS = {}
GPT_SETTINGS = {}

# Helper function to load config from a file
def load_config():
    global DATABASE_DETAILS, GPT_SETTINGS
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r") as file:
            config = json.load(file)
            DATABASE_DETAILS = config.get("database", {})
            GPT_SETTINGS = config.get("gpt", {})

# Load configuration on startup
load_config()

DB_CONNECTIONS = {}

# Helper function to create or fetch a DB connection
def create_db_connection(database: str):
    global DB_CONNECTIONS

    # Check if a connection already exists for the requested database
    if database in DB_CONNECTIONS:
        print(f"Using cached connection for database: {database}")
        return DB_CONNECTIONS[database]

    # Create a new connection if not cached
    try:
        connection_string = f"mssql+pyodbc://{DATABASE_DETAILS['user']}:{DATABASE_DETAILS['password']}@" \
                            f"{DATABASE_DETAILS['host']}:{DATABASE_DETAILS['port']}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
        
        # Create a new database connection
        db = SQLDatabase.from_uri(connection_string)
        
        # Cache the new connection
        DB_CONNECTIONS[database] = db
        print(f"Created new connection for database: {database}")
        return db

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")


# Helper function to setup the Google LLM (replacing OpenAI with Google LLM)
def setup_llm():
    try:
        # Ensure GPT settings are loaded
        if not GPT_SETTINGS:
            raise HTTPException(status_code=500, detail="GPT settings not configured.")
        
        api_key = GPT_SETTINGS['gpt_api_key']
        if not api_key:
            raise HTTPException(status_code=500, detail="Google API key is not set in configuration.")
        
        # Use Google LLM instead of OpenAI LLM
        return ChatGoogleGenerativeAI(
            model=GPT_SETTINGS['model'],
            temperature=GPT_SETTINGS['temperature'],
            api_key=api_key,
            streaming=False  # Disable streaming for faster responses
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error initializing Google LLM: {str(e)}")

# SQL prompt template

prompt_template = """
You are a SQL expert with access to the following tables: 

1. BusinessRule:
   - Id
   - RuleSetId
   - BanType
   - MultipleLOB
   - InteractionChannel
   - Tile
   - TargetPages
   - TilePosition
   - LOB
   - BUPID
   - UseCase
   - StartDate
   - EndDate
   - Days
   - Product
   - PackagePlan
   - Other
   - TilePriority
   - PrioritySource
   - Remarks
   - OfferID
   - ServiceID
   - AccountID
   - Language
   - Province
   - SuppressTile
   - IsDisabled
   - StartDateDt
   - EndDateDt
   - IsExpired

2. Tile:
   - TileID
   - TileName
   - TileCategory
   - Brand
   - DateModified
   - DateCreated
   - US_ID
   - Style
   - TileType
   - TileTactic
   - TileSubCategory
   - OfferType
   - ProductOffering
   - Origin
   - UserStory
   - JiraStoryId
   - RequestorName
   - Title_En
   - Title_Fr
   - LinkUrl_En
   - LinkUrl_Fr
   - Body_En
   - Body_Fr
   - ShowRatingsIcons
   - ModelCategory
   - LightboxActive
   - LB_Start
   - LB_End
   - Campaign_ID
   - SelfServeFlag
   - CallType
   - TargetGroup
   - Omniture_Start_Page
   - Omniture_End_Page
   - CreatedBy
   - IsLocal
   - CTA_Type
   - Protected_Tile_ODM_Guard
   - Modified_By
   - Modified_By_Person

For the following query request:

1. Provide a brief explanation of the query's purpose.
2. Generate a SQL query using these tables and schemas. Ensure that schema names are included in the SQL.
3. Provide an example of the expected results (e.g., the first 5 rows).


Current Query: {query}

Explanation:
SQL Query:
Example Data:
"""



# Endpoint to convert natural language query to SQL and execute it
@app.post("/convert-nl-to-sql-and-execute-with-validation/")
async def convert_nl_to_sql_and_execute_with_validation(query_data: QueryHistory):
    try:
        # Step 1: Create DB connection with the specified database
        db = create_db_connection(query_data.database)
        
        # Step 2: Setup GPT model (Google LLM)
        llm = setup_llm()
        
        # Step 3: Generate SQL query using LangChain agent
        prompt = PromptTemplate(input_variables=["query"], template=prompt_template)
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)

        # Initialize the agent executor
        try:
            agent_executor = create_sql_agent(
                llm=llm,
                toolkit=toolkit,
                agent_type=AgentType.OPENAI_FUNCTIONS,
                top_k=2
            )
        except Exception as init_error:
            raise HTTPException(status_code=500, detail=f"Failed to initialize agent: {str(init_error)}")

        # Format the prompt with history and the current query
        formatted_prompt = prompt.format(query=query_data.query)

        # Generate and execute SQL query
        try:
            # Get the response from the agent
            response = agent_executor.invoke(formatted_prompt)
            
            # Extract the response text
            response_text = response.get("output", "")
            
            # Extract SQL query using regex
            sql_match = re.search(r"SQL Query:.*?```sql\s*(.*?)\s*```", response_text, re.DOTALL)
            if not sql_match:
                # Try alternative pattern without ```sql
                sql_match = re.search(r"SQL Query:\s*(.*?)(?=Example Data:|$)", response_text, re.DOTALL)
            
            if not sql_match:
                raise HTTPException(status_code=500, detail="Could not extract SQL query from response")
            
            # Clean up the extracted SQL query
            sql_query = sql_match.group(1).strip()
            print(f"Extracted SQL Query: {sql_query}")
            
            # Execute the SQL query
            result = db.run(sql_query)
            print(f"Query Execution Result: {result}")
            
            # Combine all results into a single object
            combined_response = {
                "response": response_text,
                "sql_query": sql_query,
                "execution_result": result
            }

            # Return the combined response
            return combined_response
            
        except Exception as execution_error:
            raise HTTPException(status_code=500, detail=f"Execution error: {str(execution_error)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing the request: {str(e)}")


# Endpoint to save database and GPT configuration in one request
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
    
    
