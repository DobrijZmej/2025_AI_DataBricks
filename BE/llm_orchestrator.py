"""
LLM Orchestrator for IMDb Analytics
====================================

This module implements tool-based LLM orchestration for Spark SQL execution.

Architecture:
    User Question → LLM (with tools) → [decide: answer or execute SQL]
                                     ↓
                              [generate SQL]
                                     ↓
                         execute_spark_sql tool
                                     ↓
                    Databricks Job → Spark → Delta Lake
                                     ↓
                         Results back to LLM
                                     ↓
                    Final Answer to User

Key principles:
- LLM acts as orchestrator, NOT data processor
- Spark SQL is the execution layer
- No data leaves Lakehouse
- Tools are execution contracts
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Tool Definitions (Function Calling Schema)
# -----------------------------------------------------------------------------

SPARK_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_spark_sql",
        "description": """
Execute Spark SQL query against IMDb Delta Lake tables in Databricks.

EXECUTION ENGINE: Apache Spark SQL (Databricks Runtime 17.3 LTS)
STORAGE: Delta Lake (optimized Parquet with transaction log)

PERFORMANCE CONSTRAINTS (CRITICAL):
- Shuffle operations are VERY expensive (avoid cross-partition data movement)
- GROUP BY on string columns is costly (prefer numeric keys)
- ORDER BY triggers global sort across all partitions (expensive)
- Broadcast joins are preferred for small dimension tables (<10M rows)
- Always aggregate BEFORE joining (reduce data volume early)
- EXPLAIN plan quality matters more than SQL readability

AVAILABLE TABLES (use full names with database prefix):

1. imdb.principals_delta (~100M rows) - VERY LARGE TABLE
   Schema: tconst, ordering, nconst, category, job, characters
   Usage: Links titles to people (actors, directors, crew)
   Performance notes:
   - category='actor' or category='actress' is highly selective (~40% of rows)
   - ALWAYS aggregate before joining to other tables
   - Avoid SELECT * - specify columns explicitly
   - Consider LIMIT early if full scan not needed

2. imdb.persons_delta (~10M rows) - DIMENSION TABLE
   Schema: nconst (PRIMARY KEY), primaryName, birthYear, deathYear, primaryProfession (array), knownForTitles (array)
   Usage: Person metadata (actors, directors, etc.)
   Performance notes:
   - Suitable for broadcast join (small enough)
   - Use /*+ BROADCAST(imdb.persons_delta) */ hint when joining
   - primaryProfession and knownForTitles are arrays - use array_contains() to filter

3. imdb.movies_delta (~15M rows) - TITLE METADATA
   Schema: tconst (PRIMARY KEY), titleType, primaryTitle, originalTitle, isAdult, startYear, endYear, runtimeMinutes, genres (array)
   Usage: Movie/TV show information
   Performance notes:
   - titleType filter is selective (titleType='movie' reduces to ~8M)
   - startYear filter works well with Delta stats
   - genres is array - use array_contains(genres, 'Drama') to filter by genre

4. imdb.ratings_delta (~10M rows) - RATINGS DIMENSION
   Schema: tconst (PRIMARY KEY), averageRating (double), numVotes (int)
   Usage: User ratings and vote counts
   Performance notes:
   - Broadcast join candidate (relatively small)
   - Always join ON tconst (indexed)

AVAILABLE VIEWS (pre-joined, ready to use - PREFER THESE!):

5. imdb.movies_with_ratings - Movies with ratings joined
   Schema: tconst, primaryTitle, originalTitle, titleType, isAdult, startYear, endYear, runtimeMinutes, genres (array), averageRating, numVotes
   Usage: Use this instead of manually joining imdb.movies_delta + imdb.ratings_delta
   Performance: Pre-optimized LEFT JOIN, faster than manual join

