"""Collect run analytics and write a machine-readable summary for post-processing.

Produces a ``<output>.analytics.json`` next to the other outputs and a short
human-readable summary in the log: total highlights, per-colour breakdown,
reference-correction coverage, audiobook transcription confidence, etc.
"""

import datetime
import json


def build_analytics(*, input_path, input_kind, pages_total, pages_processed,
                    pages_with_highlights, results, color_counts, cross_page_merged,
                    reference_matched, sources, archive_located, outputs,
                    correction_layers=None):
    """Assemble the analytics dict from collected run data."""
    total = len(results)
    spell_only = total - reference_matched

    refs = []
    for s in sources:
        entry = {
            "kind": s.get("kind"),
            "path": s.get("path"),
            "characters": s.get("chars", len(s.get("text", "") or "")),
            "status": s.get("status", "loaded"),
        }
        if s.get("transcription"):
            entry["transcription"] = s["transcription"]
        refs.append(entry)

    from config import REVIEW_CONFIDENCE_THRESHOLD

    confidences = [r.get("confidence", 0.0) for r in results]
    review_rows = [
        {"page": r["page"], "confidence": r.get("confidence"),
         "text": r["highlight_text"][:80]}
        for r in results if r.get("review")
    ]

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "input": {
            "path": input_path,
            "type": input_kind,
            "pages_total": pages_total,
            "pages_processed": pages_processed,
            "pages_with_highlights": pages_with_highlights,
        },
        "confidence": {
            "mean": round(sum(confidences) / len(confidences), 1) if confidences else 0.0,
            "min": min(confidences) if confidences else 0.0,
            "threshold": REVIEW_CONFIDENCE_THRESHOLD,
            "flagged_for_review": len(review_rows),
            "review_rows": review_rows,
        },
        "highlights": {
            "total": total,
            "by_color": dict(sorted(color_counts.items())),
            "cross_page_merged": cross_page_merged,
            "avg_chars": round(
                sum(len(r["highlight_text"]) for r in results) / total, 1
            ) if total else 0,
        },
        "correction": {
            "references_used": len(sources),
            "reference_matched": reference_matched,
            "spell_checked_only": spell_only,
            "match_rate_pct": round(100 * reference_matched / total, 1) if total else 0.0,
            "archive_links": archive_located,
        },
        "correction_layers": correction_layers or {},
        "references": refs,
        "outputs": outputs,
    }


def write_analytics(analytics, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(analytics, f, indent=2, ensure_ascii=False)


def summary_lines(analytics):
    """Short human-readable summary (list of lines)."""
    hi = analytics["highlights"]
    inp = analytics["input"]
    corr = analytics["correction"]
    conf = analytics.get("confidence", {})
    lines = [
        "-------- Run summary --------",
        f"Input: {inp['type']} | {inp['pages_processed']}/{inp['pages_total']} "
        f"pages processed | {inp['pages_with_highlights']} with highlights",
        f"Highlights: {hi['total']} total | by colour "
        f"{hi['by_color']} | {hi['cross_page_merged']} merged across pages",
        f"Confidence: mean {conf.get('mean')} | min {conf.get('min')} | "
        f"{conf.get('flagged_for_review')} row(s) below "
        f"{conf.get('threshold')} flagged for review",
    ]
    if corr["references_used"]:
        lines.append(
            f"Correction: {corr['reference_matched']}/{hi['total']} "
            f"reference-matched ({corr['match_rate_pct']}%), "
            f"{corr['spell_checked_only']} spell-checked | "
            f"{corr['archive_links']} archive links"
        )
        for r in analytics["references"]:
            t = r.get("transcription")
            extra = (f" | transcription conf {t['confidence_pct']}%"
                     f" ({t.get('model', '?')})" if t else "")
            lines.append(f"  - {r['kind']}: {r['characters']:,} chars"
                         f" [{r['status']}]{extra}")
    else:
        lines.append("Correction: spell-check only (no reference provided)")
    return lines
