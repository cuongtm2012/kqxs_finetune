from typing import Optional


def validate_string(value: Optional[str]) -> bool:
    return value is not None and value.strip() != ""


def validate_strings(*values: Optional[str]) -> bool:
    return all(validate_string(v) for v in values)
