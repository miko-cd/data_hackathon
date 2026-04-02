import re
from pathlib import Path
from typing import Optional
import pandas as pd

LATIN_RE = re.compile(r"[A-Za-z]")  # англи/latin

MIN_WORD = 3
MAX_WORD = 18


def has_latin(text: str) -> bool:
    return LATIN_RE.search(text) is not None


# -------------------------
# Abbreviations (MGL)
def load_abbreviations_excel(path: str) -> dict[str, str]:
    abbr_map: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return abbr_map

    df = pd.read_excel(p)
    cols = {str(c).strip().lower(): c for c in df.columns}
    if "abbr" not in cols or "full" not in cols:
        return abbr_map

    abbr_col = cols["abbr"]
    full_col = cols["full"]

    for _, row in df[[abbr_col, full_col]].iterrows():
        abbr = "" if pd.isna(row[abbr_col]) else str(row[abbr_col]).strip()
        full = "" if pd.isna(row[full_col]) else str(row[full_col]).strip()
        if abbr and full:
            abbr_map[abbr] = full

    return abbr_map


def compile_abbreviation_regex(abbr_map: dict[str, str]) -> Optional[re.Pattern]:
    if not abbr_map:
        return None
    keys = sorted(abbr_map.keys(), key=len, reverse=True)
    abbr_alt = "|".join(map(re.escape, keys))
    pat = rf"(?:(?<=^)|(?<=\s)|(?<=-))({abbr_alt})(?:(?=$)|(?=\s)|(?=-))"
    return re.compile(pat)


def expand_abbreviations(text: str, abbr_map: dict[str, str], abbr_re: Optional[re.Pattern]) -> str:
    if not abbr_map or abbr_re is None:
        return text

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if not key.isupper():
            return key
        return abbr_map.get(key, key)

    return abbr_re.sub(repl, text)


# -------------------------
# Cleaning
# -------------------------
DASHES_RE = re.compile(r"[\-\u2013\u2014]")


