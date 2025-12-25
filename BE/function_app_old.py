import os
import json
import logging
import requests
import azure.functions as func
from llm_orchestrator import create_orchestrator

# -----------------------------------------------------------------------------
# App init
# -----------------------------------------------------------------------------
app = func.FunctionApp()

logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# HTTP-triggered function
# -----------------------------------------------------------------------------
@app.route(
    route="run_databricks_job",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def run_databricks_job(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("run_databricks_job triggered")

    # -------------------------------------------------------------------------
    # Parse request
    # -------------------------------------------------------------------------
    try:
        body = req.get_json()
    except ValueError:
        logging.warning("Invalid JSON body")
        return func.HttpResponse(
            "Invalid JSON body",
            status_code=400
        )

    sql_text = body.get("sql_text")
    if not sql_text:
        logging.warning("sql_text is missing")
        return func.HttpResponse(
            "sql_text is required",
            status_code=400
        )

    logging.info(f"Received SQL text: {sql_text}")

    # -------------------------------------------------------------------------
    # Read environment variables
    # -------------------------------------------------------------------------
    try:
        databricks_host = os.environ["DATABRICKS_HOST"].rstrip("/")
        databricks_token = os.environ["DATABRICKS_TOKEN"]
        job_id = int(os.environ["DATABRICKS_JOB_ID"])
    except KeyError as e:
        logging.error(f"Missing environment variable: {e}")
        return func.HttpResponse(
            f"Missing environment variable: {e}",
            status_code=500
        )

    # -------------------------------------------------------------------------
    # Call Databricks Jobs API
    # -------------------------------------------------------------------------
    url = f"{databricks_host}/api/2.1/jobs/run-now"

    headers = {
        "Authorization": f"Bearer {databricks_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "job_id": job_id,
        "notebook_params": {
            "sql_text": sql_text
        }
    }

    logging.info(f"Calling Databricks Jobs API: {url}")
    logging.info(f"Payload: {json.dumps(payload)}")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )
    except requests.RequestException as e:
        logging.exception("Error calling Databricks")
        return func.HttpResponse(
            f"Databricks request failed: {str(e)}",
            status_code=502
        )

    logging.info(f"Databricks response status: {response.status_code}")
    logging.info(f"Databricks response body: {response.text}")

    # -------------------------------------------------------------------------
    # Handle Databricks response
    # -------------------------------------------------------------------------
    if response.status_code >= 400:
        return func.HttpResponse(
            response.text,
            status_code=response.status_code,
            mimetype="application/json"
        )

    return func.HttpResponse(
        response.text,
        status_code=200,
        mimetype="application/json"
    )


# -----------------------------------------------------------------------------
# Tool Executor Function (used by LLM orchestrator)
# -----------------------------------------------------------------------------
def execute_databricks_job(sql_text: str) -> dict:
    """
    Execute Databricks Job with SQL query.
    Used as tool executor callback for LLM orchestrator.
    
    Args:
        sql_text: SQL query to execute
    
    Returns:
        Dictionary with execution result or error
    """
    try:
        databricks_host = os.environ["DATABRICKS_HOST"].rstrip("/")
        databricks_token = os.environ["DATABRICKS_TOKEN"]
        job_id = int(os.environ["DATABRICKS_JOB_ID"])
    except KeyError as e:
        logging.error(f"Missing environment variable: {e}")
        return {
            "status": "error",
            "error": f"Missing environment variable: {e}"
        }

    url = f"{databricks_host}/api/2.1/jobs/run-now"
    
    headers = {
        "Authorization": f"Bearer {databricks_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "job_id": job_id,
        "notebook_params": {
            "sql_text": sql_text
        }
    }
    
    logging.info(f"Tool executor: calling Databricks Jobs API")
    logging.info(f"SQL: {sql_text}")
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code >= 400:
            return {
                "status": "error",
                "error": f"Databricks returned status {response.status_code}",
                "details": response.text
            }
        
        result = response.json()
        logging.info(f"Databricks job started: run_id={result.get('run_id')}")
        
        return {
            "status": "success",
            "run_id": result.get("run_id"),
            "message": "Databricks job triggered successfully. Note: This is async execution - results are processed in Databricks."
        }
    
    except requests.RequestException as e:
        logging.exception("Error calling Databricks")
        return {
            "status": "error",
            "error": f"Databricks request failed: {str(e)}"
        }


# -----------------------------------------------------------------------------
# LLM-powered Chat Function (NEW - Orchestration Layer)
# -----------------------------------------------------------------------------
@app.route(
    route="chat",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def chat(req: func.HttpRequest) -> func.HttpResponse:
    """
    LLM-powered chat endpoint with tool calling.
    
    Request body:
    {
        "question": "What are the top rated movies from 2020?"
    }
    
    Response:
    {
        "status": "success",
        "final_answer": "Based on the data...",
        "tool_calls": [...],
        "iterations": 2
    }
    """
    logging.info("chat endpoint triggered")
    
    # -------------------------------------------------------------------------
    # Parse request
    # -------------------------------------------------------------------------
    try:
        body = req.get_json()
    except ValueError:
        logging.warning("Invalid JSON body")
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    question = body.get("question")
    if not question:
        logging.warning("question is missing")
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "question is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    logging.info(f"User question: {question}")
    
    # -------------------------------------------------------------------------
    # Verify Azure OpenAI configuration
    # -------------------------------------------------------------------------
    try:
        azure_openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        azure_openai_key = os.environ["AZURE_OPENAI_KEY"]
        azure_openai_deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    except KeyError as e:
        logging.error(f"Missing Azure OpenAI environment variable: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": f"Missing environment variable: {e}",
                "hint": "Configure AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT"
            }),
            status_code=500,
            mimetype="application/json"
        )
    
    # -------------------------------------------------------------------------
    # Create LLM orchestrator and process question
    # -------------------------------------------------------------------------
    try:
        orchestrator = create_orchestrator(
            tool_executor_callback=execute_databricks_job
        )
        
        result = orchestrator.process_question(question)
        
        logging.info(f"Orchestration result: {result.get('status')}")
        
        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.exception("Error in LLM orchestration")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )

