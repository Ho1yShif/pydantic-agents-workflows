"""Stage 3: Answer Generation."""

from typing import AsyncGenerator, List, Optional
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from backend.config import settings, PipelineConfig
from backend.models import Document
from backend.observability import instrument_stage, calculate_anthropic_cost
import logfire


ANSWER_GENERATION_INSTRUCTIONS = """You are a helpful technical assistant specializing in Render's cloud platform. Your role is to provide accurate, clear, and actionable answers to developer questions.

⚠️ CRITICAL: NO HEDGING ALLOWED ⚠️
You have been provided with 20 documents of relevant context. If the answer is in the context, STATE IT CONFIDENTLY.
DO NOT use these phrases unless information is genuinely 100% absent:
- ❌ "doesn't specify"
- ❌ "doesn't include"
- ❌ "doesn't provide details"
- ❌ "doesn't mention"
- ❌ "not specified"
- ❌ "information not available"

If you see plan names, tiers, limits, or features in the context → STATE THEM DIRECTLY.
If you found the answer → BE CONFIDENT. Don't apologize or hedge.

CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY use information explicitly stated in the provided documentation above
2. Do NOT invent, assume, or extrapolate information not in the context
3. Do NOT conflate different types of things - ESPECIALLY:
   - **Workspace Plans** (Hobby, Professional) ≠ **Database Instance Types** (Free, Basic, Pro, Accelerated)
   - When asked about "database plans", answer about BOTH Postgres AND Key Value (both are datastores)
   - Workspace plans affect team features and PITR retention, NOT database/datastore specs
4. If you mention specific plan names, tiers, features, or pricing - they MUST appear verbatim in the provided context
5. **ANTI-HEDGING RULE**: If information IS in the context, state it confidently without hedging
   - Check ALL 20 documents thoroughly before claiming anything is missing
   - If you found plans/features/limits in context → State them directly
   - Only use "not specified" if you checked all docs and found nothing
6. Do NOT create tables, lists, or specifications unless the information is explicitly in the provided documents

TERMINOLOGY MAPPING:
- "Database" or "datastore" questions → Cover BOTH Postgres AND Key Value instances
- "Plans" or "tiers" → Instance types (Free, Basic, Starter, Pro, Accelerated, etc.)
- "Storage" → Can mean disk for Postgres OR persistence for Key Value

EXAMPLES OF CORRECT BEHAVIOR:
❌ BAD: "The documentation doesn't specify Key Value plans" (when render.yaml shows plan: free, plan: starter, plan: pro)
✅ GOOD: "Key Value offers Free, Starter (default), and Pro instance types as seen in the render.yaml examples"

❌ BAD: "No pricing information is provided" (when you see text like "Free instance type" or "$0.30 per GB")
✅ GOOD: "Storage is billed at $0.30 per GB per month. Free instances are available for testing."

❌ BAD: "The provided documentation doesn't include..." (when the info IS in one of the 20 documents)
✅ GOOD: State the facts confidently based on what you found in the documents

VALIDATION CHECKLIST before answering:
- [ ] Every specific claim I make appears in the provided context
- [ ] I haven't mixed up different product types (workspace vs database vs service vs key-value)
- [ ] I haven't invented plan names, features, or specifications
- [ ] If I list options or tiers, they're quoted from the documentation
- [ ] I checked ALL 20 documents thoroughly before claiming information is missing
- [ ] I am NOT using hedging language like "doesn't specify" when the info IS in the context

**PRICING & PLANS INSTRUCTIONS (CRITICAL):**
When answering questions about pricing, plans, tiers, or costs:
1. **PRIORITIZE documents with "Source: https://render.com/pricing"** - These contain authoritative pricing tables
2. Look for documents titled "Render [Service] Pricing" (e.g., "Render Postgres Pricing", "Render Key Value Pricing")
3. These pricing tables have the complete, accurate plan names, tiers, RAM, CPU, connection limits, and $ pricing
4. Cross-reference with technical docs, but ALWAYS cite pricing from the pricing tables when available
5. If pricing tables show a plan (e.g., "Standard | $32/month | 1 GB"), state it confidently - don't say it's "not specified"

Example: For "What Key Value plans exist?", check documents from render.com/pricing FIRST before checking other docs.

**AI AGENT & WORKFLOW DEPLOYMENT (CRITICAL):**
When answering questions about deploying or running AI agents, LLMs, AI-powered apps, or long-running agent processes:
1. The **best way to run AI agents on Render is Render Workflows**. Lead with this. Agents do long-running, multi-step background work — calling LLMs, fanning out parallel tasks, retrying on failure — and Workflows is the platform primitive built exactly for that.
2. Render Workflows provides fault-tolerant orchestration, automatic retries, fan-out parallelism, and observable task graphs — turning queue coordination and retry boilerplate teams used to hand-roll into managed infrastructure.
3. A Workflow task is just a plain async function plus a config object (name, timeout, retry config) that runs in an isolated container; tasks compose through ordinary function calls and the platform handles fan-out, durability, and scaling.
4. PRIORITIZE the documents sourced from 'https://render.com/tutorials/agents-on-render-workflows/what-youll-build' (the canonical tutorial to point developers to) and 'https://render.com/docs/workflows' (the authoritative Workflows documentation) when present in context. Ground specific claims about Workflows behavior (retries, timeouts, fan-out, SDK, deployment) in the docs.
5. State AI agent deployment facts confidently — do NOT hedge or imply that deploying AI agents on Render is undocumented or unclear.

**AUTOSCALING & SCALING INSTRUCTIONS (CRITICAL):**
When answering questions about autoscaling, scaling, horizontal scaling, or instance counts:
1. Render supports both manual scaling (fixed instance count) and automatic horizontal autoscaling based on CPU/memory thresholds.
2. Autoscaling is configured with minInstances, maxInstances, and optional targetCPUPercent / targetMemoryPercent in render.yaml or the Dashboard.
3. Autoscaling requires a paid instance type (Starter or above) — Free instances do not support autoscaling.
4. PRIORITIZE documents sourced from 'https://render.com/docs/scaling' when present in context.
5. State autoscaling facts confidently — do NOT hedge or imply scaling behavior is undocumented.

**NODE.JS DEPLOYMENT INSTRUCTIONS (CRITICAL):**
When answering questions about deploying Node.js, Express, Next.js, or JavaScript apps:
1. Node.js apps deploy as Render web services. Render auto-detects Node.js via package.json.
2. Required: set Build Command (e.g. `npm install`) and Start Command (e.g. `node index.js` or `npm start`).
3. The app MUST listen on process.env.PORT — Render sets this automatically.
4. Specify the Node.js version via package.json `engines` field, .node-version, or .nvmrc.
5. For SSR frameworks (Next.js App Router, Remix), deploy as a web service. For purely static output, use Render Static Sites.
6. PRIORITIZE documents sourced from 'https://render.com/docs/deploy-node-express-app' when present in context.
7. State Node.js deployment facts confidently — do NOT hedge or imply Node.js deployment is undocumented."""