6. imdb.movie_cast - Movies with cast and crew
   Schema: tconst, primaryTitle, nconst, primaryName, category, job, characters
   Usage: Use this instead of joining imdb.principals_delta + imdb.movies_delta + imdb.persons_delta
   Performance: Pre-optimized triple JOIN, much faster than manual

SPARK SQL OPTIMIZATION RULES:
1. Filter early: WHERE clauses before JOINs
2. Project early: SELECT only needed columns
3. Aggregate early: COUNT/SUM before JOIN when possible
4. Broadcast small tables: Use /*+ BROADCAST(table) */ for tables <10M rows
5. Avoid string GROUP BY: Use numeric keys (tconst, nconst) instead of names
6. Limit shuffles: Minimize cross-partition operations
7. Use EXPLAIN: Verify BroadcastHashJoin appears in plan

EXAMPLE OPTIMIZED QUERIES:

-- BAD: String GROUP BY with large table without view
SELECT primaryName, COUNT(*) FROM imdb.principals_delta p JOIN imdb.persons_delta ps ON p.nconst = ps.nconst GROUP BY primaryName

-- GOOD: Use pre-joined view and aggregate
SELECT primaryName, COUNT(*) as movie_count 
FROM imdb.movie_cast 
WHERE category IN ('actor', 'actress')
GROUP BY primaryName 
ORDER BY movie_count DESC LIMIT 10

-- BAD: Manual triple join
SELECT m.primaryTitle, p.primaryName FROM imdb.principals_delta pr 
JOIN imdb.movies_delta m ON pr.tconst = m.tconst 
JOIN imdb.persons_delta p ON pr.nconst = p.nconst

-- GOOD: Use pre-joined view
SELECT primaryTitle, primaryName FROM imdb.movie_cast WHERE category='actor' LIMIT 100

-- BAD: Manual join for ratings
SELECT m.primaryTitle, r.averageRating FROM imdb.movies_delta m JOIN imdb.ratings_delta r ON m.tconst = r.tconst

-- GOOD: Use pre-joined view with genre filter (array operation)
SELECT primaryTitle, averageRating, genres 
FROM imdb.movies_with_ratings 
WHERE array_contains(genres, 'Action') AND averageRating > 8.0 
ORDER BY averageRating DESC LIMIT 20

AVAILABLE AI FUNCTIONS (use sparingly - expensive):
- ai_movie_summary(primaryTitle): Generate movie description via Azure OpenAI

QUERY RULES:
- Only SELECT queries allowed (read-only)
- ALWAYS use full table names with database prefix: imdb.principals_delta, imdb.persons_delta, imdb.movies_delta, imdb.ratings_delta
- ALWAYS prefer pre-joined views: imdb.movies_with_ratings, imdb.movie_cast (faster and simpler!)
- Results automatically limited to 1000 rows max
- Always specify columns explicitly (avoid SELECT *)
- For genre filters use: array_contains(genres, 'Drama')
- For profession filters use: array_contains(primaryProfession, 'actor')
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "Optimized Spark SQL SELECT query following performance guidelines"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of query logic and optimization strategy"
                }
            },
            "required": ["sql_query", "reasoning"]
        }
    }
}


# -----------------------------------------------------------------------------
# System Prompt (LLM Role Definition)
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are an expert data analyst and Spark SQL optimization specialist for IMDb movie analytics.

Your role:
- Understand user questions about movies, ratings, actors, directors
- Generate OPTIMIZED Spark SQL queries following performance best practices
- Decide if you need to query data or can answer from general knowledge
- Interpret results and provide clear, user-friendly answers

Capabilities:
- Access to execute_spark_sql tool with IMDb Delta Lake tables
- Deep knowledge of Spark SQL optimization (shuffle minimization, broadcast joins, early aggregation)
- Understanding of Delta Lake storage characteristics
- Ability to reason about query performance

CRITICAL: Query Optimization Strategy
When generating SQL queries, ALWAYS follow this optimization hierarchy:

