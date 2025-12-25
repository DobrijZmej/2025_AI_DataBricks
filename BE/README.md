# IMDb Analytics Backend - LLM Orchestration Layer

## 🎯 Етап 6: LLM-оркестрація (РЕАЛІЗОВАНО)

Цей backend реалізує **tool-based LLM orchestration** для аналітики IMDb даних через Databricks Lakehouse.

## 🏗️ Архітектура

```
User Question
    ↓
Azure Function: /api/chat
    ↓
LLM Orchestrator (Azure OpenAI + Function Calling)
    ↓
[Decide: Answer directly OR call tool]
    ↓
Tool: execute_spark_sql
    ↓
Databricks Jobs API
    ↓
Spark SQL Execution (near data)
    ↓
Delta Lake (IMDb data)
    ↓
Results → LLM → Final Answer
```

## 📡 API Endpoints

### 1. `/api/chat` - LLM-powered Chat (NEW)

**Призначення:** Інтелектуальний чат з автоматичною генерацією SQL та виконанням запитів

**Request:**
```json
POST https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat

{
  "question": "What are the top 5 highest rated movies from 2020?"
}
```

**Response:**
```json
{
  "status": "success",
  "final_answer": "Based on the IMDb data, here are the top 5 highest rated movies from 2020:\n\n1. Movie A (Rating: 8.9)\n2. Movie B (Rating: 8.7)\n...",
  "tool_calls": [
    {
      "iteration": 1,
      "tool": "execute_spark_sql",
      "arguments": {
        "sql_query": "SELECT m.primaryTitle, r.averageRating FROM imdb.movies_delta m JOIN imdb.ratings_delta r ON m.tconst = r.tconst WHERE m.startYear = 2020 ORDER BY r.averageRating DESC LIMIT 5",
        "reasoning": "Query joins movies with ratings, filters by year 2020, and sorts by rating"
      },
      "result": {
        "status": "success",
        "run_id": 114457146469168
      }
    }
  ],
  "iterations": 2
}
```

**Приклади запитів:**
- "Show me movies with Tom Hanks"
- "What are the highest rated sci-fi movies?"
- "Generate a short description for The Matrix"
- "List directors who worked on more than 5 movies"

---

### 2. `/api/run_databricks_job` - Direct SQL Execution (Legacy)

**Призначення:** Прямий виклик Databricks Job з SQL (без LLM)

**Request:**
```json
POST https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/run_databricks_job

{
  "sql_text": "SELECT primaryTitle FROM imdb.movies_delta LIMIT 5"
}
```

**Response:**
```json
{
  "run_id": 114457146469168,
  "number_in_job": 114457146469168
}
```

## 🔧 Environment Variables

Налаштуйте в Azure Function App Configuration:

### Databricks (вже налаштовані):
- `DATABRICKS_HOST` - Databricks workspace URL
- `DATABRICKS_TOKEN` - Personal Access Token
- `DATABRICKS_JOB_ID` - ID job'а для SQL execution

### Azure OpenAI (ПОТРІБНО ДОДАТИ):
- `AZURE_OPENAI_ENDPOINT` - Azure OpenAI endpoint (напр. `https://your-resource.openai.azure.com/`)
- `AZURE_OPENAI_KEY` - Azure OpenAI API key
- `AZURE_OPENAI_DEPLOYMENT` - Deployment name (напр. `gpt-4`)

### Як додати через Azure CLI:
```powershell
az functionapp config appsettings set `
  --name imdb-dbx-backend-func `
  --resource-group EPAM_AI_DataBricks `
  --settings `
    "AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/" `
    "AZURE_OPENAI_KEY=your-key" `
    "AZURE_OPENAI_DEPLOYMENT=gpt-4"
```

## 🎭 LLM Orchestration Logic

### System Prompt
LLM отримує інструкції:
- Розуміти питання про фільми, рейтинги, акторів
- Вирішувати: відповісти одразу VS викликати tool
- Генерувати Spark SQL при потребі
- Інтерпретувати результати

### Tool Definition
```python
execute_spark_sql(sql_query, reasoning)
```

**Опис для LLM:**
- Доступні таблиці: `imdb.movies_delta`, `imdb.ratings_delta`, etc.
- AI функції: `ai_movie_summary(primaryTitle)`
- Правила: лише SELECT, макс 100 рядків

### Decision Flow
1. **User asks:** "Top rated movies?"
2. **LLM decides:** Need data → call tool
3. **LLM generates SQL:** `SELECT ... ORDER BY rating DESC LIMIT 10`
4. **Tool executes:** Databricks Job triggered
5. **LLM interprets:** "Here are the top movies..."

## 🚀 Deployment

### 1. Встановити залежності локально (опційно):
```powershell
pip install -r requirements.txt
```

### 2. Деплой через VS Code:
- F1 → `Azure Functions: Deploy to Function App`
- Вибрати `imdb-dbx-backend-func`

### 3. Або через CLI:
```powershell
func azure functionapp publish imdb-dbx-backend-func
```

## 🧪 Testing

### Test Chat Endpoint:
```powershell
$body = @{
    question = "What are the top 3 highest rated movies?"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/chat" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

### Test Direct SQL (Legacy):
```powershell
$body = @{
    sql_text = "SELECT primaryTitle FROM imdb.movies_delta LIMIT 3"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://imdb-dbx-backend-func-buheg0bce0bvahbz.westeurope-01.azurewebsites.net/api/run_databricks_job" `
  -Method POST `
  -Body $body `
  -ContentType "application/json" `
  -UseBasicParsing
```

## 📊 Architecture Principles

### ✅ Data-Centric Design
- **Дані не виходять з Lakehouse**
- Spark - єдиний execution engine
- Backend - лише orchestrator

### ✅ LLM Near Data
- AI функції виконуються в Spark
- `ai_movie_summary()` працює поруч із даними
- Мінімальна латентність

### ✅ Tool-Based Orchestration
- LLM вирішує ЩО робити
- Spark виконує ЯК робити
- Чітке розділення відповідальності

### ✅ Explicit Intent
- Tool calling явний та прозорий
- Логування всіх викликів
- Повна трасованість

## 📝 Files Structure

```
BE/
├── function_app.py          # Azure Functions (2 endpoints)
├── llm_orchestrator.py      # LLM orchestration logic
├── requirements.txt         # Python dependencies
├── host.json                # Azure Functions config
└── README.md                # This file
```

## 🎓 Learning Outcomes (Етап 6)

✅ **Реалізовано:**
- Tool-based LLM orchestration
- Function calling з Azure OpenAI
- Інтеграція LLM + Databricks
- Chat endpoint з інтелектуальним роутингом
- SQL generation та validation

✅ **Продемонстровано:**
- LLM як orchestrator (not executor)
- Data-centric AI architecture
- Separation of concerns
- Explicit tool calling patterns

## 🔮 Next Steps (Етап 7)

- [ ] Додати Frontend (chat UI)
- [ ] Реалізувати async результати (polling Databricks Job)
- [ ] Додати streaming відповідей
- [ ] Кешування результатів
- [ ] Rate limiting

## 📚 References

- [Azure Functions Python](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Azure OpenAI Function Calling](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/function-calling)
- [Databricks Jobs API](https://docs.databricks.com/api/workspace/jobs/runnow)
