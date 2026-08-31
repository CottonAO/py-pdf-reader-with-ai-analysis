import json
import re

CATEGORIES = (
    "etran_double_act",
    "etran_unified_wait_instruction",
    "no_tech_capability_clean",
    "no_tech_capability_mixed",
    "etran_on_siding",
    "emergency_chs",
    "gov_decree_478",
    "rules_mismatch",
    "logistics_control",
    "other_reject",
    "unknown",
)

CATEGORY_DECISION = {
    "etran_double_act": "correct",
    "etran_unified_wait_instruction": "correct",
    "no_tech_capability_clean": "correct",
    "no_tech_capability_mixed": "reject",
    "etran_on_siding": "reject",
    "emergency_chs": "reject",
    "gov_decree_478": "reject",
    "rules_mismatch": "reject",
    "logistics_control": "reject",
    "other_reject": "reject",
    "unknown": "reject",
}

CORRECT_REPLY = (
    "По формулировке причины в акте ГУ-23 есть основания для корректировки. "
    "Направьте ГУ-23 на Claims@ufaoil.ru"
)
REJECT_REPLY = (
    "Причина, указанная в ГУ-23, является основанием для отказа в корректировке."
)

REPLIES = {"correct": CORRECT_REPLY, "reject": REJECT_REPLY}


def strip_json(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def parse_model_json(raw: str) -> dict:
    try:
        parsed = json.loads(strip_json(raw))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Модель вернула не JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Модель вернула JSON не-объект")
    return parsed


def build_classify_result(parsed: dict, model: str) -> dict:
    category = str(parsed.get("category") or "unknown").strip()
    if category not in CATEGORIES:
        category = "unknown"

    decision = CATEGORY_DECISION[category]
    wagons = parsed.get("wagons") or []
    if not isinstance(wagons, list):
        wagons = [str(wagons)]

    return {
        "ok": True,
        "decision": decision,
        "reply_text": REPLIES[decision],
        "needs_ocr": False,
        "extracted": {
            "legal_entity": str(parsed.get("legal_entity") or ""),
            "station": str(parsed.get("station") or ""),
            "act_number": str(parsed.get("act_number") or ""),
            "act_date": str(parsed.get("act_date") or ""),
            "wagons": [str(item) for item in wagons if item],
            "reason_quote": str(parsed.get("reason_quote") or ""),
        },
        "debug": {
            "category": category,
            "confidence": str(parsed.get("confidence") or "low"),
            "act_form": str(parsed.get("act_form") or "unknown"),
            "location": str(parsed.get("location") or "unknown"),
            "notes": str(parsed.get("notes") or ""),
            "model": model,
        },
    }
