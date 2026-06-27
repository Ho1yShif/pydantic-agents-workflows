"""Shared chunking helper for documentation ingestion.

Splits a single page of content into ~2000-character chunks at paragraph
boundaries, producing the doc dicts ({title, section, source, content}) consumed
by generate_embeddings.py and crawl_tutorials.py. Keeping this in one place means
the bulk-docs corpus and the tutorials crawl chunk content identically.
"""

import re
from typing import Dict, List, Optional

MAX_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 100

# Below this, a heading section is too small to stand alone (e.g. a heading with
# a one-line body); it gets merged into the previous section's chunk instead.
_MERGE_FLOOR_CHARS = 60

_HEADING_RE = re.compile(r"(?m)^(#{2,3}\s+.*)$")


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


def chunk_markdown_by_heading(
    title: str,
    source: str,
    content: str,
    max_chars: int = MAX_CHUNK_CHARS,
) -> List[Dict]:
    """Split structured markdown into one focused chunk per ``##``/``###`` section.

    Hand-curated docs pack many distinct facts into one page. A single whole-page
    embedding (or even ~2000-char chunks) dilutes any one fact, so a narrow claim
    like "billed prorated by the second" can't surface its supporting passage in a
    top-k similarity search and fails verification. Splitting on headings gives each
    fact-cluster its own embedding, with the heading text (e.g. "Pricing", "Beta
    Limitations") kept in the chunk so it matches the claim's vocabulary.

    Behavior:
    - The pre-heading preamble (page H1 + "Source:" line) is dropped — it carries no
      verifiable facts and only dilutes the first section.
    - A section longer than ``max_chars`` falls back to paragraph chunking.
    - A section too small to stand alone is merged into the previous chunk.
    - Content with no ``##``/``###`` headings falls back to ``chunk_document``.

    The section heading becomes each doc's ``section``; ``title`` stays the page title.
    """
    clean_content = content.strip()
    if len(clean_content) < MIN_CHUNK_CHARS:
        return []

    # re.split with a captured group yields: [preamble, heading1, body1, heading2, body2, ...]
    parts = _HEADING_RE.split(clean_content)
    headings_and_bodies = parts[1:]
    if not headings_and_bodies:
        # No section headings to split on — fall back to size-based chunking.
        return chunk_document(title, None, source, content, max_chars)

    def _doc(section: str, chunk_content: str) -> Dict:
        return {
            "title": f"{title} - {section}",
            "section": section,
            "source": source,
            "content": chunk_content,
        }

    docs: List[Dict] = []
    for i in range(0, len(headings_and_bodies), 2):
        heading_line = headings_and_bodies[i].strip()
        body = headings_and_bodies[i + 1].strip() if i + 1 < len(headings_and_bodies) else ""
        section = re.sub(r"^#{2,3}\s+", "", heading_line).strip()
        text = f"{heading_line}\n\n{body}".strip() if body else heading_line

        # Merge a too-small section into the previous chunk rather than emit dust.
        if len(text) < _MERGE_FLOOR_CHARS and docs:
            docs[-1]["content"] = f"{docs[-1]['content']}\n\n{text}"
            continue

        # Sub-split an oversized section at paragraph boundaries.
        if len(text) > max_chars:
            docs.extend(
                {**sub, "title": f"{title} - {section}"}
                for sub in chunk_document(title, section, source, text, max_chars)
            )
        else:
            docs.append(_doc(section, text))

    return docs
