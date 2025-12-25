"""
Databricks Client for Job Management
=====================================

This module provides async job execution and status polling.
"""

import os
import time
import logging
import requests
import json
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DatabricksClient:
    """
    Client for Databricks Jobs API with async execution support.
    """
    
    def __init__(
        self,
        databricks_host: str,
        databricks_token: str,
        job_id: int
    ):
        """
        Initialize Databricks client.
        
        Args:
            databricks_host: Databricks workspace URL
            databricks_token: Personal Access Token
            job_id: Default job ID for SQL execution
        """
        self.host = databricks_host.rstrip("/")
        self.token = databricks_token
        self.job_id = job_id
        self.headers = {
            "Authorization": f"Bearer {databricks_token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Databricks client initialized: {self.host}")
    
    def trigger_job(self, sql_query: str) -> Dict[str, Any]:
        """
        Trigger Databricks job with SQL query.
        
        Args:
            sql_query: SQL query to execute
        
        Returns:
            Dictionary with run_id and status
        
        Raises:
            requests.RequestException: If API call fails
        """
        url = f"{self.host}/api/2.1/jobs/run-now"
        
        payload = {
            "job_id": self.job_id,
            "notebook_params": {
                "sql_text": sql_query
            }
        }
        
        logger.info(f"Triggering Databricks job {self.job_id}")
        logger.info(f"SQL: {sql_query[:100]}...")
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            run_id = result.get("run_id")
            logger.info(f"Job triggered successfully: run_id={run_id}")
            
            return {
                "status": "success",
                "run_id": run_id,
                "number_in_job": result.get("number_in_job")
            }
        
        except requests.RequestException as e:
            logger.error(f"Error triggering job: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_run_status(self, run_id: int) -> Dict[str, Any]:
        """
        Get Databricks job run status.
        
        Args:
            run_id: Run ID from trigger_job
        
        Returns:
            Dictionary with status, state, and result
        """
        url = f"{self.host}/api/2.1/jobs/runs/get"
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params={"run_id": run_id},
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            state = data.get("state", {})
            life_cycle_state = state.get("life_cycle_state")
            result_state = state.get("result_state")
            state_message = state.get("state_message", "")
            
            logger.info(f"Run {run_id}: {life_cycle_state} / {result_state}")
            
            return {
                "status": "success",
                "run_id": run_id,
                "life_cycle_state": life_cycle_state,
                "result_state": result_state,
                "state_message": state_message,
                "is_running": life_cycle_state in ["PENDING", "RUNNING"],
                "is_completed": life_cycle_state == "TERMINATED",
                "is_successful": result_state == "SUCCESS",
                "raw_response": data
            }
        
        except requests.RequestException as e:
            logger.error(f"Error getting run status: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def wait_for_completion(
        self,
        run_id: int,
        max_wait_seconds: int = 300,
        poll_interval_seconds: int = 3
    ) -> Dict[str, Any]:
        """
        Wait for job completion (synchronous polling).
        
        Args:
            run_id: Run ID to wait for
            max_wait_seconds: Maximum time to wait
            poll_interval_seconds: Seconds between status checks
        
        Returns:
            Final job status
        """
        start_time = time.time()
        logger.info(f"Waiting for run {run_id} to complete (max {max_wait_seconds}s)")
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > max_wait_seconds:
                logger.warning(f"Timeout waiting for run {run_id}")
                return {
                    "status": "timeout",
                    "run_id": run_id,
                    "elapsed_seconds": elapsed
                }
            
            status = self.get_run_status(run_id)
            
            if status["status"] == "error":
                return status
            
            if status["is_completed"]:
                logger.info(f"Run {run_id} completed: {status['result_state']}")
                return status
            
            logger.info(f"Run {run_id} still running, waiting {poll_interval_seconds}s...")
            time.sleep(poll_interval_seconds)
    
    def get_run_output(self, run_id: int) -> Optional[Any]:
        """
        Get job run output from notebook execution.
        
        For multi-task jobs, we need to get the task run_id first,
        then query its output using runs/get-output API.
        
        Args:
            run_id: Job run ID
        
        Returns:
            Parsed notebook output (list of results) or None
        """
        # First, get the run status to find task run_id
        run_status = self.get_run_status(run_id)
        if run_status.get("status") != "success":
            logger.error(f"Cannot get output - run {run_id} status check failed")
            return None
        
        # Extract task run_id from the raw response
        raw_response = run_status.get("raw_response", {})
        tasks = raw_response.get("tasks", [])
        
        if not tasks:
            logger.warning(f"No tasks found in run {run_id}")
            return None
        
        # Get the first task (execute_sql task)
        task = tasks[0]
        task_run_id = task.get("run_id")
        task_key = task.get("task_key", "execute_sql")
        
        if not task_run_id:
            logger.warning(f"No task run_id found in run {run_id}")
            return None
        
        logger.info(f"Found task '{task_key}' with run_id {task_run_id} for job run {run_id}")
        
        # Now query the task output
        url = f"{self.host}/api/2.1/jobs/runs/get-output"
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params={"run_id": task_run_id},  # Use task run_id, not job run_id
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Log the raw response structure for debugging
            logger.info(f"get_run_output response keys for task {task_run_id}: {list(data.keys())}")
            
            # Check for notebook output
            notebook_output = data.get("notebook_output")
            if notebook_output:
                logger.info(f"Found notebook_output with keys: {list(notebook_output.keys())}")
                result_data = notebook_output.get("result")
                if result_data:
                    logger.info(f"Retrieved notebook result for task {task_run_id}: {result_data[:100] if isinstance(result_data, str) else 'data'}")
                    return self._parse_result_data(result_data)
            
            # Check for error
            error = data.get("error")
            if error:
                logger.error(f"Notebook execution error for task {task_run_id}: {error}")
                return None
            
            # Check metadata
            metadata = data.get("metadata")
            if metadata:
                state = metadata.get("state", {})
                result_state = state.get("result_state")
                if result_state == "SUCCESS":
                    logger.warning(f"Task {task_run_id} succeeded but no output captured. Check if notebook uses dbutils.notebook.exit()")
                    return None
            
            logger.warning(f"No output found for task {task_run_id}. Response keys: {list(data.keys())}")
            return None
        
        except requests.RequestException as e:
            logger.error(f"Error getting task output: {e}")
            return None
    
    def _parse_result_data(self, result_data: Any) -> Optional[Any]:
        """
        Parse result data from notebook output.
        
        Args:
            result_data: Raw result data (string or dict)
        
        Returns:
            Parsed results or None
        """
        try:
            # If it's already a dict/list, return it
            if isinstance(result_data, (dict, list)):
                return result_data
            
            # If it's a string, try to parse as JSON
            if isinstance(result_data, str):
                result_data = result_data.strip()
                if result_data.startswith('[') or result_data.startswith('{'):
                    return json.loads(result_data)
                else:
                    # Maybe it's plain text output - return as is
                    return result_data
            
            return result_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing result data as JSON: {e}")
            return result_data  # Return as is if can't parse
        except Exception as e:
            logger.error(f"Error parsing result data: {e}")
            return None


def create_client() -> DatabricksClient:
    """
    Create Databricks client from environment variables.
    
    Returns:
        Configured DatabricksClient instance
    
    Raises:
        KeyError: If required environment variables are missing
    """
    databricks_host = os.environ["DATABRICKS_HOST"]
    databricks_token = os.environ["DATABRICKS_TOKEN"]
    databricks_job_id = int(os.environ["DATABRICKS_JOB_ID"])
    
    return DatabricksClient(
        databricks_host=databricks_host,
        databricks_token=databricks_token,
        job_id=databricks_job_id
    )
