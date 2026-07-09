from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from backend.app.memory_store import list_analyst_memories
from pio_platform.data_loader import DatasetBundle
from pio_platform.profiling import build_column_profile


KNOWLEDGE_ROOT = Path("knowledge")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "month",
    "of",
    "on",
    "or",
    "part",
    "show",
    "that",
    "the",
    "this",
    "to",
    "what",
    "why",
    "with",
}


def retrieve_analyst_context(
    workbook_id: str,
    sheet_name: str,
    question: str,
    bundle: DatasetBundle,
    filtered_df: pd.DataFrame,
    anomaly_center: dict[str, Any],
    forecast_payload: dict[str, Any] | None,
    filters: dict[str, Any],
    limit: int = 6,
) -> list[dict[str, Any]]:
    question_tokens = _tokenize(question)
    snippets: list[dict[str, Any]] = []

    snippets.extend(_scope_snippets(sheet_name=sheet_name, filtered_df=filtered_df, filters=filters))
    snippets.extend(_field_snippets(bundle=bundle, filtered_df=filtered_df))
    snippets.extend(_anomaly_snippets(anomaly_center))
    snippets.extend(_forecast_snippets(forecast_payload))
    snippets.extend(
        _memory_snippets(
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            question=question,
            forecast_payload=forecast_payload,
        )
    )
    snippets.extend(_knowledge_snippets())

    scored: list[dict[str, Any]] = []
    for snippet in snippets:
        text = " ".join(
            [
                str(snippet.get("title", "")),
                str(snippet.get("content", "")),
                " ".join(str(tag) for tag in snippet.get("tags", [])),
            ]
        )
        score = float(snippet.get("baseScore", 0))
        overlap = len(question_tokens & _tokenize(text))
        score += overlap * 2.0

        focus_part = forecast_payload["selectedPart"] if forecast_payload else ""
        if focus_part and focus_part.lower() in text.lower():
            score += 3.0
        if score <= 0:
            continue
        enriched = dict(snippet)
        enriched["score"] = round(score, 2)
        scored.append(enriched)

    scored.sort(
        key=lambda item: (
            -float(item["score"]),
            int(item.get("priority", 999)),
            str(item.get("title", "")),
        )
    )

    chosen: list[dict[str, Any]] = []
    seen = set()
    for snippet in scored:
        key = (snippet.get("source"), snippet.get("title"), snippet.get("content"))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(
            {
                "source": snippet["source"],
                "title": snippet["title"],
                "content": snippet["content"],
                "tags": snippet.get("tags", []),
                "score": snippet["score"],
            }
        )
        if len(chosen) >= limit:
            break

    return chosen