def remove_special_characters(text: str) -> str:
    text = text.lower()

    # ярианы эхний зураас
    text = re.sub(r"(^|\s)[\-\u2013\u2014]+\s*", r"\1", text)

    # ишлэлүүдийг авах
    text = re.sub(r"[\"'“”‘’«»]", "", text)

    # цэг, таслал, slash, colon, percent, dash-ийг түр үлдээнэ
    # (14.00, 3,980, 12/25, см3 гэх мэт case-д хэрэгтэй)
    text = re.sub(r"[^0-9а-яёөү\s\-\.,:/%]", " ", text, flags=re.IGNORECASE)

    # кирилл-кирилл хоорондох зураасыг наах
    text = re.sub(r"([а-яёөү])\s*-\s*([а-яёөү])", r"\1\2", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()
    return text


# -------------------------
def number_to_mongolian(n):
    if not isinstance(n, int):
        try:
            n = int(n)
        except ValueError:
            return "Буруу оролт"

    if n < 0:
        return "сөрөг " + number_to_mongolian(abs(n))
    if n == 0:
        return "тэг"

    ones = ["", "нэг", "хоёр", "гурав", "дөрөв", "тав", "зургаа", "долоо", "найм", "ес"]
    ones_combined = ["", "нэгэн", "хоёр", "гурван", "дөрвөн", "таван", "зургаан", "долоон", "найман", "есөн"]
    tens = ["", "арав", "хорь", "гуч", "дөч", "тавь", "жар", "дал", "ная", "ер"]
    tens_combined = ["", "арван", "хорин", "гучин", "дөчин", "тавин", "жаран", "далан", "наян", "ерэн"]

    def convert_below_hundred(num, is_combined=False):
        if num == 0:
            return ""
        if num < 10:
            return ones_combined[num] if is_combined else ones[num]
        if num == 10:
            return "арван" if is_combined else "арав"
        if num < 20:
            return "арван " + ones[num % 10]
        ten_digit = num // 10
        one_digit = num % 10
        if one_digit == 0:
            return tens_combined[ten_digit] if is_combined else tens[ten_digit]
        return tens_combined[ten_digit] + " " + (ones_combined[one_digit] if is_combined else ones[one_digit])

    def convert_below_thousand(num, is_combined=False):
        if num == 0:
            return ""
        if num < 100:
            return convert_below_hundred(num, is_combined)

        hundred_part = num // 100
        remainder = num % 100
        hundred_suffix = "зуу" if (remainder == 0 and not is_combined) else "зуун"

        if hundred_part == 1:
            result = hundred_suffix
        else:
            result = ones_combined[hundred_part] + " " + hundred_suffix

        if remainder > 0:
            result += " " + convert_below_hundred(remainder, is_combined)
        return result

    result = []
    if n >= 1_000_000_000:
        part = n // 1_000_000_000
        n %= 1_000_000_000
        result.append("тэрбум" if part == 1 else convert_below_thousand(part, True) + " тэрбум")
    if n >= 1_000_000:
        part = n // 1_000_000
        n %= 1_000_000
        result.append("сая" if part == 1 else convert_below_thousand(part, True) + " сая")
    if n >= 1000:
        part = n // 1000
        n %= 1000
        result.append("мянга" if part == 1 else convert_below_thousand(part, True) + " мянга")
    if n > 0:
        result.append(convert_below_thousand(n, False))
    return " ".join(result)


def number_to_mongolian_year(n: int) -> str:
    if n < 1000 or n > 2999:
        return number_to_mongolian(n)
    thousands = n // 1000
    rem = n % 1000

    if thousands == 1:
        head = "мянга"
    elif thousands == 2:
        head = "хоёр мянга"
    else:
        head = number_to_mongolian(thousands) + " мянга"

    if rem == 0:
        return head
    return f"{head} {number_to_mongolian(rem)}"


def phone_number_to_mongolian(phone):
    digits = re.sub(r"[-\s]", "", str(phone))
    if not digits.isdigit() or len(digits) != 8:
        return None

    pairs = [digits[i: i + 2] for i in range(0, 8, 2)]
    ones = ["тэг", "нэг", "хоёр", "гурав", "дөрөв", "тав", "зургаа", "долоо", "найм", "ес"]
    tens = ["", "арван", "хорин", "гучин", "дөчин", "тавин", "жаран", "далан", "наян", "ерэн"]

    def two_digit_to_mongolian(num_str):
        num = int(num_str)
        if num == 0:
            return "тэг тэг"
        if num < 10:
            return "тэг " + ones[num]
        if num == 10:
            return "арав"
        if num < 20:
            return "арван " + ones[num % 10]
        ten_digit = num // 10
        one_digit = num % 10
        if one_digit == 0:
            return tens[ten_digit]
        return tens[ten_digit] + " " + ones[one_digit]

    return ", ".join(two_digit_to_mongolian(p) for p in pairs)


# -------------------------
# Helper-үүд
VALID_PHONE_PREFIXES = {
    "50", "55", "60", "66", "70", "75", "76", "77",
    "80", "83", "85", "86", "88", "89", "90", "91",
    "94", "95", "96", "99"
}

ORDINAL_SUFFIX_RE = r"(?:-?(?:нд|д|т|ний|ны|ын|ийн|аар|ээр|оор|өөр))"
RANGE_JOIN_RE = r"(?:\s*(?:-|–|—)\s*)"


def _to_plain_int(num_str: str) -> int:
    return int(num_str.replace(",", ""))


def _num_word(num_str: str) -> str:
    n = _to_plain_int(num_str)
    if 1900 <= n <= 2099:
        return number_to_mongolian_year(n)
    return number_to_mongolian(n)


def convert_numbers_in_text(text: str) -> str:
    # 0) 14.00-17.00
    time_range_pattern = r"(?<!\d)(\d{1,2})\s*\.\s*00" + RANGE_JOIN_RE + r"(\d{1,2})\s*\.\s*00(?!\d)"
    text = re.sub(
        time_range_pattern,
        lambda m: f"{number_to_mongolian(int(m.group(1)))}өөс {number_to_mongolian(int(m.group(2)))}",
        text
    )

    # 1) year/number range: 2015-2016, 7-12
    range_pattern = r"(?<!\d)(\d{1,4}(?:,\d{3})*)(?:\s*)" + RANGE_JOIN_RE + r"(\d{1,4}(?:,\d{3})*)(?!\d)"
    text = re.sub(
        range_pattern,
        lambda m: f"{_num_word(m.group(1))}аас {_num_word(m.group(2))}",
        text
    )

    # 2) phone with explicit separator
    phone_pattern = r"(?<!\d)(\d{4})[-\s](\d{4})(?!\d)"

    def replace_phone(m: re.Match) -> str:
        digits = m.group(1) + m.group(2)
        if m.group(1)[:2] not in VALID_PHONE_PREFIXES:
            return m.group(0)
        r = phone_number_to_mongolian(digits)
        return r.replace(", ", " ") if r else m.group(0)

    text = re.sub(phone_pattern, replace_phone, text)

    # 3) см3 / м3
    cubic_pattern = r"(?<!\d)(\d{1,4}(?:,\d{3})*)\s*(см|м)\s*3(?!\d)"
    text = re.sub(
        cubic_pattern,
        lambda m: f"{_num_word(m.group(1))} {'сантиметр куб' if m.group(2) == 'см' else 'метр куб'}",
        text
    )

    # 4) ordinal: 25-нд
    ordinal_pattern = r"(?<!\d)(\d{1,4}(?:,\d{3})*)" + ORDINAL_SUFFIX_RE
    text = re.sub(
        ordinal_pattern,
        lambda m: f"{_num_word(m.group(1))}{m.group(0)[len(m.group(1)):]}",
        text
    )

    # 5) plain numbers incl 3,980
    number_pattern = r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d+)(?!\d)"

    def replace_number(m: re.Match) -> str:
        num_str = m.group(1).replace(",", "")

        if len(num_str) == 8 and num_str[:2] in VALID_PHONE_PREFIXES:
            ph = phone_number_to_mongolian(num_str)
            if ph:
                return ph.replace(", ", " ")

        n = int(num_str)
        if 1900 <= n <= 2099:
            return number_to_mongolian_year(n)
        return number_to_mongolian(n)

    text = re.sub(number_pattern, replace_number, text)

    # cleanup punctuation
    text = re.sub(r"[,:;/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


PARENS_RE = re.compile(r"\([^)]*\)")


def drop_parentheses_if_contains_abbr(text: str, abbr_map: dict[str, str]) -> str:
    if not text or not abbr_map:
        return text
    keys = sorted(abbr_map.keys(), key=len, reverse=True)

    def repl(m: re.Match) -> str:
        chunk = m.group(0)
        for k in keys:
            if k and k in chunk:
                return ""
        return chunk

    return PARENS_RE.sub(repl, text)


# -------------------------
def build_normalizer(
    abbr_csv_path: str = "mongol_abb.xlsx",
    enable_abbr: bool = False,
    drop_if_latin: bool = True,
):
    abbr_map = load_abbreviations_excel(abbr_csv_path) if enable_abbr else {}
    abbr_re = compile_abbreviation_regex(abbr_map) if enable_abbr else None

    def normalize_text(text) -> str:
        if text is None:
            return text

        text_ = text if isinstance(text, str) else str(text)

        if drop_if_latin and has_latin(text_):
            return ""

        if enable_abbr:
            text_ = drop_parentheses_if_contains_abbr(text_, abbr_map)

        if enable_abbr:
            text_ = expand_abbreviations(text_, abbr_map, abbr_re)

        text_ = remove_special_characters(text_)
        text_ = convert_numbers_in_text(text_)

        return text_

    return normalize_text