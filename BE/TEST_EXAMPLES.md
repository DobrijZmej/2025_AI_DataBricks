# Test Examples for LLM Orchestration

## Setup Azure OpenAI Environment Variables

Before testing, configure Azure OpenAI in your Function App:

```powershell
az functionapp config appsettings set `
  --name imdb-dbx-backend-func `
  --resource-group EPAM_AI_DataBricks `
  --settings `
    "AZURE_OPENAI_ENDPOINT=<your-endpoint>" `
    "AZURE_OPENAI_KEY=<your-key>" `
    "AZURE_OPENAI_DEPLOYMENT=<deployment-name>"
```

## Test 1: Simple Question (LLM should answer directly)

```powershell
$body = @{
    question = "Who is Tom Hanks?"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected:** LLM answers from general knowledge, NO tool calls

---

## Test 2: Data Query (LLM should call tool)

```powershell
$body = @{
    question = "What are the top 5 highest rated movies?"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected:** LLM generates SQL, calls `execute_spark_sql`, returns results

**SQL Generated (example):**
```sql
SELECT m.primaryTitle, r.averageRating 
FROM imdb.movies_delta m 
JOIN imdb.ratings_delta r ON m.tconst = r.tconst 
ORDER BY r.averageRating DESC 
LIMIT 5
```

---

## Test 3: Specific Year Filter

```powershell
$body = @{
    question = "Show me popular movies from 2020"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected SQL:**
```sql
SELECT primaryTitle, averageRating 
FROM imdb.movies_delta m 
JOIN imdb.ratings_delta r ON m.tconst = r.tconst 
WHERE m.startYear = 2020 
ORDER BY r.numVotes DESC 
LIMIT 10
```

---

## Test 4: AI Function Usage

```powershell
$body = @{
    question = "Generate a short description for the movie Inception"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected SQL:**
```sql
SELECT primaryTitle, ai_movie_summary(primaryTitle) AS summary 
FROM imdb.movies_delta 
WHERE primaryTitle LIKE '%Inception%' 
LIMIT 1
```

---

## Test 5: Complex Join

```powershell
$body = @{
    question = "Which actors appeared in movies with rating above 8.5?"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected:** Multi-table JOIN with complex filtering

---

## Test 6: Genre Filter

```powershell
$body = @{
    question = "List top 10 sci-fi movies"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

**Expected SQL:**
```sql
SELECT m.primaryTitle, r.averageRating 
FROM imdb.movies_delta m 
JOIN imdb.ratings_delta r ON m.tconst = r.tconst 
WHERE m.genres LIKE '%Sci-Fi%' 
ORDER BY r.averageRating DESC 
LIMIT 10
```

---

## Analyzing Response

Response structure:
```json
{
  "status": "success",
  "final_answer": "Human-readable answer from LLM",
  "tool_calls": [
    {
      "iteration": 1,
      "tool": "execute_spark_sql",
      "arguments": {
        "sql_query": "SELECT ...",
        "reasoning": "Why this query"
      },
      "result": {
        "status": "success",
        "run_id": 123456789
      }
    }
  ],
  "iterations": 2
}
```

**Key metrics:**
- `iterations`: How many LLM calls were made
- `tool_calls`: Which tools were invoked
- `final_answer`: User-friendly response

---

## Debugging

### Check logs:
```powershell
az functionapp logs tail `
  --name imdb-dbx-backend-func `
  --resource-group EPAM_AI_DataBricks
```

### Common issues:

1. **Missing Azure OpenAI config:**
   - Error: "Missing environment variable: AZURE_OPENAI_ENDPOINT"
   - Fix: Add environment variables

2. **Invalid deployment name:**
   - Error: "The API deployment for this resource does not exist"
   - Fix: Use correct deployment name (e.g., "gpt-4", "gpt-35-turbo")

3. **Databricks Job timeout:**
   - Tool result shows: "Databricks job triggered successfully"
   - This is async - check Databricks UI for results

4. **SQL validation failed:**
   - LLM might generate invalid SQL
   - Check tool_calls[].arguments.sql_query in response

---

## Performance Expectations

- **LLM response time:** 2-5 seconds (depends on complexity)
- **Tool calling overhead:** +1-2 seconds per tool call
- **Databricks Job start:** ~30 seconds (cold start)
- **Total user experience:** 5-40 seconds (depends on query)

**Optimization tips:**
- Use warmed Databricks cluster
- Cache frequent queries
- Implement streaming responses
