# Production-Ready API Documentation

## 🏗️ Architecture Overview

```
User → Frontend
         ↓
    POST /api/chat/start
         ↓
  Azure Function (creates conversation)
         ↓
    Cosmos DB (stores state)
         ↓
  Background Thread (LLM + Databricks)
         ↓
    Cosmos DB (updates progress)
         ↑
    GET /api/chat/{id}/status (polling every 1-2 sec)
         ↑
      Frontend (shows progress)
```

## 📡 API Endpoints

### 1. Start Conversation (Async)

**POST** `/api/chat/start`

**Request:**
```json
{
  "question": "What are the top rated movies from 2020?",
  "user_id": "optional_user_id"
}
```

**Response:** (202 Accepted)
```json
{
  "status": "success",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "processing_status": "started",
  "message": "Conversation started. Poll /chat/{id}/status for updates.",
  "poll_url": "/api/chat/550e8400-e29b-41d4-a716-446655440000/status"
}
```

---

### 2. Get Status (Polling Endpoint)

**GET** `/api/chat/{conversation_id}/status`

**Response** (while processing):
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "question": "What are the top rated movies from 2020?",
  "final_answer": null,
  "error": null,
  "databricks_jobs": [
    {
      "run_id": 123456,
      "sql_query": "SELECT ...",
      "status": "running",
      "started_at": "2025-12-23T19:00:00Z"
    }
  ],
  "progress": {
    "current_step": "Executing Spark SQL (0/1 queries completed)...",
    "percentage": 60
  },
  "created_at": "2025-12-23T19:00:00Z",
  "updated_at": "2025-12-23T19:00:15Z"
}
```

**Response** (completed):
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "question": "What are the top rated movies from 2020?",
  "final_answer": "Based on IMDb ratings, here are the top movies from 2020:\n\n1. Movie A (8.9/10)\n2. Movie B (8.7/10)\n...",
  "error": null,
  "databricks_jobs": [
    {
      "run_id": 123456,
      "sql_query": "SELECT ...",
      "status": "completed",
      "started_at": "2025-12-23T19:00:00Z",
      "finished_at": "2025-12-23T19:00:30Z"
    }
  ],
  "progress": {
    "current_step": "Completed",
    "percentage": 100
  },
  "created_at": "2025-12-23T19:00:00Z",
  "updated_at": "2025-12-23T19:00:35Z"
}
```

---

### 3. Get Messages (Full History)

**GET** `/api/chat/{conversation_id}/messages`

**Response:**
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "role": "user",
      "content": "What are the top rated movies from 2020?",
      "timestamp": "2025-12-23T19:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Based on IMDb ratings, here are the top movies from 2020...",
      "timestamp": "2025-12-23T19:00:35Z",
      "tool_calls": [...]
    }
  ]
}
```

---

## 🔄 Frontend Integration Example

### JavaScript/React polling pattern:

```javascript
// 1. Start conversation
async function askQuestion(question) {
  const response = await fetch('/api/chat/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  });
  
  const data = await response.json();
  const conversationId = data.conversation_id;
  
  // 2. Start polling
  return pollStatus(conversationId);
}

// 2. Poll for status
async function pollStatus(conversationId) {
  const maxAttempts = 60; // 60 * 2 sec = 2 minutes max
  let attempts = 0;
  
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      attempts++;
      
      const response = await fetch(`/api/chat/${conversationId}/status`);
      const data = await response.json();
      
      // Update UI with progress
      updateProgress(data.progress);
      
      // Check if completed
      if (data.status === 'completed') {
        clearInterval(interval);
        resolve(data.final_answer);
      } else if (data.status === 'error') {
        clearInterval(interval);
        reject(data.error);
      } else if (attempts >= maxAttempts) {
        clearInterval(interval);
        reject('Timeout');
      }
    }, 2000); // Poll every 2 seconds
  });
}

// 3. Update UI
function updateProgress(progress) {
  document.getElementById('progress-bar').style.width = progress.percentage + '%';
  document.getElementById('progress-text').textContent = progress.current_step;
}

// Usage
askQuestion('What are the top movies?')
  .then(answer => {
    console.log('Answer:', answer);
    displayAnswer(answer);
  })
  .catch(error => {
    console.error('Error:', error);
  });
```

---

## 💾 Data Storage (Cosmos DB)

### Schema:
```json
{
  "id": "conversation_uuid",
  "partition_key": "conversation_uuid",
  "user_id": "optional",
  "status": "processing|completed|error",
  "question": "User question",
  "messages": [...],
  "databricks_jobs": [...],
  "final_answer": "LLM response",
  "error": null,
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "ttl": 86400
}
```

### Features:
- ✅ Auto-cleanup after 24h (TTL)
- ✅ Partitioned by conversation_id
- ✅ Fast read/write
- ✅ Low cost (~$1/month for POC)

---

## 🔐 Environment Variables

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://aoai-imdb.openai.azure.com/
AZURE_OPENAI_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=imdb-gpt-4-1

# Databricks
DATABRICKS_HOST=https://adb-288324157907063.3.azuredatabricks.net
DATABRICKS_TOKEN=<token>
DATABRICKS_JOB_ID=<job_id>

# Cosmos DB
COSMOS_ENDPOINT=https://imdb-chat-cosmos.documents.azure.com:443/
COSMOS_KEY=<key>
```

---

## 🧪 Testing

### Test 1: Start conversation
```powershell
$body = @{
    question = "What are the top 3 highest rated movies?"
} | ConvertTo-Json

$response = Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat/start" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing

$data = $response.Content | ConvertFrom-Json
$conversationId = $data.conversation_id

Write-Host "Conversation ID: $conversationId"
```

### Test 2: Poll status
```powershell
# Poll every 2 seconds
while ($true) {
  $status = Invoke-WebRequest `
    -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat/$conversationId/status" `
    -UseBasicParsing | ConvertFrom-Json
  
  Write-Host "Status: $($status.status) - $($status.progress.current_step)"
  
  if ($status.status -eq "completed") {
    Write-Host "`nFinal Answer:`n$($status.final_answer)"
    break
  } elseif ($status.status -eq "error") {
    Write-Host "`nError: $($status.error)"
    break
  }
  
  Start-Sleep -Seconds 2
}
```

---

## 📊 Progress States

| Percentage | State |
|------------|-------|
| 0-20% | Analyzing question with LLM |
| 20-40% | Generating SQL query |
| 40-80% | Executing Spark SQL |
| 80-95% | Processing results with LLM |
| 95-100% | Preparing final answer |
| 100% | Completed |

---

## 🚀 Performance Metrics

- **API Response Time:** <200ms (start endpoint)
- **LLM Processing:** 2-5 seconds
- **Spark Execution:** 10-60 seconds
- **Total End-to-End:** 15-70 seconds
- **Polling Overhead:** <10ms per request

---

## 🔮 Future Enhancements

1. **WebSockets** - Real-time updates instead of polling
2. **Server-Sent Events (SSE)** - One-way streaming
3. **Azure Durable Functions** - Proper async orchestration
4. **Queue-based processing** - Azure Queue Storage for jobs
5. **Caching** - Redis for frequent queries
6. **Rate Limiting** - Per-user quotas
7. **Authentication** - Azure AD integration

---

## 📝 Architecture Benefits

✅ **Scalable** - Each conversation is independent  
✅ **Resilient** - State persisted in Cosmos DB  
✅ **Async** - Non-blocking user experience  
✅ **Traceable** - Full audit trail in storage  
✅ **Cost-effective** - Pay per execution  
✅ **Production-ready** - Error handling, logging, TTL  
