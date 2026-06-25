# Observability with Logfire

This guide demonstrates comprehensive observability patterns for AI pipelines using Logfire. Every component is instrumented to provide deep insights into performance, costs, and quality.

## Table of Contents

- [Auto-Instrumentation](#auto-instrumentation)
- [Custom Instrumentation](#custom-instrumentation)
- [Structured Logging](#structured-logging)
- [Distributed Tracing](#distributed-tracing)
- [SQL Queries](#sql-queries)
- [Dashboards](#dashboards)
- [Alerts](#alerts)

---

## Auto-Instrumentation

Logfire automatically captures detailed telemetry from popular frameworks and libraries.

### Setup

```python
# Enable auto-instrumentation in observability.py
import logfire

logfire.instrument_openai()        # All OpenAI API calls
logfire.instrument_anthropic()     # All Anthropic API calls
logfire.instrument_asyncpg()       # All database queries
logfire.instrument_httpx()         # All HTTP client requests
logfire.instrument_fastapi(app)    # All FastAPI endpoints
```

> **Note:** Anthropic instrumentation includes graceful error handling for version compatibility. Even if auto-instrumentation fails, Anthropic API calls will still work normally.

### What You Get Automatically

- **Request/response bodies and headers** - Full HTTP request/response data
- **Token counts and costs** - Automatic cost calculation for LLM calls
- **SQL query text and execution time** - Database performance monitoring
- **HTTP status codes and latencies** - API performance tracking
- **Error traces with full context** - Stack traces and error details

### Example: OpenAI Auto-Instrumentation

When you call OpenAI's API, Logfire automatically captures:

```python
# Your code
embedding = await openai.embeddings.create(
    model="text-embedding-3-small",
    input=question
)

# Logfire automatically tracks:
# - Request: model, input, parameters
# - Response: embedding vector, usage stats
# - Metadata: latency, cost, token count
# - Context: parent span, session ID, user info
```

---

## Custom Instrumentation

Beyond auto-instrumentation, add business-specific observability.

### Pipeline Stage Tracking

Use the `@logfire.instrument` decorator to track pipeline stages:

```python
@logfire.instrument("embed_question")
async def embed_question(text: str) -> List[float]:
    with logfire.span("openai_embedding") as span:
        span.set_attribute("text_length", len(text))
        span.set_attribute("model", "text-embedding-3-small")
        
        embedding = await openai.embeddings.create(...)
        
        span.set_attribute("cost_usd", calculate_cost(...))
        span.set_attribute("success", True)
        
        return embedding
```

### Session-Level Tracing

Track end-to-end user journeys:

```python
with logfire.span(
    "user_session.qa_request",
    session_id=session_id,
    question=question[:100],
    user_id=user_id
):
    # All pipeline stages become children of this span
    # Enables complete user journey tracking
    result = await execute_pipeline(question)
    
    logfire.info(
        "Session completed",
        total_cost_usd=result.cost,
        quality_score=result.quality_score,
        iterations=result.iterations
    )
```

### Custom Business Metrics

Track business-specific KPIs:

```python
# Track cost distribution
logfire.metric("pipeline.cost.total", value=cost_usd)
logfire.metric("pipeline.cost.by_stage", 
    value=stage_cost, 
    stage=stage_name
)

# Track quality scores
logfire.metric("pipeline.quality_score", value=score)
logfire.metric("pipeline.quality_score.by_category",
    value=score,
    category=question_category
)

# Track iteration patterns
logfire.metric("pipeline.iterations", value=iterations)
logfire.metric("pipeline.first_pass_rate",
    value=1 if iterations == 1 else 0
)
```

### Error Handling

Capture errors with context:

```python
try:
    result = await generate_answer(question, context)
except Exception as e:
    logfire.error(
        "Answer generation failed",
        error=str(e),
        error_type=type(e).__name__,
        question_length=len(question),
        context_length=len(context),
        attempt=attempt_number
    )
    raise
```

---

## Structured Logging

Rich attributes enable powerful queries and analysis.

### Best Practices

```python
# Good: Rich structured data
logfire.info(
    "Pipeline execution completed",
    question_length=len(question),
    total_cost_usd=total_cost,
    duration_ms=duration,
    quality_score=quality_score,
    iterations=iterations,
    passed_first_iteration=iterations == 1,
    session_id=session_id,
    stage_costs={
        "embedding": embedding_cost,
        "generation": generation_cost,
        "evaluation": eval_cost
    }
)

# Bad: Unstructured string
logfire.info(f"Pipeline completed in {duration}ms with score {quality_score}")
```

### Common Attributes

Track these attributes consistently across your pipeline:

- **Identifiers:** `session_id`, `request_id`, `user_id`
- **Timing:** `duration_ms`, `start_time`, `end_time`
- **Costs:** `cost_usd`, `total_cost_usd`, `cost_by_stage`
- **Quality:** `quality_score`, `accuracy_score`, `agreement_level`
- **Metadata:** `model_name`, `token_count`, `iteration_number`

---

## Distributed Tracing

Every request creates a trace hierarchy showing parent-child relationships.

### Example Trace

```
user_session.qa_request                    [4.2s, $0.08]
├── qa_pipeline                            [4.1s, $0.08]
│   ├── question_embedding                 [0.1s, $0.0002]
│   │   └── openai.embeddings.create      [0.09s, $0.0002]
│   ├── rag_retrieval                      [0.3s, $0.0001]
│   │   ├── hybrid_search                 [0.2s]
│   │   └── postgres.query                [0.18s]
│   ├── answer_generation                  [2.1s, $0.045]
│   │   └── anthropic.messages.create     [2.0s, $0.045]
│   ├── claims_extraction                  [0.4s, $0.008]
│   │   └── openai.chat.completions       [0.38s, $0.008]
│   ├── claims_verification                [0.5s, $0.0015]
│   ├── technical_accuracy                 [0.6s, $0.018]
│   │   └── anthropic.messages.create     [0.58s, $0.018]
│   ├── quality_evaluation                 [0.3s, $0.007]
│   └── quality_gate                       [0.01s, $0]
```

### What This Shows

- **Parent-child relationships** - How stages compose
- **Time spent in each stage** - Where time is spent
- **Cost attribution** - Where money is spent
- **Bottleneck identification** - Which stages are slow

---

## SQL Queries

Logfire stores all telemetry in a queryable database. Use SQL to analyze patterns.

### Find Expensive Requests

```sql
SELECT 
    session_id, 
    question_length, 
    total_cost_usd, 
    iterations
FROM logs
WHERE total_cost_usd > 0.10
ORDER BY total_cost_usd DESC
LIMIT 10;
```

### Identify Quality Issues

```sql
SELECT 
    DATE(timestamp), 
    AVG(quality_score), 
    COUNT(*)
FROM logs
WHERE event_type = 'Pipeline execution completed'
GROUP BY DATE(timestamp)
HAVING AVG(quality_score) < 85;
```

### Analyze Iteration Patterns

```sql
SELECT 
    iterations,
    COUNT(*) as request_count,
    AVG(quality_score) as avg_quality,
    AVG(total_cost_usd) as avg_cost
FROM logs
WHERE event_type = 'Pipeline execution completed'
GROUP BY iterations
ORDER BY iterations;
```

### Track Cost Efficiency

```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total_requests,
    SUM(total_cost_usd) as total_cost,
    AVG(total_cost_usd) as avg_cost_per_request,
    SUM(CASE WHEN iterations = 1 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as first_pass_rate
FROM logs
WHERE event_type = 'Pipeline execution completed'
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

### Monitor Performance Trends

```sql
SELECT 
    DATE(timestamp) as date,
    AVG(duration_ms) as avg_duration,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms) as p99_duration
FROM logs
WHERE event_type = 'Pipeline execution completed'
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

---

## Dashboards

Create custom dashboards to visualize key metrics.

### 1. Pipeline Overview Dashboard

**What it shows:**
- Real-time request volume
- Average response time
- Cost per request
- Success/failure rates
- Current iteration distribution

**SQL Query:**

```sql
SELECT 
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(*) as total_requests,
  AVG(duration_ms) as avg_duration,
  SUM(cost_usd) as total_cost,
  AVG(quality_score) as avg_quality
FROM pipeline_executions
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

### 2. Cost Analysis Dashboard

**What it shows:**
- Cost breakdown by stage
- Cost per question type
- Model comparison (OpenAI vs Anthropic)
- Cost trends over time
- Budget tracking

**SQL Query:**

```sql
SELECT 
  stage_name,
  COUNT(*) as executions,
  SUM(cost_usd) as total_cost,
  AVG(cost_usd) as avg_cost,
  SUM(cost_usd) / (SELECT SUM(cost_usd) FROM pipeline_stages) * 100 as pct_of_total
FROM pipeline_stages
WHERE DATE(timestamp) = CURRENT_DATE
GROUP BY stage_name
ORDER BY total_cost DESC;
```

### 3. Quality Metrics Dashboard

**What it shows:**
- Quality score distribution
- Evaluator agreement rates
- Iteration patterns
- Question type performance
- Failure analysis

**SQL Query:**

```sql
SELECT 
  question_category,
  COUNT(*) as questions,
  AVG(quality_score) as avg_score,
  AVG(openai_score - anthropic_score) as avg_disagreement,
  SUM(CASE WHEN iterations > 1 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as iteration_rate
FROM pipeline_executions
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY question_category
ORDER BY iteration_rate DESC;
```

---

## Alerts

Configure alerts to catch issues proactively.

### 1. High Cost Alert

**Trigger:** Cost per request > $0.15

**Action:** Investigate expensive queries

**SQL Query:**

```sql
SELECT COUNT(*) as high_cost_requests
FROM logs
WHERE 
    event_type = 'Pipeline execution completed'
    AND timestamp > NOW() - INTERVAL '1 hour'
    AND total_cost_usd > 0.15;
```

### 2. Low Quality Alert

**Trigger:** Quality score < 75 for > 10% of requests

**Action:** Review recent answers

**SQL Query:**

```sql
SELECT 
    COUNT(*) as total_requests,
    SUM(CASE WHEN quality_score < 75 THEN 1 ELSE 0 END) as low_quality_requests,
    SUM(CASE WHEN quality_score < 75 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as low_quality_pct
FROM logs
WHERE 
    event_type = 'Pipeline execution completed'
    AND timestamp > NOW() - INTERVAL '1 hour'
HAVING low_quality_pct > 10;
```

### 3. High Iteration Rate Alert

**Trigger:** Iteration rate > 25%

**Action:** Check RAG document quality

**SQL Query:**

```sql
SELECT 
    COUNT(*) as total_requests,
    SUM(CASE WHEN iterations > 1 THEN 1 ELSE 0 END) as multi_iteration_requests,
    SUM(CASE WHEN iterations > 1 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as iteration_rate
FROM logs
WHERE 
    event_type = 'Pipeline execution completed'
    AND timestamp > NOW() - INTERVAL '1 hour'
HAVING iteration_rate > 25;
```

### 4. Slow Response Alert

**Trigger:** P95 latency > 10 seconds

**Action:** Optimize slow stages

**SQL Query:**

```sql
SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration
FROM logs
WHERE 
    event_type = 'Pipeline execution completed'
    AND timestamp > NOW() - INTERVAL '1 hour'
HAVING p95_duration > 10000;
```

---

## Related Documentation

- [Pipeline Guide](./PIPELINE.md) - Detailed pipeline stages
- [Configuration Guide](./CONFIGURATION.md) - All configuration options
- [Logfire Documentation](https://docs.pydantic.dev/logfire/) - Official Logfire docs

