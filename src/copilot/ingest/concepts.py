"""LOINC code → lab concept. Built from codes observed in the data, not from memory.
Within each list, earlier codes are preferred when two codes report the same day."""

LAB_CONCEPTS: dict[str, list[str]] = {
    "hba1c":      ["4548-4"],
    "egfr":       ["33914-3"],
    "creatinine": ["2160-0", "38483-4"],   # serum/plasma preferred over blood
    "glucose":    ["2345-7", "2339-0"],
    "potassium":  ["2823-3", "6298-4"],
}

_CODE_TO_CONCEPT = {code: concept for concept, codes in LAB_CONCEPTS.items() for code in codes}


def concept_for(loinc: str | None) -> str | None:
    return _CODE_TO_CONCEPT.get(loinc) if loinc else None


def code_rank(concept: str, loinc: str) -> int:
    """Lower is preferred."""
    return LAB_CONCEPTS[concept].index(loinc)