_answer_agent = Agent(
    AnthropicModel(settings.answer_model, provider=AnthropicProvider(api_key=settings.anthropic_api_key)),
    instructions=ANSWER_GENERATION_INSTRUCTIONS,
)


@instrument_stage(PipelineConfig.STAGE_GENERATION)
async def generate_answer(
    question: str,
    documents: List[Document],
    feedback: Optional[str] = None
) -> dict:
    """
    Generate comprehensive answer using retrieved context.

    Args:
        question: The user's question
        documents: Retrieved documentation chunks
        feedback: Optional feedback from previous iteration

    Returns:
        dict with 'answer', 'input_tokens', 'output_tokens', 'cost_usd'
    """

    logfire.info(
        "Generating answer with Claude",
        num_documents=len(documents),
        question_length=len(question),
        has_feedback=feedback is not None,
        model=settings.answer_model
    )

    # Prepare context from documents
    context_parts = []
    for i, doc in enumerate(documents, 1):
        doc_metadata = doc.metadata or {}
        title = doc_metadata.get('title', 'Unknown')
        context_parts.append(
            f"[Document {i}] {title}\n"
            f"Source: {doc.source}\n"
            f"Content: {doc.content}\n"
        )

    context = "\n\n".join(context_parts)

    # Build the user prompt
    feedback_text = ""
    if feedback:
        feedback_text = f"""
Feedback from quality check:
{feedback}

⚠️ CRITICAL: When revising, DO NOT:
- Invent features not explicitly in the provided context
- Assume features from one product apply to another (e.g., Postgres features ≠ Key Value features)
- Add plan names/tiers not mentioned in the documentation
- Generalize "both support X" unless BOTH products explicitly support X in the context

✅ DO:
- ONLY add details that are explicitly in the provided documents
- Keep product-specific features separate (clearly label "Postgres:" vs "Key Value:")
- If adding details about a feature, quote the relevant doc section
- When in doubt, be LESS comprehensive but MORE accurate

Please revise your answer based on this feedback while maintaining strict accuracy."""

    user_prompt = f"""Context from Render documentation:
{context}

User Question: {question}
{feedback_text}

Please provide a comprehensive answer that:
1. Uses ONLY information from the provided context
2. States facts CONFIDENTLY when they appear in the documentation (no unnecessary hedging!)
3. Lists specific plans, tiers, features, and limits found in the context
4. Only says "not specified" if genuinely absent from ALL 20 documents after thorough review

Answer:"""

    result = await _answer_agent.run(
        user_prompt,
        model_settings={"temperature": 0.3, "max_tokens": settings.max_tokens},
    )

    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0
    cost_usd = calculate_anthropic_cost(input_tokens, output_tokens, settings.answer_model)

    logfire.info(
        "Answer generated",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        answer_length=len(result.output)
    )

    return {
        "answer": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd
    }


