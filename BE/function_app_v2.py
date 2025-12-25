import os
import json
import logging
import asyncio
import azure.functions as func
from llm_orchestrator import create_orchestrator
from cosmos_storage import create_storage
from databricks_client import create_client

# -----------------------------------------------------------------------------
# App init
# -----------------------------------------------------------------------------
app = func.FunctionApp()

logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Background Job Processor
# -----------------------------------------------------------------------------
def process_conversation_async(conversation_id: str):
    """
    Background processing of conversation with LLM and Databricks.
    This runs after initial response is sent to user.
    
    Args:
        conversation_id: ID of conversation to process
    """
    try:
        storage = create_storage()
        databricks = create_client()
        
        # Get conversation
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            logging.error(f"Conversation not found: {conversation_id}")
            return
        
        question = conversation["question"]
        logging.info(f"Processing conversation {conversation_id}: {question}")
        
        # Tool executor callback
        def execute_tool(sql_query: str) -> dict:
            """Execute Spark SQL via Databricks."""
            logging.info(f"Executing SQL: {sql_query[:100]}...")
            
            # Trigger job
            result = databricks.trigger_job(sql_query)
            
            if result["status"] == "error":
                return result
            
            run_id = result["run_id"]
            
            # Register job in conversation
            storage.add_databricks_job(conversation_id, run_id, sql_query)
            
            # Wait for completion (async polling)
            logging.info(f"Waiting for Databricks job {run_id} to complete...")
            final_status = databricks.wait_for_completion(run_id, max_wait_seconds=120)
            
            # Update job status
            if final_status.get("is_successful"):
                storage.update_databricks_job_status(
                    conversation_id,
                    run_id,
                    "completed",
                    final_status
                )
                
                # Try to get output
                output = databricks.get_run_output(run_id)
                
                return {
                    "status": "success",
                    "run_id": run_id,
                    "result": output or final_status,
                    "message": f"Query executed successfully in {final_status.get('raw_response', {}).get('execution_duration', 0)}ms"
                }
            else:
                storage.update_databricks_job_status(
                    conversation_id,
                    run_id,
                    "failed",
                    final_status
                )
                return {
                    "status": "error",
                    "run_id": run_id,
                    "error": final_status.get("state_message", "Job failed")
                }
        
        # Create orchestrator and process
        orchestrator = create_orchestrator(tool_executor_callback=execute_tool)
        result = orchestrator.process_question(question)
        
        # Store result
        if result["status"] == "success":
            storage.set_final_answer(conversation_id, result["final_answer"])
            logging.info(f"Conversation {conversation_id} completed successfully")
        else:
            storage.set_error(conversation_id, result.get("error", "Unknown error"))
            logging.error(f"Conversation {conversation_id} failed: {result.get('error')}")
    
    except Exception as e:
        logging.exception(f"Error processing conversation {conversation_id}")
        try:
            storage = create_storage()
            storage.set_error(conversation_id, str(e))
        except:
            pass


# -----------------------------------------------------------------------------
# NEW ENDPOINTS - Production-Ready Async Architecture
# -----------------------------------------------------------------------------

@app.route(
    route="chat/start",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def chat_start(req: func.HttpRequest) -> func.HttpResponse:
    """
    Start new conversation (async).
    
    Request:
    {
        "question": "What are the top movies?",
        "user_id": "optional_user_id"
    }
    
    Response:
    {
        "conversation_id": "uuid",
        "status": "processing",
        "message": "Conversation started, use /chat/{id}/status to poll"
    }
    """
    logging.info("chat/start endpoint triggered")
    
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    question = body.get("question")
    user_id = body.get("user_id")
    
    if not question:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "question is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        # Create conversation in Cosmos DB
        storage = create_storage()
        conversation = storage.create_conversation(question, user_id)
        conversation_id = conversation["id"]
        
        logging.info(f"Created conversation: {conversation_id}")
        
        # Start background processing
        # Note: Azure Functions doesn't support true async background tasks
        # In production, use Azure Durable Functions or Queue-based processing
        # For now, we'll process synchronously but return immediately with polling endpoint
        
        # TODO: Replace with Azure Durable Functions or Queue trigger
        import threading
        thread = threading.Thread(
            target=process_conversation_async,
            args=(conversation_id,)
        )
        thread.daemon = True
        thread.start()
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "conversation_id": conversation_id,
                "processing_status": "started",
                "message": f"Conversation started. Poll /chat/{conversation_id}/status for updates.",
                "poll_url": f"/api/chat/{conversation_id}/status"
            }, indent=2),
            status_code=202,  # 202 Accepted
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.exception("Error starting conversation")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


