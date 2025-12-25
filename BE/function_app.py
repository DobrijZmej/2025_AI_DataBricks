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
        def execute_tool(tool_args: dict) -> dict:
            """Execute Spark SQL via Databricks."""
            sql_query = tool_args.get("sql_query")
            reasoning = tool_args.get("reasoning", "Executing query...")
            
            logging.info(f"LLM reasoning: {reasoning}")
            logging.info(f"Executing SQL: {sql_query[:100]}...")
            
            # Trigger job
            result = databricks.trigger_job(sql_query)
            
            if result["status"] == "error":
                return result
            
            run_id = result["run_id"]
            
            # Register job in conversation with reasoning
            storage.add_databricks_job(conversation_id, run_id, sql_query, reasoning)
            
            # Don't wait for completion - let polling endpoint check status
            # This prevents blocking for 2+ minutes on cold start
            logging.info(f"Databricks job {run_id} started, will be checked via polling")
            
            return {
                "status": "success",
                "run_id": run_id,
                "message": "Query submitted to Databricks. Processing..."
            }
        
        # Create orchestrator and process
        orchestrator = create_orchestrator(tool_executor_callback=execute_tool)
        result = orchestrator.process_question(question)
        
        # Store result
        if result["status"] == "success":
            # Check if there are pending Databricks jobs
            conversation = storage.get_conversation(conversation_id)
            jobs = conversation.get("databricks_jobs", [])
            
            if jobs:
                # Jobs were triggered - keep conversation in processing state
                # The polling endpoint will check job status and complete conversation when ready
                logging.info(f"Conversation {conversation_id} has {len(jobs)} jobs, keeping in processing state")
                # Don't set final_answer yet - wait for job completion
            else:
                # No jobs triggered - LLM answered directly
                storage.add_message(
                    conversation_id,
                    role="assistant",
                    content=result["final_answer"],
                    tool_calls=result.get("tool_calls")
                )
                storage.set_final_answer(conversation_id, result["final_answer"])
                logging.info(f"Conversation {conversation_id} completed without jobs")
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
    route="chat/history",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def chat_history(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get conversation history for device.
    
    Query params:
        device_id: Device identifier (required)
        limit: Max conversations to return (default: 50)
    
    Response:
    {
        "conversations": [
            {
                "id": "uuid",
                "question": "First message...",
                "status": "completed",
                "created_at": "2025-12-23T19:00:00Z",
                "updated_at": "2025-12-23T19:01:00Z"
            },
            ...
        ]
    }
    """
    logging.info("chat/history endpoint triggered")
    
    device_id = req.params.get("device_id")
    limit = int(req.params.get("limit", 50))
    
    if not device_id:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "device_id is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        storage = create_storage()
        conversations = storage.get_conversations_by_device(device_id, limit)
        
        return func.HttpResponse(
            json.dumps({"conversations": conversations}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.exception(f"Error getting conversation history: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


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
        "device_id": "browser_device_uuid",
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
    device_id = body.get("device_id")
    user_id = body.get("user_id")
    
    if not question:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "question is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    if not device_id:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "device_id is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        # Create conversation in Cosmos DB
        storage = create_storage()
        conversation = storage.create_conversation(question, device_id, user_id)
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
        databricks = create_client()
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
        
        # Check for 30 minute timeout
        _check_conversation_timeout(conversation, storage, conversation_id)
        
        # Update Databricks job statuses if still processing
        if conversation["status"] == "processing":
            _update_databricks_job_statuses(conversation, databricks, storage, conversation_id)
        
        # Refresh conversation after updates
        conversation = storage.get_conversation(conversation_id)
        
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

def _generate_delay_message(
    question: str,
    reasoning: str,
    minutes_elapsed: int
) -> str:
    """
    Generate delay status message using LLM in same language as question.
    
    Args:
        question: User's original question
        reasoning: LLM's reasoning for current operation
        minutes_elapsed: How many minutes job has been running
    
    Returns:
        Status message in same language as question
    """
    try:
        from llm_orchestrator import create_orchestrator
        from openai import AzureOpenAI
        import os
        
        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version="2024-08-01-preview"
        )
        
        prompt = f"""User asked: "{question}"

Current operation: {reasoning}

Context: This operation has been running for {minutes_elapsed} minutes, which is longer than usual. This typically happens when:
- Databricks cluster is starting up (cold start)
- Query is complex and requires more processing time
- Large dataset processing

Generate a brief, friendly status message (2-3 sentences max) in the SAME LANGUAGE as the user's question. Explain that it's taking longer than expected and why, but assure them to please wait. Be concise and natural."""
        
        response = client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates status messages in the user's language."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        message = response.choices[0].message.content.strip()
        logging.info(f"Generated delay message: {message}")
        return f"{reasoning}\n\n{message}"
        
    except Exception as e:
        logging.exception(f"Error generating delay message: {e}")
        # Fallback to English
        return f"{reasoning}\n\nThis is taking longer than usual ({minutes_elapsed} min). The Databricks cluster may be starting up or the query is complex. Please wait..."


def _check_conversation_timeout(
    conversation: dict,
    storage,
    conversation_id: str,
    max_minutes: int = 30
):
    """Check if conversation exceeded 30 minute timeout."""
    if conversation["status"] != "processing":
        return
    
    from datetime import datetime, timezone, timedelta
    
    created_at = datetime.fromisoformat(conversation["created_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    elapsed = now - created_at
    
    if elapsed > timedelta(minutes=max_minutes):
        # Generate timeout message using LLM in user's language
        question = conversation.get("question", "")
        try:
            from openai import AzureOpenAI
            
            client = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=os.environ["AZURE_OPENAI_KEY"],
                api_version="2024-08-01-preview"
            )
            
            prompt = f"""User asked: "{question}"

Context: The request has been running for {max_minutes} minutes without completing. This is a timeout situation.

Generate a brief, apologetic message (2-3 sentences) in the SAME LANGUAGE as the user's question explaining that:
- We couldn't get a response after {max_minutes} minutes
- The Databricks cluster may need more time or the query is too complex
- They can try again with a simpler question

Be friendly and concise."""
            
            response = client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates error messages in the user's language."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            error_msg = response.choices[0].message.content.strip()
            
        except Exception as e:
            logging.exception(f"Error generating timeout message: {e}")
            # Fallback to English
            error_msg = f"Request timeout: No response from Databricks after {max_minutes} minutes. The cluster may need more time to start or the query is too complex."
        
        logging.warning(f"Conversation {conversation_id} timed out after {elapsed}")
        storage.set_error(conversation_id, error_msg)


def _update_databricks_job_statuses(
    conversation: dict,
    databricks,
    storage,
    conversation_id: str
):
    """Update statuses of pending/running Databricks jobs."""
    jobs = conversation.get("databricks_jobs", [])
    any_updated = False
    
    for job in jobs:
        if job["status"] in ["pending", "running"]:
            run_id = job["run_id"]
            
            # Check current status in Databricks
            status_result = databricks.get_run_status(run_id)
            
            if status_result.get("status") == "error":
                # Error getting status - mark as failed
                storage.update_databricks_job_status(
                    conversation_id,
                    run_id,
                    "failed",
                    status_result
                )
                any_updated = True
            elif status_result.get("is_completed"):
                if status_result.get("is_successful"):
                    # Job completed successfully
                    storage.update_databricks_job_status(
                        conversation_id,
                        run_id,
                        "completed",
                        status_result
                    )
                    any_updated = True
                    logging.info(f"Job {run_id} completed successfully")
                else:
                    # Job failed
                    storage.update_databricks_job_status(
                        conversation_id,
                        run_id,
                        "failed",
                        status_result
                    )
                    any_updated = True
            else:
                # Still running - update status
                storage.update_databricks_job_status(
                    conversation_id,
                    run_id,
                    "running",
                    status_result
                )
                any_updated = True
    
    # If any jobs were updated, check if all are completed
    if any_updated:
        conversation = storage.get_conversation(conversation_id)
        jobs = conversation.get("databricks_jobs", [])
        
        all_completed = all(j["status"] in ["completed", "failed"] for j in jobs)
        any_failed = any(j["status"] == "failed" for j in jobs)
        
        if all_completed:
            if any_failed:
                # At least one job failed
                error_msg = "Some queries failed to execute in Databricks"
                storage.set_error(conversation_id, error_msg)
                logging.warning(f"Conversation {conversation_id} completed with failures")
            else:
                # All jobs succeeded - generate final answer using LLM with results
                _finalize_conversation_with_results(conversation_id, conversation, storage, databricks)


def _finalize_conversation_with_results(
    conversation_id: str,
    conversation: dict,
    storage,
    databricks
):
    """Generate final answer using LLM with Databricks results."""
    try:
        from llm_orchestrator import create_orchestrator
        from openai import AzureOpenAI
        
        question = conversation["question"]
        jobs = conversation.get("databricks_jobs", [])
        
        # Collect all job results
        results_text = []
        for job in jobs:
            sql = job.get("sql_query", "")
            run_id = job["run_id"]
            
            # Get job output
            output = databricks.get_run_output(run_id)
            
            # Temporary debug logging
            logging.info(f"[DEBUG] get_run_output returned for run {run_id}: type={type(output)}, value={'None' if output is None else str(output)[:200]}")
            
            if output:
                results_text.append(f"Query: {sql}\\n\\nResults: {json.dumps(output, ensure_ascii=False, indent=2)}")
            else:
                results_text.append(f"Query: {sql}\\n\\nResults: [No output available]")
        
        combined_results = "\\n\\n---\\n\\n".join(results_text)
        
        # Generate final answer using LLM
        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version="2024-08-01-preview"
        )
        
        prompt = f"""
        Original question: "{question}"

Query results from database:
{combined_results}

Based on these results, provide a clear, natural answer to the user's question in the SAME LANGUAGE as the question. Format the answer in a user-friendly way.\"\"\"
        """
        response = client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=[
                {"role": "system", "content": "You are a helpful assistant that interprets database results and answers user questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        final_answer = response.choices[0].message.content.strip()
        
        # Save final answer
        storage.add_message(
            conversation_id,
            role="assistant",
            content=final_answer
        )
        storage.set_final_answer(conversation_id, final_answer)
        logging.info(f"Conversation {conversation_id} finalized with LLM-generated answer")
        
    except Exception as e:
        logging.exception(f"Error finalizing conversation {conversation_id}")
        storage.set_error(conversation_id, f"Error generating final answer: {str(e)}")


def _calculate_progress(conversation: dict) -> dict:
    """Calculate conversation progress for UI."""
    from datetime import datetime, timezone, timedelta
    
    status = conversation["status"]
    jobs = conversation.get("databricks_jobs", [])
    question = conversation.get("question", "")
    
    if status == "completed":
        return {
            "current_step": "Completed",
            "percentage": 100
        }
    elif status == "error":
        error_msg = conversation.get("error", "Error occurred")
        return {
            "current_step": error_msg,
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
        # Check if running for more than 2 minutes
        first_job = running_jobs[0]
        started_at = datetime.fromisoformat(first_job["started_at"].replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - started_at
        
        current_reasoning = first_job.get("reasoning", "Executing Spark SQL...")
        
        if elapsed > timedelta(minutes=2):
            # Check if we already generated delay message
            delay_message = first_job.get("delay_message")
            minutes_elapsed = int(elapsed.total_seconds() / 60)
            
            if not delay_message:
                # Generate delay message using LLM (same language as question)
                delay_message = _generate_delay_message(question, current_reasoning, minutes_elapsed)
                # Cache it in job to avoid regenerating on every poll
                first_job["delay_message"] = delay_message
            
            return {
                "current_step": delay_message,
                "percentage": 50
            }
        else:
            return {
                "current_step": current_reasoning,
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
