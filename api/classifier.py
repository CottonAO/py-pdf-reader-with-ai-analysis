# Константы для классификации (общие для всех провайдеров)
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