@app.route(
    route="chat/{conversation_id}/status",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def chat_status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get conversation status (for polling).
    
    Response:
    {
        "conversation_id": "uuid",
        "status": "processing|completed|error",
        "question": "User's question",
        "final_answer": "LLM answer" (if completed),
        "databricks_jobs": [...],
        "progress": {
            "current_step": "Waiting for Spark execution...",
            "percentage": 60
        }
    }
    """
    conversation_id = req.route_params.get("conversation_id")
    
    if not conversation_id:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "conversation_id is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        storage = create_storage()
        conversation = storage.get_conversation(conversation_id)
        
        if not conversation:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "error": f"Conversation not found: {conversation_id}"
                }),
                status_code=404,
                mimetype="application/json"
            )
        
        # Calculate progress
        progress = _calculate_progress(conversation)
        
        response = {
            "conversation_id": conversation_id,
            "status": conversation["status"],
            "question": conversation["question"],
            "final_answer": conversation.get("final_answer"),
            "error": conversation.get("error"),
            "databricks_jobs": conversation.get("databricks_jobs", []),
            "progress": progress,
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"]
        }
        
        return func.HttpResponse(
            json.dumps(response, indent=2),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.exception("Error getting conversation status")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


@app.route(
    route="chat/{conversation_id}/messages",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def chat_messages(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get full conversation history.
    
    Response:
    {
        "conversation_id": "uuid",
        "messages": [
            {"role": "user", "content": "...", "timestamp": "..."},
            {"role": "assistant", "content": "...", "timestamp": "..."}
        ]
    }
    """
    conversation_id = req.route_params.get("conversation_id")
    
    if not conversation_id:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "conversation_id is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        storage = create_storage()
        conversation = storage.get_conversation(conversation_id)
        
        if not conversation:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "error": f"Conversation not found: {conversation_id}"
                }),
                status_code=404,
                mimetype="application/json"
            )
        
        response = {
            "conversation_id": conversation_id,
            "messages": conversation.get("messages", [])
        }
        
        return func.HttpResponse(
            json.dumps(response, indent=2),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.exception("Error getting messages")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _calculate_progress(conversation: dict) -> dict:
    """Calculate conversation progress for UI."""
    status = conversation["status"]
    jobs = conversation.get("databricks_jobs", [])
    
    if status == "completed":
        return {
            "current_step": "Completed",
            "percentage": 100
        }
    elif status == "error":
        return {
            "current_step": "Error occurred",
            "percentage": 0
        }
    
    # Processing
    if not jobs:
        return {
            "current_step": "Analyzing question with LLM...",
            "percentage": 20
        }
    
    # Check job statuses
    running_jobs = [j for j in jobs if j["status"] in ["pending", "running"]]
    completed_jobs = [j for j in jobs if j["status"] == "completed"]
    
    if running_jobs:
        return {
            "current_step": f"Executing Spark SQL ({len(completed_jobs)}/{len(jobs)} queries completed)...",
            "percentage": 40 + (len(completed_jobs) / len(jobs) * 40)
        }
    
    if completed_jobs:
        return {
            "current_step": "Processing results with LLM...",
            "percentage": 85
        }
    
    return {
        "current_step": "Processing...",
        "percentage": 30
    }


# -----------------------------------------------------------------------------
# LEGACY ENDPOINTS (for backward compatibility)
# -----------------------------------------------------------------------------

@app.route(
    route="run_databricks_job",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def run_databricks_job(req: func.HttpRequest) -> func.HttpResponse:
    """
    Legacy endpoint: Direct SQL execution (synchronous).
    Kept for backward compatibility.
    """
    logging.info("run_databricks_job triggered (legacy endpoint)")
    
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            "Invalid JSON body",
            status_code=400
        )
    
    sql_text = body.get("sql_text")
    if not sql_text:
        return func.HttpResponse(
            "sql_text is required",
            status_code=400
        )
    
    try:
        databricks = create_client()
        result = databricks.trigger_job(sql_text)
        
        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.exception("Error in legacy endpoint")
        return func.HttpResponse(
            json.dumps({"status": "error", "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
