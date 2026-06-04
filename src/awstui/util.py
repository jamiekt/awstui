from __future__ import annotations


def human_bytes(n: int) -> str:
    """Format a byte count as a human-readable string (B, KB, ..., TB)."""
    size: float = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{n} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} B"
