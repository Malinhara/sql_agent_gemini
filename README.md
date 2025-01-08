

1. Clone the repository:( should clone New Barch code for Mssql , main brach code is suitable Mysql 

    TYPE ON CMD ==> git clone https://github.com/Malinhara/sql_agent_gemini.git

    cd yourrepository (go to inside)


2. Create a virtual environment (if it does not already exist):

    python -m venv venv

extra: My Python version is 3.12.4

3. Activate the virtual environment:
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. Install the required dependencies:

    type on terminal -> pip install -r requirements.txt

4. go inside frontend folder:

   type on terminal -> streamlit run main.py

5. go inside backend folder:

   
   type on terminal -> uvicorn main:app --reload ( main means gemeini base ai assistant)<br>


6. after run the project put your GPT and  db details in admin pannel

7. after success get the home panel and type the query

Once done, you can start working with the project.
