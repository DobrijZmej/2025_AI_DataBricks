# IMDb Analytics with AI-Powered Lakehouse

> **Laboratory Project:** AI-Enhanced Data Engineering with Azure Databricks and LLM Orchestration

A production-ready demonstration of modern data engineering practices combining **Azure Databricks Lakehouse**, **Delta Lake**, **LLM orchestration**, and **serverless architecture** for intelligent data analytics.

---

## 🎯 Project Overview

This project demonstrates advanced data engineering capabilities by building an **AI-powered analytics platform** that enables natural language queries over a large-scale IMDb dataset (~100M+ records). The system showcases:

- **Data Engineering:** ETL pipelines, Delta Lake optimization, Spark SQL performance tuning
- **AI Integration:** LLM orchestration with tool calling, AI-powered UDFs in Spark
- **Cloud Architecture:** Serverless compute, async patterns, distributed storage
- **Production Practices:** Partitioning strategies, query optimization, observability

### Key Achievement

**Natural language → Optimized Spark SQL → Intelligent query execution** across 100M+ records with LLM-driven query optimization and cost-effective Lakehouse architecture.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         User Interface                               │
│                  (Pure JS SPA - Static Web App)                      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ REST API
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    Azure Functions Backend                           │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  LLM Orchestrator (Azure OpenAI GPT-4 + Function Calling)  │      │
│  │          ↓ generates optimized Spark SQL ↓                 │      │
│  └────────────────────────────────────────────────────────────┘      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ Jobs API
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Azure Databricks Lakehouse                        │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │  Spark SQL Engine (Databricks Runtime 17.3 LTS)         │        │
│  │  ├─ Query Optimization (Broadcast joins, predicate      │        │
│  │  │  pushdown, Delta stats)                              │        │
│  │  ├─ AI Functions: ai_movie_summary() UDF                │        │
│  │  └─ Pre-optimized Views (movies_with_ratings, etc.)     │        │
│  └─────────────────────────────────────────────────────────┘        │
│                             ↓ reads                                 │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │              Delta Lake Storage (ADLS Gen2)             │        │
│  │  ├─ principals_delta (~100M rows - cast & crew)         │        │
│  │  ├─ persons_delta (~10M rows - actor metadata)          │        │
│  │  ├─ movies_delta (~15M rows - title metadata)           │        │
│  │  └─ ratings_delta (~10M rows - user ratings)            │        │
│  └─────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                             ↑
                             │ stores conversation state
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│  Azure Cosmos DB (NoSQL - conversation tracking with TTL)            │
└──────────────────────────────────────────────────────────────────────┘
```

### Architecture Highlights

**1. Lakehouse Pattern:**
- Delta Lake for ACID transactions on data lake storage
- Unified analytics across structured data (Parquet + transaction log)
- Schema evolution and time travel capabilities

**2. AI-Near-Data Processing:**
- LLM generates SQL but **doesn't process data** (stays in Spark)
- AI UDFs run distributed in Databricks (parallel processing)
- Minimizes data movement (computation goes to data)

**3. Async Polling Architecture:**
- Non-blocking HTTP triggers (Azure Functions Consumption Plan)
- Client-side polling for long-running queries
- Cosmos DB as state machine for conversation tracking

---

## 🔬 Data Engineering Highlights

### 1. **ETL Pipeline** (`data/Notebooks/01_Load/`)

**Data Ingestion:**
- Source: IMDb TSV datasets (public dataset)
- Volume: ~100M+ records across 4 core tables
- Format: Delta Lake (Parquet + transaction log)
- Storage: Azure Data Lake Storage Gen2

**Key Techniques:**
```python
# Delta Lake optimization
spark.sql("OPTIMIZE imdb.principals_delta ZORDER BY (tconst)")
spark.sql("ANALYZE TABLE imdb.principals_delta COMPUTE STATISTICS")

# Partition strategy for time-series queries
.write.partitionBy("startYear") \
      .format("delta") \
      .mode("overwrite") \
      .save("path")
