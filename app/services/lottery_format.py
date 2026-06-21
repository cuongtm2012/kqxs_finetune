"""Map 27 MB prize slots to prize levels (xskt order)."""

MB_SLOT_LEVELS = (
    ["DB"]
    + ["G1"]
    + ["G2", "G2"]
    + ["G3"] * 6
    + ["G4"] * 4
    + ["G5"] * 6
    + ["G6"] * 3
    + ["G7"] * 4
)


def slot_to_level(slot_index: int) -> str:
    if 0 <= slot_index < len(MB_SLOT_LEVELS):
        return MB_SLOT_LEVELS[slot_index]
    return "UNK"


def level_order_count(level: str) -> int:
    counts = {"DB": 1, "G1": 1, "G2": 2, "G3": 6, "G4": 4, "G5": 6, "G6": 3, "G7": 4}
    return counts.get(level, 1)


def split_number_fields(number: str) -> dict:
    tail = number[-2:].zfill(2) if number else "00"
    try:
        val = int(tail)
        return {
            "number": number,
            "last_two": tail,
            "first_digit": str(int(val / 10)),
            "last_digit": str(val % 10),
        }
    except ValueError:
        return {"number": number, "last_two": tail, "first_digit": None, "last_digit": None}


def bucket_dau_dit(last_two_values: list[str]) -> tuple[dict, dict]:
    dau = {i: [] for i in range(10)}
    dit = {i: [] for i in range(10)}
    for val in last_two_values:
        if not val:
            continue
        try:
            val_int = int(val)
        except ValueError:
            continue
        dit[val_int % 10].append(val)
        dau[int(val_int / 10)].append(val)
    for bucket in (dau, dit):
        for i in range(10):
            bucket[i].sort()
    return dau, dit


def prizes_to_ketqua(draw_date: str, prizes: list[dict]) -> dict:
    """Build legacy ketqua dict from normalized prize rows."""
    item = {"ngaychot": draw_date}
    for i in range(27):
        item[f"kq{i}"] = ""
    for i in range(10):
        item[f"dau{i}"] = ""
        item[f"dit{i}"] = ""

    last_two = []
    for row in sorted(prizes, key=lambda r: r["slot_index"]):
        idx = row["slot_index"]
        num = row["number"]
        if idx < 27:
            item[f"kq{idx}"] = num
        if row.get("last_two"):
            last_two.append(row["last_two"])

    last_two.sort()
    item["kqAr"] = last_two
    dau, dit = bucket_dau_dit(last_two)
    for i in range(10):
        item[f"dau{i}"] = str(dau[i])
        item[f"dit{i}"] = str(dit[i])
    return item


def flat_numbers_to_prize_rows(numbers: list[str]) -> list[dict]:
    rows = []
    level_seen: dict[str, int] = {}
    for slot_index, number in enumerate(numbers[:27]):
        if not number:
            continue
        level = slot_to_level(slot_index)
        order = level_seen.get(level, 0)
        level_seen[level] = order + 1
        fields = split_number_fields(number)
        rows.append(
            {
                "slot_index": slot_index,
                "prize_level": level,
                "prize_order": order,
                **fields,
            }
        )
    return rows
