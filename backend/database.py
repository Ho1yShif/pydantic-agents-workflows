"""Database connection and pgvector operations."""

import asyncpg
from typing import Optional
import numpy as np
import json
from contextlib import asynccontextmanager

from backend.config import settings
from backend.models import Document, DocumentChunk
import logfire


class VectorStore:
    """PostgreSQL vector store with pgvector extension."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize the database connection pool and create tables."""
        
        logfire.info("Initializing database connection pool")
        
        self.pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        
        # Create tables and enable pgvector
        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create documents table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    section TEXT,
                    metadata JSONB DEFAULT '{}',
                    embedding vector(1536),
                    content_tsv tsvector,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index for vector similarity search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                ON documents USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
            
            # Create index for source lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS documents_source_idx 
                ON documents(source)
            """)
            
            # Create GIN index for full-text search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS documents_content_tsv_idx 
                ON documents USING gin(content_tsv)
            """)
            
            # Create trigger function for auto-updating tsvector
            await conn.execute("""
                CREATE OR REPLACE FUNCTION documents_tsvector_trigger() RETURNS trigger AS $$
                BEGIN
                    NEW.content_tsv := to_tsvector('english', 
                        coalesce(NEW.title, '') || ' ' || 
                        coalesce(NEW.section, '') || ' ' || 
                        coalesce(NEW.content, '')
                    );
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql;
            """)
            
            # Create trigger to auto-update tsvector on insert/update
            await conn.execute("""
                DROP TRIGGER IF EXISTS documents_tsvector_update ON documents;
                
                CREATE TRIGGER documents_tsvector_update 
                BEFORE INSERT OR UPDATE ON documents
                FOR EACH ROW 
                EXECUTE FUNCTION documents_tsvector_trigger();
            """)
            
            # Create sessions table for Q&A history
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_sessions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sources JSONB DEFAULT '[]',
                    claims JSONB DEFAULT '[]',
                    evaluations JSONB DEFAULT '[]',
                    quality_score FLOAT NOT NULL,
                    iterations INTEGER NOT NULL,
                    total_cost FLOAT NOT NULL,
                    total_duration_ms FLOAT NOT NULL,
                    trace_id TEXT,
                    stages JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index for recent sessions
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS qa_sessions_created_at_idx 
                ON qa_sessions(created_at DESC)
            """)
            
            # Create index for trace_id lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS qa_sessions_trace_id_idx 
                ON qa_sessions(trace_id)
            """)
        
        logfire.info("Database initialized successfully")
    
    async def close(self):
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
            logfire.info("Database connection pool closed")
    
    async def insert_document(
        self,
        content: str,
        source: str,
        title: str,
        embedding: list[float],
        section: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> int:
        """Insert a document with its embedding."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Convert metadata dict to JSON string for JSONB column
        metadata_json = json.dumps(metadata or {})
        
        # Convert embedding list to pgvector format string
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO documents (content, source, title, section, metadata, embedding)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::vector)
                RETURNING id
            """, content, source, title, section, metadata_json, embedding_str)
            
            return result['id']
    
    async def insert_documents_batch(
        self,
        documents: list[tuple[str, str, str, list[float], Optional[str], dict]]
    ) -> list[int]:
        """Insert multiple documents in a batch."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            # Use a transaction for batch insert
            async with conn.transaction():
                ids = []
                for content, source, title, embedding, section, metadata in documents:
                    # Convert metadata dict to JSON string for JSONB column
                    metadata_json = json.dumps(metadata or {})
                    
                    # Convert embedding list to pgvector format string
                    embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                    
                    result = await conn.fetchrow("""
                        INSERT INTO documents (content, source, title, section, metadata, embedding)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6::vector)
                        RETURNING id
                    """, content, source, title, section, metadata_json, embedding_str)
                    ids.append(result['id'])
                
                return ids
    
    async def similarity_search(
        self,
        query_embedding: list[float],
        k: int = 10,
        threshold: float = 0.0
    ) -> list[Document]:
        """Search for similar documents using cosine similarity."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Convert embedding list to pgvector format string
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    content,
                    source,
                    title,
                    section,
                    metadata,
                    1 - (embedding <=> $1::vector) as similarity_score
                FROM documents
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, embedding_str, threshold, k)
            
            documents = []
            for row in rows:
                # Parse metadata if it's a string
                metadata = row['metadata']
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                doc = Document(
                    content=row['content'],
                    source=row['source'],
                    similarity_score=float(row['similarity_score']),
                    metadata={
                        'title': row['title'],
                        'section': row['section'],
                        **(metadata or {})
                    }
                )
                documents.append(doc)
            
            return documents
    
    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        k: int = 10,
        threshold: float = 0.0,
        bm25_weight: float = 0.5
    ) -> list[Document]:
        """
        Hybrid search combining semantic (vector) and lexical (BM25) search.
        
        Uses Reciprocal Rank Fusion (RRF) to combine results from both methods.
        
        Args:
            query_text: The query text for BM25 search
            query_embedding: The query embedding for semantic search
            k: Number of final results to return
            threshold: Similarity threshold for semantic search
            bm25_weight: Weight for BM25 scores (0-1), semantic weight is (1 - bm25_weight)
            
        Returns:
            List of documents ranked by combined RRF score
        """
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Convert embedding list to pgvector format string
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Pass raw query text; plainto_tsquery handles tokenization and strips special chars
        tsquery = query_text
        
        async with self.pool.acquire() as conn:
            # Fetch more results from each method to ensure good coverage
            fetch_k = k * 3
            
            # 1. Semantic search results
            semantic_rows = await conn.fetch("""
                SELECT 
                    id,
                    content,
                    source,
                    title,
                    section,
                    metadata,
                    1 - (embedding <=> $1::vector) as similarity_score
                FROM documents
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, embedding_str, threshold, fetch_k)
            
            # 2. BM25 (full-text) search results
            bm25_rows = await conn.fetch("""
                SELECT 
                    id,
                    content,
                    source,
                    title,
                    section,
                    metadata,
                    ts_rank_cd(content_tsv, query) as bm25_score
                FROM documents, 
                     plainto_tsquery('english', $1) as query
                WHERE content_tsv @@ query
                ORDER BY bm25_score DESC
                LIMIT $2
            """, tsquery, fetch_k)
            
            logfire.debug(
                "Hybrid search results",
                semantic_count=len(semantic_rows),
                bm25_count=len(bm25_rows),
                query_text=query_text
            )
            
            # 3. Combine using Reciprocal Rank Fusion (RRF)
            # RRF formula: score = sum(1 / (k + rank)) for each method
            # k is usually set to 60
            rrf_k = 60
            doc_scores = {}  # doc_id -> (combined_score, doc_data)
            
            # Add semantic search rankings
            for rank, row in enumerate(semantic_rows, start=1):
                doc_id = row['id']
                semantic_rrf = 1.0 / (rrf_k + rank)
                
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = {
                        'semantic_rrf': 0.0,
                        'bm25_rrf': 0.0,
                        'row': row
                    }
                
                doc_scores[doc_id]['semantic_rrf'] = semantic_rrf
            
            # Add BM25 search rankings
            for rank, row in enumerate(bm25_rows, start=1):
                doc_id = row['id']
                bm25_rrf = 1.0 / (rrf_k + rank)
                
                if doc_id not in doc_scores:
                    # This doc was in BM25 but not semantic results
                    # Fetch the semantic score for it
                    semantic_row = await conn.fetchrow("""
                        SELECT 
                            id,
                            content,
                            source,
                            title,
                            section,
                            metadata,
                            1 - (embedding <=> $1::vector) as similarity_score
                        FROM documents
                        WHERE id = $2
                    """, embedding_str, doc_id)
                    
                    doc_scores[doc_id] = {
                        'semantic_rrf': 0.0,
                        'bm25_rrf': 0.0,
                        'row': semantic_row or row
                    }
                
                doc_scores[doc_id]['bm25_rrf'] = bm25_rrf
            
            # Combine scores with weights
            ranked_docs = []
            for doc_id, scores in doc_scores.items():
                # Weighted RRF combination
                combined_score = (
                    (1 - bm25_weight) * scores['semantic_rrf'] +
                    bm25_weight * scores['bm25_rrf']
                )
                
                ranked_docs.append((combined_score, scores['row']))
            
            # Sort by combined score (descending)
            ranked_docs.sort(key=lambda x: x[0], reverse=True)
            
            # Take top k and convert to Document objects
            documents = []
            for combined_score, row in ranked_docs[:k]:
                # Parse metadata if it's a string
                metadata = row['metadata']
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                # Use combined RRF score as similarity_score
                doc = Document(
                    content=row['content'],
                    source=row['source'],
                    similarity_score=float(combined_score),
                    metadata={
                        'title': row['title'],
                        'section': row['section'],
                        **(metadata or {})
                    }
                )
                documents.append(doc)
            
            logfire.info(
                "Hybrid search completed",
                final_count=len(documents),
                top_score=documents[0].similarity_score if documents else 0.0
            )
            
            return documents
    
    async def get_document_count(self) -> int:
        """Get the total number of documents in the database."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("SELECT COUNT(*) FROM documents")
            return result['count']
    
    async def delete_all_documents(self):
        """Delete all documents (useful for testing)."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM documents")
        
        logfire.info("All documents deleted")
    
    async def health_check(self) -> bool:
        """Check if database connection is healthy."""
        
        try:
            if not self.pool:
                return False
            
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            return True
        except Exception as e:
            logfire.error(f"Database health check failed: {e}")
            return False
    
    async def save_session(
        self,
        question: str,
        answer: str,
        sources: list,
        claims: list,
        evaluations: list,
        quality_score: float,
        iterations: int,
        total_cost: float,
        total_duration_ms: float,
        trace_id: Optional[str] = None,
        stages: Optional[list] = None
    ) -> str:
        """Save a Q&A session to the database."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Convert lists to JSON strings for JSONB columns
        sources_json = json.dumps(sources)
        claims_json = json.dumps(claims)
        evaluations_json = json.dumps(evaluations)
        stages_json = json.dumps(stages or [])
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO qa_sessions 
                (question, answer, sources, claims, evaluations, quality_score, 
                 iterations, total_cost, total_duration_ms, trace_id, stages)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10, $11::jsonb)
                RETURNING id
            """, question, answer, sources_json, claims_json, evaluations_json,
                quality_score, iterations, total_cost, total_duration_ms, trace_id, stages_json)
            
            session_id = str(result['id'])
            logfire.info(f"Saved Q&A session: {session_id}", trace_id=trace_id)
            return session_id
    
    async def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        """Get recent Q&A sessions."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id, question, answer, sources, claims, evaluations,
                    quality_score, iterations, total_cost, total_duration_ms,
                    created_at, trace_id, stages
                FROM qa_sessions
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)
            
            sessions = []
            for row in rows:
                session = dict(row)
                session['id'] = str(session['id'])
                session['created_at'] = session['created_at'].isoformat()
                # Parse JSONB fields back to Python objects
                if isinstance(session['sources'], str):
                    session['sources'] = json.loads(session['sources'])
                if isinstance(session['claims'], str):
                    session['claims'] = json.loads(session['claims'])
                if isinstance(session['evaluations'], str):
                    session['evaluations'] = json.loads(session['evaluations'])
                if isinstance(session['stages'], str):
                    session['stages'] = json.loads(session['stages'])
                sessions.append(session)
            
            return sessions
    
    async def get_session_by_id(self, session_id: str) -> Optional[dict]:
        """Get a specific Q&A session by ID."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    id, question, answer, sources, claims, evaluations,
                    quality_score, iterations, total_cost, total_duration_ms,
                    created_at, trace_id, stages
                FROM qa_sessions
                WHERE id = $1
            """, session_id)
            
            if not row:
                return None
            
            session = dict(row)
            session['id'] = str(session['id'])
            session['created_at'] = session['created_at'].isoformat()
            # Parse JSONB fields back to Python objects
            if isinstance(session['sources'], str):
                session['sources'] = json.loads(session['sources'])
            if isinstance(session['claims'], str):
                session['claims'] = json.loads(session['claims'])
            if isinstance(session['evaluations'], str):
                session['evaluations'] = json.loads(session['evaluations'])
            if isinstance(session['stages'], str):
                session['stages'] = json.loads(session['stages'])
            
            return session
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a specific Q&A session by ID."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM qa_sessions
                WHERE id = $1
            """, session_id)
            
            # Check if any row was deleted
            deleted = result.split()[-1] != '0'
            
            if deleted:
                logfire.info(f"Deleted session: {session_id}")
            
            return deleted
    
    async def delete_all_sessions(self) -> int:
        """Delete all Q&A sessions."""
        
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM qa_sessions")
            deleted_count = int(result.split()[-1])
            
            logfire.info(f"Deleted all sessions: {deleted_count} total")
            
            return deleted_count


# Global vector store instance
vector_store = VectorStore()


@asynccontextmanager
async def get_vector_store():
    """Get the vector store instance."""
    yield vector_store