```

### 2. **Query Optimization Strategies**

**Problem:** Complex multi-table joins on 100M+ rows = expensive shuffles

**Solution:** Pre-computed materialized views

```sql
-- Instead of manual 3-way join (expensive):
SELECT m.primaryTitle, p.primaryName 
FROM principals_delta pr 
  JOIN movies_delta m ON pr.tconst = m.tconst 
  JOIN persons_delta p ON pr.nconst = p.nconst

-- Use pre-optimized view (10x faster):
SELECT primaryTitle, primaryName 
FROM movie_cast 
WHERE category='actor' LIMIT 100
```

**Performance Gains:**
- Broadcast joins for dimension tables (<10M rows)
- Predicate pushdown with Delta stats
- Partition pruning on indexed columns
- Early aggregation before joins

### 3. **AI-Powered Data Transformations** (`data/Notebooks/02_Integration/`)

**Distributed AI UDF:**
```python
# Azure OpenAI as Spark UDF
@udf(returnType=StringType())
def ai_movie_summary(title: str) -> str:
    return azure_openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Summarize: {title}"}]
    ).choices[0].message.content

# Parallel execution across Spark cluster
df.withColumn("ai_description", ai_movie_summary(col("primaryTitle")))
```

**Benefits:**
- Scales horizontally (each executor calls OpenAI in parallel)
- Enables semantic enrichment at data layer
- Cached results in Delta Lake (no re-computation)

---

## 🤖 LLM Orchestration Layer

### Tool-Based Function Calling

The LLM acts as a **query planner**, not a data processor:

```python
# LLM receives tool definition
SPARK_SQL_TOOL = {
    "name": "execute_spark_sql",
    "description": "Execute Spark SQL against IMDb Delta Lake...",
    "parameters": {
        "sql_query": "string",
        "reasoning": "string"  # Forces LLM to explain query strategy
    }
}

# LLM generates optimized query
User: "Top 5 highest rated movies from 2020?"

LLM Decision: 
  Tool: execute_spark_sql
  SQL: SELECT m.primaryTitle, r.averageRating 
       FROM movies_with_ratings m  -- uses pre-joined view!
       WHERE m.startYear = 2020 
       ORDER BY r.averageRating DESC 
       LIMIT 5
  Reasoning: "Using pre-joined view to avoid manual join overhead..."
