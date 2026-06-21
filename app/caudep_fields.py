def caudep_field_name(limit: int, nhay: int, lon: int) -> str:
    return f"limit{limit}nhay{nhay}lon{lon}"


def iter_caudep_combinations(max_limit: int = 15):
    for limit in range(1, max_limit):
        for nhay in range(1, 4):
            for lon in range(0, 2):
                yield limit, nhay, lon


CAUDEP_INSERT_FIELDS = []
for limit in range(1, 21):
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 1, 0))
for limit in range(1, 6):
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 2, 0))
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 3, 0))
for limit in range(1, 21):
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 1, 1))
for limit in range(1, 6):
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 2, 1))
    CAUDEP_INSERT_FIELDS.append(caudep_field_name(limit, 3, 1))
