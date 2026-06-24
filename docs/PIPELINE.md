# The 8-Stage AI Pipeline

This document provides a detailed breakdown of each stage in the Q&A pipeline, including instrumentation patterns, costs, and performance characteristics.

## Pipeline Overview

The pipeline processes questions through eight stages, with automatic quality gates and iterative refinement:

```
[1] Embedding → [2] Retrieval → [3] Generation → [4] Claims → 
[5] Verification → [6] Accuracy → [7] Evaluation → [8] Quality Gate
                                                         ↓
                                                    (iterate if needed)
```

The stage logic below lives in [`backend/pipeline/`](../backend/pipeline/) and is unchanged.
In production it executes as a **Render Workflows** run: the `run_qa_pipeline` orchestrator
([`workflows/app.py`](../workflows/app.py)) keeps the cheap stages (1, 2, 8) in-process and
promotes the heavy LLM stages (3, 4, 5) to their own retried subtasks, with stages 6 + 7
running as three concurrent subtasks on separate instances. See the
[Architecture section of the README](../README.md#architecture) for the topology.

---

## Stage 1: Question Embedding

**Purpose:** Convert natural language question to vector representation

**Model:** OpenAI `text-embedding-3-small`

**Cost:** ~$0.002 per question

**Instrumentation:**

```python
@logfire.instrument("embed_question")
async def embed_question(text: str) -> List[float]:
    with logfire.span("openai_embedding") as span:
        span.set_attribute("text_length", len(text))
        embedding = await openai.embeddings.create(...)
        span.set_attribute("cost_usd", calculate_cost(...))
        return embedding
```

**Key Metrics:**
- Average latency: ~100ms
- Cost per embedding: $0.0002
- Embedding dimensions: 1536

---

## Stage 2: RAG Document Retrieval (Hybrid Search)

**Purpose:** Find relevant documentation chunks using hybrid search

**Database:** PostgreSQL with pgvector extension + full-text search

**Method:** Hybrid Search combining semantic (vector) + lexical (BM25) search

**Ranking:** Reciprocal Rank Fusion (RRF) to merge results

### Why Hybrid Search?

Pure semantic search can miss documents with specific keywords (e.g., "15 minutes", "port 3000"). Hybrid search combines:

- **Semantic search (60%)** - Understanding intent and context
- **BM25 lexical search (40%)** - Exact keyword and phrase matching

### How it Works

1. Run vector similarity search (pgvector) for semantic matches
2. Run full-text search (PostgreSQL `tsvector`) for keyword matches
3. Combine rankings using RRF: `score = 1/(k + rank)` where k=60
4. Return top documents sorted by combined score

### Instrumentation

```python
@logfire.instrument("rag_retrieval")
async def retrieve_documents(embedding: List[float], query_text: str) -> List[Document]:
    with logfire.span("hybrid_search") as span:
        docs = await vectorstore.hybrid_search(
            query_text=query_text,
            query_embedding=embedding,
            k=10,
            bm25_weight=0.4  # 60% semantic, 40% BM25
        )
        span.set_attribute("docs_found", len(docs))
        span.set_attribute("semantic_count", semantic_results)
        span.set_attribute("bm25_count", bm25_results)
        return docs
```

**Performance:** Hybrid search increases retrieval accuracy by ~35% for queries with specific numbers, technical terms, or product names.

**Key Metrics:**
- Average latency: ~300ms
- Documents retrieved: 10 (configurable)
- Cost: ~$0.0001 per retrieval

For a technical deep-dive on hybrid search implementation, see [HYBRID_SEARCH.md](./HYBRID_SEARCH.md).

---

## Stage 3: Answer Generation

**Purpose:** Generate comprehensive answer using retrieved context

**Model:** Claude Sonnet 4.6

**Context:** RAG documents + conversation history

**Max Tokens:** 2000 (optimized for cost)

**Instrumentation:**

```python
@logfire.instrument("generate_answer")
async def generate_answer(question: str, context: str) -> dict:
    with logfire.span("claude_generation") as span:
        response = await anthropic.messages.create(...)
        span.set_attribute("input_tokens", response.usage.input_tokens)
        span.set_attribute("output_tokens", response.usage.output_tokens)
        span.set_attribute("cost_usd", calculate_anthropic_cost(...))
        return {"answer": response.content[0].text, "cost": cost}
```

**Key Metrics:**
- Average latency: ~2.1s
- Cost per generation: ~$0.045 (most expensive stage)
- Average output tokens: ~800

---

## Stage 4: Claims Extraction

**Purpose:** Extract verifiable factual claims from generated answer

**Model:** GPT-4o-mini (fast + cheap)

**Output:** JSON list of claims

**Example Claims:**
- "Render supports Node.js versions 14, 16, 18, and 20"
- "PostgreSQL databases include automated daily backups"
- "Static sites deploy automatically on git push"

**Key Metrics:**
- Average latency: ~400ms
- Cost per extraction: ~$0.008
- Average claims per answer: 5-8

---

## Stage 5: Claims Verification

**Purpose:** Verify each claim against documentation

**Method:** RAG search for each claim's embedding

**Threshold:** 0.85 similarity score

**Output:** Verified vs unverified claims

**Key Metrics:**
- Average latency: ~500ms
- Cost per verification: ~$0.0015
- Verification accuracy: ~92%

---

## Stage 6: Technical Accuracy Check

**Purpose:** Deep accuracy validation using Claude

**Model:** Claude Sonnet 4.6

**Input:** Original answer + claims + verification results

**Output:** Accuracy score (0-100) + corrections needed

**Key Metrics:**
- Average latency: ~600ms
- Cost per check: ~$0.018
- Average accuracy score: 89/100

---

## Stage 7: Quality Rating (Dual-Model Evaluation)

**Purpose:** Independent quality assessment from two models

**Models:** OpenAI GPT-4o-mini + Anthropic Claude Sonnet 4.6

**Criteria:**
- Technical accuracy (30%)
- Clarity & organization (25%)
- Completeness (25%)
- Developer value (20%)

**Output:**

```json
{
  "openai_score": 92,
  "anthropic_score": 88,
  "average_score": 90,
  "agreement_level": "high",
  "feedback": "..."
}
```

**Key Metrics:**
- Average latency: ~300ms
- Cost per evaluation: ~$0.007
- Inter-rater agreement: 77% (within 10 points)

---

## Stage 8: Quality Gate

**Purpose:** Decide whether to return or iterate

**Logic:**

```python
if average_score >= quality_threshold and iteration < max_iterations:
    return answer
else:
    # Regenerate with feedback from evaluators
    feedback = merge_evaluator_feedback()
    iteration += 1
    goto Stage 3  # with feedback
```

**Configuration:**
- Max iterations: 3 (configurable)
- Quality threshold: 85 (configurable)
- Success rate: ~88% pass on first iteration

---

## Performance Metrics

### Cost Breakdown (per question)

```
┌────────────────────────────────┬──────────┬──────────┐
│ Stage                          │ Cost     │ % Total  │
├────────────────────────────────┼──────────┼──────────┤
│ Question Embedding             │ $0.0002  │    2%    │
│ RAG Retrieval                  │ $0.0001  │    1%    │
│ Answer Generation (Claude)     │ $0.0450  │   56%    │ ← Most expensive
│ Claims Extraction (GPT)        │ $0.0080  │   10%    │
│ Claims Verification (RAG)      │ $0.0015  │    2%    │
│ Accuracy Check (Claude)        │ $0.0180  │   22%    │
│ Quality Rating (Dual)          │ $0.0070  │    9%    │
├────────────────────────────────┼──────────┼──────────┤
│ TOTAL (first iteration)        │ $0.0798  │  100%    │
│ TOTAL (if 2 iterations)        │ $0.1346  │          │
└────────────────────────────────┴──────────┴──────────┘
```

### Response Time Metrics

- **Average Response Time:** 4.2 seconds (first iteration)
- **P95 Response Time:** 8.7 seconds
- **P99 Response Time:** 12.3 seconds
- **Iteration Rate:** 12% of questions require refinement

### Quality Scores

- **Average Quality Score:** 89/100
- **OpenAI Average:** 87/100
- **Anthropic Average:** 91/100
- **Agreement Rate:** 77% (within 10 points)

### Question Patterns

```
Deployment questions:  35% of traffic, 92% first-try success
Database questions:    28% of traffic, 78% first-try success  ← Higher iteration rate
Configuration:         20% of traffic, 88% first-try success
Pricing/Plans:         10% of traffic, 95% first-try success
Other:                  7% of traffic, 82% first-try success
```

---

## Optimization Tips

### Reducing Costs

1. **Lower MAX_TOKENS** - Reduce output token limit for generation
2. **Use smaller models** - Consider GPT-4o-mini for less critical stages
3. **Cache frequent questions** - Store common Q&A pairs
4. **Adjust quality threshold** - Lower threshold to reduce iterations

### Improving Quality

1. **Improve RAG context** - Add more documentation, refine chunking
2. **Tune prompts** - Iterate on generation and evaluation prompts
3. **Increase MAX_TOKENS** - Allow more detailed answers for complex questions
4. **Add examples** - Few-shot examples in prompts

### Reducing Latency

1. **Parallelize stages** - Run independent evaluators concurrently
2. **Optimize retrieval** - Fine-tune hybrid search weights and top-k
3. **Use streaming** - Stream responses to users as they're generated
4. **Cache embeddings** - Store question embeddings for common queries

---

## Related Documentation

- [Observability Guide](./OBSERVABILITY.md) - Detailed instrumentation patterns
- [Configuration Guide](./CONFIGURATION.md) - All configuration options
- [Hybrid Search Deep-Dive](./HYBRID_SEARCH.md) - Technical implementation details