```

### Why This Approach?

✅ **Scalability:** LLM orchestrates, Spark processes (no 2MB token limits)  
✅ **Cost:** Only LLM API calls for planning (~500 tokens), not data transfer  
✅ **Accuracy:** SQL runs on actual data, not LLM "hallucinations"  
✅ **Performance:** Near-data processing (Databricks processes in-place)

---

## 📊 Dataset

### IMDb Non-Commercial Dataset

**Source:** [IMDb Datasets](https://datasets.imdbws.com/) (public)

**Tables:**

| Table | Rows | Description | Key Columns |
|-------|------|-------------|-------------|
| `principals_delta` | ~100M | Cast & crew relationships | tconst, nconst, category, job |
| `persons_delta` | ~10M | Actor/director metadata | nconst, primaryName, birthYear |
| `movies_delta` | ~15M | Movie/TV metadata | tconst, primaryTitle, startYear, genres |
| `ratings_delta` | ~10M | User ratings | tconst, averageRating, numVotes |

**Data Volume:** ~25GB raw, ~18GB optimized (Delta compression)

**Schema Design:**
- Partition key: `tconst` (title ID) for join optimization
- Composite partition key: `startYear` + `tconst` for time-series queries
- Array columns: `genres[]`, `knownForTitles[]` (native Spark array type)

---

## 🚀 Technical Stack

### **Data Engineering:**
- **Azure Databricks** (Spark 3.5, Runtime 17.3 LTS)
- **Delta Lake** (ACID transactions, time travel, Z-ordering)
- **Apache Spark SQL** (distributed query engine)
- **Azure Data Lake Storage Gen2** (hierarchical namespace)

### **AI/ML:**
- **Azure OpenAI** (GPT-4o with Function Calling API)
- **LangChain patterns** (tool calling, async execution)
- **Semantic embeddings** (for future RAG implementation)

### **Backend:**
- **Azure Functions** (Python 3.11, Consumption Plan)
- **Azure Cosmos DB** (NoSQL, partitioned by conversation ID)
- **Databricks Jobs API** (async SQL execution)

### **Frontend:**
- **Vanilla JavaScript** (no frameworks - instant deploy)
- **Azure Static Web Apps** (global CDN)

---

## 📁 Project Structure

```
├── BE/                          # Backend (Azure Functions)
│   ├── function_app.py          # HTTP triggers (chat endpoints)
│   ├── llm_orchestrator.py      # LLM + tool calling logic
│   ├── cosmos_storage.py        # Conversation state management
│   ├── databricks_client.py     # Jobs API integration
│   ├── requirements.txt         # Python dependencies
│   └── API_DOCUMENTATION.md     # REST API specs
│
├── FE/                          # Frontend (Static Web App)
│   ├── index.html               # Single-page application
│   ├── js/
│   │   ├── config.js            # API endpoints, polling config
│   │   ├── api.js               # HTTP client
│   │   ├── chat.js              # Polling logic
│   │   └── ui.js                # DOM manipulation
│   └── staticwebapp.config.json # SWA routing rules
│
├── data/                        # Databricks notebooks
│   ├── Notebooks/
│   │   ├── 01_Load/             # ETL pipeline
│   │   │   ├── 01_configs.py    # Storage config
│   │   │   ├── 02_read.py       # Ingest TSV → DataFrame
│   │   │   └── 03_save.py       # Write Delta Lake
│   │   └── 02_Integration/      # AI integrations
│   │       ├── 01_config.py     # OpenAI UDF setup
│   │       └── 02_execute.py    # Distributed AI transformations
│
└── README.md                    # This file
```

---

## 🎓 Learning Outcomes

This project demonstrates proficiency in:

### **Data Engineering:**
- [x] Design and implement ETL pipelines for large-scale data
- [x] Optimize Spark SQL queries (broadcast joins, partition pruning)
- [x] Use Delta Lake for ACID transactions and schema evolution
- [x] Create materialized views for performance optimization
- [x] Implement cost-effective storage strategies (partitioning, Z-ordering)

### **AI/ML Integration:**
- [x] Integrate LLMs into data workflows (tool calling patterns)
- [x] Build AI-powered UDFs for distributed processing
- [x] Design AI-near-data architectures (minimize data movement)
- [x] Implement prompt engineering for SQL generation

### **Cloud Architecture:**
- [x] Design serverless applications (Azure Functions, consumption plans)
- [x] Implement async patterns (polling, state machines)
- [x] Use managed services (Cosmos DB, Databricks, OpenAI)
- [x] Apply cost optimization strategies (TTL, auto-scaling)

### **Production Practices:**
- [x] Error handling and retry logic
- [x] Logging and observability patterns
- [x] API design (REST, polling, async)
- [x] Documentation and code organization

---

## 🔧 Deployment

### **Prerequisites:**
- Azure subscription
- Databricks workspace
- Azure OpenAI service deployment (GPT-4o)
- Azure Storage Account (ADLS Gen2)

### **Quick Start:**

1. **Deploy Data Layer (Databricks):**
   ```bash
   # Run notebooks in order:
   data/Notebooks/01_Load/01_configs.py   # Configure storage
   data/Notebooks/01_Load/02_read.py      # Ingest data
   data/Notebooks/01_Load/03_save.py      # Create Delta tables
   ```

2. **Deploy Backend (Azure Functions):**
   ```bash
   cd BE/
   func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
   ```

3. **Deploy Frontend (Static Web App):**
   ```bash
   cd FE/
   az staticwebapp create \
     --name imdb-chat-frontend \
     --resource-group <YOUR_RG> \
     --location "West Europe"
   ```

### **Configuration:**

Set environment variables in Azure Function App:
```bash
DATABRICKS_HOST=https://adb-xxxx.xx.azuredatabricks.net
DATABRICKS_TOKEN=<your_token>
DATABRICKS_JOB_ID=<job_id>
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_KEY=<your_key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
COSMOS_ENDPOINT=https://xxx.documents.azure.com:443/
COSMOS_KEY=<your_key>
```

---

## � Cost Optimization

### **Architecture Benefits:**
- **Databricks:** Job-based pricing (pay only when running, auto-shutdown after 15 min idle)
- **Azure Functions:** Consumption plan (~0.5M free requests/month)
- **Cosmos DB:** Serverless mode (pay per request, auto-scales to zero)
- **Storage:** ~$2/month for 25GB Delta Lake tables (LRS)
- **OpenAI:** Pay-per-token model (efficient with tool calling)

### **Cost-Saving Strategies:**
- Async polling pattern (no long-running compute)
- Pre-optimized views (reduce query execution time)
- TTL in Cosmos DB (automatic data cleanup)
- Broadcast joins (minimize shuffle overhead)
- Delta Z-ordering (reduce data scanned)

---

## 🎬 Example Queries

```
User: "Show me the top 5 highest rated movies from 2020"