def _scope_snippets(
    sheet_name: str,
    filtered_df: pd.DataFrame,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    active_filters: list[str] = []
    for key, label in [
        ("search", "search"),
        ("brand", "brand"),
        ("model", "model"),
        ("modelYear", "model year"),
        ("part", "part"),
        ("startDate", "start date"),
        ("endDate", "end date"),
    ]:
        value = filters.get(key)
        if isinstance(value, list) and value:
            active_filters.append(f"{label}: {', '.join(map(str, value[:4]))}")
        elif value:
            active_filters.append(f"{label}: {value}")

    snippets.append(
        {
            "source": "data_scope",
            "title": "Current filter scope",
            "content": (
                f"Filtered slice contains {len(filtered_df):,} rows from sheet {sheet_name}. "
                + (
                    "Active filters are " + "; ".join(active_filters) + "."
                    if active_filters
                    else "No explicit business filters are active."
                )
            ),
            "tags": ["filters", "scope", "slice"],
            "baseScore": 2.0,
            "priority": 1,
        }
    )
    return snippets


def _field_snippets(bundle: DatasetBundle, filtered_df: pd.DataFrame) -> list[dict[str, Any]]:
    profile = build_column_profile(bundle.dataframe, bundle.date_candidates)
    if profile.empty:
        return []

    role_to_column = bundle.roles
    snippets: list[dict[str, Any]] = []
    role_labels = {
        "date": "time axis",
        "brand": "brand dimension",
        "model": "vehicle model dimension",
        "model_year": "model year dimension",
        "part_number": "part number identifier",
        "part_description": "part description label",
        "installation_quantity": "installation quantity metric",
        "revenue": "sales revenue metric",
    }
    for role, column in role_to_column.items():
        row = profile.loc[profile["Column"] == column]
        if row.empty:
            continue
        item = row.iloc[0]
        current_unique = int(filtered_df[column].nunique()) if column in filtered_df.columns else 0
        snippets.append(
            {
                "source": "field_profile",
                "title": f"{column} field profile",
                "content": (
                    f"{column} is the detected {role_labels.get(role, role)}. "
                    f"Type: {item['Type']}. Missing rate: {item['Missing %']}%. "
                    f"Unique values in the current slice: {current_unique:,}. "
                    f"Sample values: {item['Sample Values'] or 'N/A'}."
                ),
                "tags": [role, column, "schema", "field"],
                "baseScore": 1.5,
                "priority": 2,
            }
        )
    return snippets


def _anomaly_snippets(anomaly_center: dict[str, Any]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for index, record in enumerate((anomaly_center.get("records") or [])[:4], start=1):
        content = (
            f"Part {record['part']} is ranked anomaly #{index}. "
            f"Latest change: {(record.get('deltaPct') or 0):+.1f}% month over month. "
            f"Regime: {record.get('regime', 'Unknown')}. "
            f"Forecast risk: {record.get('forecastRisk', 'Unknown')}."
        )
        evidence = record.get("evidence") or []
        if evidence:
            content += f" Evidence: {' '.join(evidence[:2])}"
        snippets.append(
            {
                "source": "anomaly_center",
                "title": f"Anomaly signal for {record['part']}",
                "content": content,
                "tags": ["anomaly", "change", record["part"]],
                "baseScore": 2.5 if index == 1 else 1.4,
                "priority": 3,
            }
        )
    return snippets


def _forecast_snippets(forecast_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not forecast_payload:
        return []

    summary = forecast_payload["summary"]
    content = (
        f"Forecast focus part {forecast_payload['selectedPart']} uses model {summary['modelName']}. "
        f"Next forecast: {summary['nextForecast']:,.0f}. "
        f"Latest actual: {summary['latestActual']:,.0f}. "
        f"Confidence: {summary['confidence']}. Forecast risk: {summary['forecastRisk']}."
    )
    if summary.get("wape") is not None and summary.get("bias") is not None:
        content += f" Backtest WAPE: {summary['wape'] * 100:.1f}%. Bias: {summary['bias'] * 100:+.1f}%."

    return [
        {
            "source": "forecast_center",
            "title": f"Forecast summary for {forecast_payload['selectedPart']}",
            "content": content,
            "tags": ["forecast", forecast_payload["selectedPart"], "backtest"],
            "baseScore": 2.2,
            "priority": 4,
        }
    ]


def _memory_snippets(
    workbook_id: str,
    sheet_name: str,
    question: str,
    forecast_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    target_part = forecast_payload["selectedPart"] if forecast_payload else ""
    question_tokens = _tokenize(question)
    snippets: list[dict[str, Any]] = []

    for item in list_analyst_memories(workbook_id=workbook_id, sheet_name=sheet_name, limit=12):
        text = " ".join(
            [
                item.get("question", ""),
                item.get("answer", ""),
                item.get("focusPart") or "",
                " ".join(item.get("evidence", [])),
            ]
        )
        overlap = len(question_tokens & _tokenize(text))
        if target_part and item.get("focusPart") == target_part:
            overlap += 2
        if overlap <= 0:
            continue

        snippets.append(
            {
                "source": "analyst_memory",
                "title": f"Past analyst memory #{item['id']}",
                "content": (
                    f"Previous question: {item['question']}. "
                    f"Saved conclusion: {item['answer']}"
                ),
                "tags": ["memory", item.get("focusPart") or "", item.get("riskLevel") or ""],
                "baseScore": 1.0 + overlap,
                "priority": 5,
            }
        )
    return snippets[:3]


def _knowledge_snippets() -> list[dict[str, Any]]:
    if not KNOWLEDGE_ROOT.exists():
        return []

    snippets: list[dict[str, Any]] = []
    for path in sorted(KNOWLEDGE_ROOT.rglob("*.md"))[:30]:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not text:
            continue

        title = path.stem.replace("-", " ").replace("_", " ")
        for index, chunk in enumerate(_chunk_markdown(text)[:6], start=1):
            snippets.append(
                {
                    "source": "knowledge_doc",
                    "title": f"{title} · section {index}",
                    "content": chunk,
                    "tags": [path.parent.name, path.stem, "knowledge"],
                    "baseScore": 0.6,
                    "priority": 6,
                }
            )
    return snippets


def _chunk_markdown(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    chunks: list[str] = []
    for block in blocks:
        single = re.sub(r"\s+", " ", block).strip()
        if len(single) > 360:
            single = single[:357].rstrip() + "..."
        if len(single) >= 40:
            chunks.append(single)
    return chunks


def _tokenize(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9_]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    }
    return tokens
