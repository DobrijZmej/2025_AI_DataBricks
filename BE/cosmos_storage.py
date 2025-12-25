"""
Cosmos DB Storage for Conversations
====================================

This module manages conversation storage in Azure Cosmos DB.

Schema:
    {
        "id": "conv_uuid",
        "partition_key": "conv_uuid",
        "user_id": "optional_user_id",
        "status": "processing|completed|error",
        "question": "User's original question",
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "...", "tool_calls": [...]}
        ],
        "databricks_jobs": [
            {
                "run_id": 123,
                "sql_query": "SELECT ...",
                "status": "pending|running|completed|failed",
                "result": {...}
            }
        ],
        "final_answer": "LLM's final response",
        "error": null,
        "created_at": "2025-12-23T19:00:00Z",
        "updated_at": "2025-12-23T19:01:00Z",
        "ttl": 86400
    }
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from azure.cosmos import CosmosClient, PartitionKey, exceptions

logger = logging.getLogger(__name__)


class ConversationStorage:
    """
    Manages conversation persistence in Cosmos DB.
    """
    
    def __init__(
        self,
        cosmos_endpoint: str,
        cosmos_key: str,
        database_name: str = "imdb_chat",
        container_name: str = "conversations"
    ):
        """
        Initialize Cosmos DB client.
        
        Args:
            cosmos_endpoint: Cosmos DB endpoint URL
            cosmos_key: Cosmos DB master key
            database_name: Database name (will be created if not exists)
            container_name: Container name (will be created if not exists)
        """
        self.client = CosmosClient(cosmos_endpoint, cosmos_key)
        self.database_name = database_name
        self.container_name = container_name
        
        # Create database and container if not exist
        self._ensure_database_and_container()
        
        self.container = self.client.get_database_client(database_name).get_container_client(container_name)
        
        logger.info(f"Cosmos DB initialized: {database_name}/{container_name}")
    
    def _ensure_database_and_container(self):
        """Create database and container if they don't exist."""
        try:
            # Create database
            database = self.client.create_database_if_not_exists(id=self.database_name)
            logger.info(f"Database ready: {self.database_name}")
            
            # Create container with partition key and TTL
            container = database.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/partition_key"),
                default_ttl=86400  # 24 hours TTL
            )
            logger.info(f"Container ready: {self.container_name}")
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error creating database/container: {e}")
            raise
    
    def create_conversation(
        self,
        question: str,
        device_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create new conversation.
        
        Args:
            question: User's question
            device_id: Device identifier from frontend (for conversation history)
            user_id: Optional user identifier
        
        Returns:
            Created conversation document
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        conversation = {
            "id": conversation_id,
            "partition_key": conversation_id,
            "device_id": device_id,
            "user_id": user_id,
            "status": "processing",
            "question": question,
            "messages": [
                {
                    "role": "user",
                    "content": question,
                    "timestamp": now
                }
            ],
            "databricks_jobs": [],
            "final_answer": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "ttl": 86400
        }
        
        try:
            created = self.container.create_item(body=conversation)
            logger.info(f"Conversation created: {conversation_id}")
            return created
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error creating conversation: {e}")
            raise
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation by ID.
        
        Args:
            conversation_id: Conversation ID
        
        Returns:
            Conversation document or None if not found
        """
        try:
            item = self.container.read_item(
                item=conversation_id,
                partition_key=conversation_id
            )
            return item
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error reading conversation: {e}")
            raise
    
    def get_conversations_by_device(
        self,
        device_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations for a specific device.
        
        Args:
            device_id: Device identifier
            limit: Maximum number of conversations to return
        
        Returns:
            List of conversation summaries sorted by created_at (newest first)
        """
        try:
            query = """
                SELECT 
                    c.id, 
                    c.device_id, 
                    c.status, 
                    c.question, 
                    c.final_answer,
                    c.error,
                    c.progress,
                    c.created_at, 
                    c.updated_at
                FROM c
                WHERE c.device_id = @device_id
                ORDER BY c.created_at DESC
                OFFSET 0 LIMIT @limit
            """
            
            parameters = [
                {"name": "@device_id", "value": device_id},
                {"name": "@limit", "value": limit}
            ]
            
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            
            logger.info(f"Found {len(items)} conversations for device {device_id}")
            return items
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error querying conversations: {e}")
            raise
    
    def update_conversation(
        self,
        conversation_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update conversation fields.
        
        Args:
            conversation_id: Conversation ID
            updates: Dictionary of fields to update
        
        Returns:
            Updated conversation document
        """
        try:
            # Read current conversation
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation not found: {conversation_id}")
            
            # Apply updates
            conversation.update(updates)
            conversation["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Write back
            updated = self.container.replace_item(
                item=conversation_id,
                body=conversation
            )
            
            logger.info(f"Conversation updated: {conversation_id}")
            return updated
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error updating conversation: {e}")
            raise
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Add message to conversation.
        
        Args:
            conversation_id: Conversation ID
            role: Message role (user|assistant|system)
            content: Message content
            tool_calls: Optional tool calls metadata
        
        Returns:
            Updated conversation document
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")
        
        conversation["messages"].append(message)
        
        return self.update_conversation(conversation_id, {
            "messages": conversation["messages"]
        })
    
    def add_databricks_job(
        self,
        conversation_id: str,
        run_id: int,
        sql_query: str,
        reasoning: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register Databricks job execution.
        
        Args:
            conversation_id: Conversation ID
            run_id: Databricks run ID
            sql_query: SQL query being executed
            reasoning: LLM's reasoning for this query
        
        Returns:
            Updated conversation document
        """
        job = {
            "run_id": run_id,
            "sql_query": sql_query,
            "reasoning": reasoning,
            "status": "pending",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "result": None
        }
        
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")
        
        conversation["databricks_jobs"].append(job)
        
        return self.update_conversation(conversation_id, {
            "databricks_jobs": conversation["databricks_jobs"]
        })
    
    def update_databricks_job_status(
        self,
        conversation_id: str,
        run_id: int,
        status: str,
        result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update Databricks job status.
        
        Args:
            conversation_id: Conversation ID
            run_id: Databricks run ID
            status: Job status (running|completed|failed)
            result: Optional job result
        
        Returns:
            Updated conversation document
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")
        
        # Find and update job
        for job in conversation["databricks_jobs"]:
            if job["run_id"] == run_id:
                job["status"] = status
                if result:
                    job["result"] = result
                if status in ["completed", "failed"]:
                    job["finished_at"] = datetime.now(timezone.utc).isoformat()
                break
        
        return self.update_conversation(conversation_id, {
            "databricks_jobs": conversation["databricks_jobs"]
        })
    
    def set_final_answer(
        self,
        conversation_id: str,
        answer: str
    ) -> Dict[str, Any]:
        """
        Set final answer and mark conversation as completed.
        
        Args:
            conversation_id: Conversation ID
            answer: Final answer from LLM
        
        Returns:
            Updated conversation document
        """
        return self.update_conversation(conversation_id, {
            "status": "completed",
            "final_answer": answer
        })
    
    def set_error(
        self,
        conversation_id: str,
        error: str
    ) -> Dict[str, Any]:
        """
        Mark conversation as failed with error.
        
        Args:
            conversation_id: Conversation ID
            error: Error message
        
        Returns:
            Updated conversation document
        """
        return self.update_conversation(conversation_id, {
            "status": "error",
            "error": error
        })


def create_storage() -> ConversationStorage:
    """
    Create storage instance from environment variables.
    
    Returns:
        Configured ConversationStorage instance
    
    Raises:
        KeyError: If required environment variables are missing
    """
    cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
    cosmos_key = os.environ["COSMOS_KEY"]
    
    return ConversationStorage(
        cosmos_endpoint=cosmos_endpoint,
        cosmos_key=cosmos_key
    )
