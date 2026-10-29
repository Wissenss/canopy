import re

TAG_COUNT = 8

def seconds_to_ms(seconds: float) -> int:
    """
        converts seconds to whole milliseconds.
    """

    return int(round(seconds * 1000))


def cue_values(v_s: float, v_e: float) -> dict[str, str]:
    """
        returns the vocals start / end tag values (in seconds and milliseconds).
    """

    return {
        "vocals_start_s": str(int(round(v_s))),
        "vocals_start_ms": str(seconds_to_ms(v_s)),
        "vocals_end_s": str(int(round(v_e))),
        "vocals_end_ms": str(seconds_to_ms(v_e)),
    }


def pattern_tags(pattern: str) -> set[str]:
    """
        returns the names of the #tag# placeholders used in pattern.
    """

    return set(re.findall(r"#(\w+)#", pattern))


def build_query(pattern: str, values: dict[str, str]) -> str:
    """
        returns pattern with each #tag# replaced by its value, unknown tags are left as is.
    """

    return re.sub(r"#(\w+)#", lambda m: values.get(m.group(1), m.group(0)), pattern)


if __name__ == "__main__":
    print(build_query("UPDATE songs SET v_s = #vocals_start_s#, v_e = #vocals_end_s# WHERE song_id = #val_1#;", {**cue_values(10.22, 194.068), "val_1": "2"}))