LLM Generated SQL:
SELECT m.primaryTitle, m.averageRating, m.numVotes
FROM imdb.movies_with_ratings m
WHERE m.startYear = 2020 
  AND m.titleType = 'movie'
ORDER BY m.averageRating DESC
LIMIT 5

Results: Hamilton, Da 5 Bloods, Palm Springs, Tenet, Soul
```

```
User: "Find directors who worked with Tom Hanks"

LLM Generated SQL:
WITH hanks_movies AS (
  SELECT DISTINCT tconst 
  FROM imdb.movie_cast 
  WHERE primaryName = 'Tom Hanks'
)
SELECT DISTINCT mc.primaryName, COUNT(*) as collaborations
FROM imdb.movie_cast mc
JOIN hanks_movies hm ON mc.tconst = hm.tconst
WHERE mc.category = 'director'
GROUP BY mc.primaryName
ORDER BY collaborations DESC

Results: Steven Spielberg (5), Robert Zemeckis (3), ...
```

---

## 🔒 Security & Risk Considerations

### **Implemented:**
- ✅ Managed identities for service-to-service auth (where possible)
- ✅ Key Vault for secrets (Databricks token, storage keys)
- ✅ CORS configuration for API
- ✅ SQL injection prevention (parameterized queries)
- ✅ Read-only SQL execution (no DDL/DML allowed)
- ✅ **Automatic LIMIT injection** in Databricks notebook (prevents unbounded AI UDF calls)

### **Residual Risks (AI UDF Cost Management):**

⚠️ **Cost Risk: AI Function Usage**  
Even with automatic LIMIT enforcement, AI UDFs (`ai_movie_summary()`) can generate unexpected costs:

**Scenarios:**
1. **High LIMIT values:** LLM generates `LIMIT 1000` → 1000 OpenAI API calls per query
2. **Multiple users:** 10 concurrent users × 500 rows = 5000 API calls/minute
3. **Repeated queries:** User refreshes or retries → duplicate API calls (no caching)
4. **Token costs:** Complex movie summaries may use 200-500 tokens per call

**Example Cost Calculation:**
```
Query: SELECT ai_movie_summary(title) FROM movies WHERE year=2020 LIMIT 500
Cost per call: ~$0.002 (GPT-4o input + output tokens)
Total cost: 500 calls × $0.002 = $1.00 per query
Daily exposure (100 queries): $100/day
```

**Additional Mitigations for Production:**
- 🔄 **Smart LIMIT caps:** Set max 50-100 for queries with AI UDFs (detect in query plan)
- 🔄 **Result caching:** Cache AI-generated summaries in Delta Lake (avoid re-computation)
- 🔄 **Rate limiting:** Throttle AI UDF queries per user/device (e.g., 10/hour)
- 🔄 **Cost monitoring:** Azure Monitor alerts on OpenAI spend thresholds
- 🔄 **Prompt optimization:** Use shorter system prompts to reduce token usage

### **Future Enhancements:**
- 🔄 Azure AD authentication for frontend
- 🔄 Rate limiting per user/IP
- 🔄 Query cost estimation before execution
- 🔄 Data access policies (row-level security)
- 🔄 API key rotation automation

---

## 📄 License

This project is for educational purposes as part of EPAM onboarding laboratory work.  
IMDb dataset is used under [IMDb Non-Commercial Licensing](https://developer.imdb.com/non-commercial-datasets/).

---

**Last Updated:** December 2025