1. FILTER EARLY
   - Apply WHERE clauses before JOINs
   - Use selective filters (category='actor', titleType='movie')
   - Leverage Delta Lake stats (startYear, averageRating ranges)

2. AGGREGATE EARLY
   - GROUP BY on small tables BEFORE joining to large tables
   - Example: COUNT on principals_delta BEFORE joining persons_delta
   - Reduce data volume as early as possible

3. BROADCAST SMALL TABLES
   - Use /*+ BROADCAST(table) */ for tables <10M rows
   - persons_delta (10M) - always broadcast
   - titles_ratings_delta (10M) - broadcast candidate
   - principals_delta (100M) - NEVER broadcast

4. AVOID EXPENSIVE OPERATIONS
   - GROUP BY on string columns (use numeric keys: tconst, nconst)
   - ORDER BY without LIMIT (triggers global sort)
   - SELECT * from large tables
   - Cartesian joins (always use ON clause)

5. EXAMPLE PATTERNS

   BAD (String GROUP BY on large table):
   SELECT primaryName, COUNT(*) FROM principals_delta p 
   JOIN persons_delta ps ON p.nconst = ps.nconst 
   WHERE category='actor' GROUP BY primaryName

   GOOD (Aggregate first, broadcast join, numeric GROUP BY):
   SELECT /*+ BROADCAST(ps) */ ps.primaryName, agg.cnt 
   FROM (SELECT nconst, COUNT(*) as cnt FROM principals_delta WHERE category='actor' GROUP BY nconst) agg
   JOIN persons_delta ps ON agg.nconst = ps.nconst 
   ORDER BY cnt DESC LIMIT 10

