"""Shared chunking helper for documentation ingestion.

Splits a single page of content into ~2000-character chunks at paragraph
boundaries, producing the doc dicts ({title, section, source, content}) consumed
by generate_embeddings.py and crawl_tutorials.py. Keeping this in one place means
the bulk-docs corpus and the tutorials crawl chunk content identically.
"""

from typing import Dict, List, Optional

MAX_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 100


def chunk_document(
    title: str,
    section: Optional[str],
    source: str,
    content: str,
    max_chars: int = MAX_CHUNK_CHARS,
) -> List[Dict]:
    """Split content into chunks of ~max_chars, splitting at paragraph boundaries.

    Returns a list of doc dicts. Content shorter than MIN_CHUNK_CHARS yields no
    chunks. The display title combines the page title and section when a section
    is present, matching the existing corpus convention.
    """
    clean_content = content.strip()
    if len(clean_content) < MIN_CHUNK_CHARS:
        return []

    display_title = title if not section else f"{title} - {section}"
    display_section = section or title

    def _doc(chunk_content: str) -> Dict:
        return {
            "title": display_title,
            "section": display_section,
            "source": source,
            "content": chunk_content,
        }

    if len(clean_content) <= max_chars:
        return [_doc(clean_content)]

    # Prefer paragraph boundaries; fall back to single newlines for content that
    # arrives as one block (e.g. text scraped from HTML, which has no blank lines).
    separator = "\n\n"
    segments = clean_content.split(separator)
    if len(segments) == 1:
        separator = "\n"
        segments = clean_content.split(separator)

    # Hard-split any segment still larger than max_chars so no chunk is oversized.
    bounded_segments: List[str] = []
    for segment in segments:
        if len(segment) <= max_chars:
            bounded_segments.append(segment)
        else:
            for start in range(0, len(segment), max_chars):
                bounded_segments.append(segment[start:start + max_chars])

    docs: List[Dict] = []
    current_chunk: List[str] = []
    current_length = 0
    sep_len = len(separator)

    for segment in bounded_segments:
        segment_length = len(segment)
        if current_length + segment_length > max_chars and current_chunk:
            docs.append(_doc(separator.join(current_chunk)))
            current_chunk = [segment]
            current_length = segment_length
        else:
            current_chunk.append(segment)
            current_length += segment_length + sep_len

    if current_chunk:
        docs.append(_doc(separator.join(current_chunk)))

    return docs