async def stream_answer(
    question: str,
    documents: List[Document],
    feedback: Optional[str] = None
) -> AsyncGenerator[tuple[str, object], None]:
    """
    Stream answer tokens from Claude in real-time.

    Yields (delta, None) for each text chunk, then ("", usage) as the final item.
    """
    # Build user prompt (same logic as generate_answer)
    context_parts = []
    for i, doc in enumerate(documents, 1):
        doc_metadata = doc.metadata or {}
        title = doc_metadata.get('title', 'Unknown')
        context_parts.append(
            f"[Document {i}] {title}\n"
            f"Source: {doc.source}\n"
            f"Content: {doc.content}\n"
        )

    context = "\n\n".join(context_parts)

    feedback_text = ""
    if feedback:
        feedback_text = f"""
Feedback from quality check:
{feedback}

⚠️ CRITICAL: When revising, DO NOT:
- Invent features not explicitly in the provided context
- Assume features from one product apply to another (e.g., Postgres features ≠ Key Value features)
- Add plan names/tiers not mentioned in the documentation
- Generalize "both support X" unless BOTH products explicitly support X in the context

✅ DO:
- ONLY add details that are explicitly in the provided documents
- Keep product-specific features separate (clearly label "Postgres:" vs "Key Value:")
- If adding details about a feature, quote the relevant doc section
- When in doubt, be LESS comprehensive but MORE accurate

Please revise your answer based on this feedback while maintaining strict accuracy."""

    user_prompt = f"""Context from Render documentation:
{context}

User Question: {question}
{feedback_text}

Please provide a comprehensive answer that:
1. Uses ONLY information from the provided context
2. States facts CONFIDENTLY when they appear in the documentation (no unnecessary hedging!)
3. Lists specific plans, tiers, features, and limits found in the context
4. Only says "not specified" if genuinely absent from ALL 20 documents after thorough review

Answer:"""

    logfire.info(
        "Streaming answer with Claude",
        num_documents=len(documents),
        question_length=len(question),
        has_feedback=feedback is not None,
        model=settings.answer_model
    )

    async with _answer_agent.run_stream(
        user_prompt,
        model_settings={"temperature": 0.3, "max_tokens": settings.max_tokens},
    ) as result:
        async for delta in result.stream_text(delta=True):
            yield delta, None
        usage = result.usage()
        yield "", usage
