"""
Thread Splitter Utility.
Splits long content into sequential, gracefully formatted thread posts for Twitter, Threads, and Bluesky.
"""
import re

PLATFORM_LIMITS = {
    "twitter": 280,
    "threads": 500,
    "bluesky": 300,
}


def split_into_thread(content: str, platform: str = "twitter", max_chars: int | None = None) -> list[str]:
    """
    Split text into numbered thread segments respecting word and sentence boundaries.
    Adds `(i/N)` paging identifiers.
    """
    if not content or not content.strip():
        return []

    content = content.strip()
    limit = max_chars or PLATFORM_LIMITS.get(platform.lower(), 280)

    if len(content) <= limit:
        return [content]

    # Approximate reservation for pagination suffix (e.g. "\n\n(1/5)")
    suffix_reserve = 10
    effective_limit = limit - suffix_reserve

    # 1. First split by paragraphs
    paragraphs = content.split("\n\n")
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if not current_chunk:
            if len(para) <= effective_limit:
                current_chunk = para
            else:
                sentences = re.split(r'(?<=[.!?]) +', para)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    if not current_chunk:
                        if len(sentence) <= effective_limit:
                            current_chunk = sentence
                        else:
                            words = sentence.split(" ")
                            for word in words:
                                if not current_chunk:
                                    current_chunk = word
                                elif len(current_chunk) + 1 + len(word) <= effective_limit:
                                    current_chunk += " " + word
                                else:
                                    chunks.append(current_chunk.strip())
                                    current_chunk = word
                    elif len(current_chunk) + 1 + len(sentence) <= effective_limit:
                        current_chunk += " " + sentence
                    else:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence
        elif len(current_chunk) + 2 + len(para) <= effective_limit:
            current_chunk += "\n\n" + para
        else:
            chunks.append(current_chunk.strip())
            if len(para) <= effective_limit:
                current_chunk = para
            else:
                sentences = re.split(r'(?<=[.!?]) +', para)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    if not current_chunk:
                        current_chunk = sentence
                    elif len(current_chunk) + 1 + len(sentence) <= effective_limit:
                        current_chunk += " " + sentence
                    else:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    total = len(chunks)
    if total <= 1:
        return chunks

    paged_chunks = []
    for i, chunk in enumerate(chunks, 1):
        suffix = f"\n\n({i}/{total})"
        if len(chunk) + len(suffix) > limit:
            allowed_len = limit - len(suffix)
            chunk = chunk[:allowed_len].rstrip()
        paged_chunks.append(f"{chunk}{suffix}")

    return paged_chunks