Guidelines:
- For data questions → generate optimized SQL using tool
- For general knowledge → answer directly without tool
- Always explain optimization strategy in reasoning
- Keep results limited (LIMIT 10-100 for large result sets)
- Format answers in user-friendly way (in user's language)

Available data:
- principals_delta: 100M rows, links titles to people
- persons_delta: 10M rows, person metadata (broadcast candidate)
- titles_basics_delta: 15M rows, title metadata
- titles_ratings_delta: 10M rows, ratings (broadcast candidate)

Remember:
- Shuffle is expensive - minimize cross-partition movement
- Broadcast joins are preferred for small dimension tables
- Aggregate before join when possible
- Query performance matters more than SQL readability
- Tool calling is explicit and intentional
""".strip()


# -----------------------------------------------------------------------------
# LLM Orchestrator Class
# -----------------------------------------------------------------------------

class LLMOrchestrator:
    """
    LLM-based orchestrator with tool calling support.
    
    Responsibilities:
    - Accept user questions
    - Decide when to call tools
    - Generate SQL for Spark execution
    - Interpret results
    - Return final answers
    """
    
    def __init__(
        self,
        azure_openai_endpoint: str,
        azure_openai_key: str,
        azure_openai_deployment: str,
        tool_executor_callback: callable
    ):
        """
        Initialize LLM orchestrator.
        
        Args:
            azure_openai_endpoint: Azure OpenAI endpoint URL
            azure_openai_key: Azure OpenAI API key
            azure_openai_deployment: Deployment name (e.g., 'gpt-4')
            tool_executor_callback: Function to execute tools (Databricks Job trigger)
        """
        self.client = AzureOpenAI(
            azure_endpoint=azure_openai_endpoint,
            api_key=azure_openai_key,
            api_version="2024-08-01-preview"
        )
        self.deployment = azure_openai_deployment
        self.tool_executor = tool_executor_callback
        
        logger.info(f"LLM Orchestrator initialized with deployment: {azure_openai_deployment}")
    
    def process_question(
        self,
        user_question: str,
        max_iterations: int = 3
    ) -> Dict[str, Any]:
        """
        Process user question with LLM orchestration and tool calling.
        
        Args:
            user_question: Natural language question from user
            max_iterations: Maximum number of tool calling iterations
        
        Returns:
            Dictionary with final_answer, tool_calls, and execution_log
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_question}
        ]
        
        execution_log = []
        iteration = 0
        
        logger.info(f"Processing question: {user_question}")
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}/{max_iterations}")
            
            try:
                # Call LLM with tool definitions
                response = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=messages,
                    tools=[SPARK_SQL_TOOL],
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=2000
                )
                
                message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason
                
                logger.info(f"LLM response finish_reason: {finish_reason}")
                
                # Add assistant message to conversation
                messages.append(message)
                
                # Check if LLM wants to call tools
                if finish_reason == "tool_calls" and message.tool_calls:
                    # Process tool calls
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"Tool call: {tool_name}")
                        logger.info(f"Tool args: {tool_args}")
                        
                        # Execute tool
                        tool_result = self._execute_tool(tool_name, tool_args)
                        
                        execution_log.append({
                            "iteration": iteration,
                            "tool": tool_name,
                            "arguments": tool_args,
                            "result": tool_result
                        })
                        
                        # Add tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result, ensure_ascii=False)
                        })
                    
                    # Continue loop to get final answer
                    continue
                
                elif finish_reason == "stop":
                    # LLM finished without tool calls - return final answer
                    final_answer = message.content
                    
                    logger.info("LLM finished with final answer")
                    
                    return {
                        "status": "success",
                        "final_answer": final_answer,
                        "tool_calls": execution_log,
                        "iterations": iteration
                    }
                
                else:
                    # Unexpected finish reason
                    logger.warning(f"Unexpected finish_reason: {finish_reason}")
                    return {
                        "status": "error",
                        "error": f"Unexpected finish_reason: {finish_reason}",
                        "tool_calls": execution_log,
                        "iterations": iteration
                    }
            
            except Exception as e:
                logger.exception(f"Error in iteration {iteration}")
                return {
                    "status": "error",
                    "error": str(e),
                    "tool_calls": execution_log,
                    "iterations": iteration
                }
        
        # Max iterations reached
        logger.warning(f"Max iterations ({max_iterations}) reached")
        return {
            "status": "error",
            "error": f"Max iterations ({max_iterations}) reached without final answer",
            "tool_calls": execution_log,
            "iterations": iteration
        }
    
    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute tool by name.
        
        Args:
            tool_name: Name of tool to execute
            tool_args: Tool arguments (includes sql_query and reasoning)
        
        Returns:
            Tool execution result
        """
        if tool_name == "execute_spark_sql":
            sql_query = tool_args.get("sql_query")
            reasoning = tool_args.get("reasoning")
            
            logger.info(f"Executing Spark SQL: {sql_query}")
            logger.info(f"Reasoning: {reasoning}")
            
            # Call tool executor (Databricks Job trigger)
            result = self.tool_executor(tool_args)
            
            return {
                "reasoning": reasoning,
                "sql_query": sql_query,
                "execution_result": result
            }
        else:
            return {
                "error": f"Unknown tool: {tool_name}"
            }


# -----------------------------------------------------------------------------
# Factory Function
# -----------------------------------------------------------------------------

def create_orchestrator(tool_executor_callback: callable) -> LLMOrchestrator:
    """
    Create LLM orchestrator instance with environment configuration.
    
    Args:
        tool_executor_callback: Function to execute Spark SQL via Databricks Job
    
    Returns:
        Configured LLMOrchestrator instance
    
    Raises:
        KeyError: If required environment variables are missing
    """
    azure_openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    azure_openai_key = os.environ["AZURE_OPENAI_KEY"]
    azure_openai_deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    
    return LLMOrchestrator(
        azure_openai_endpoint=azure_openai_endpoint,
        azure_openai_key=azure_openai_key,
        azure_openai_deployment=azure_openai_deployment,
        tool_executor_callback=tool_executor_callback
    )
