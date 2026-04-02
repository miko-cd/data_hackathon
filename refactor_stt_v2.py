#!/usr/bin/env python3
"""
Mongolian STT text refactoring pipeline.

Steps:
  0. Run pre-clean (cleaning_shit.py) to remove register/profanity, expand abbrev/currency, etc.
  1. Join fragmented sentence rows
  2. Split on intra-line sentence boundaries (e.g. "байна.Тэгвэл")
  3. Normalize numbers → Mongolian words
  4. Filter noise lines and invalid lengths
  5. Deduplicate
  6. Output clean CSV/TXT

Usage:
  python refactor_stt.py [input.csv|input.txt] [output.csv|output.txt]
"""

import csv
import re
import sys
from pathlib import Path

from pre_clean  import main as pre_clean_main

# ── Number → Mongolian words (REPLACED with your function) ──── ──────────────

DIGIT_WORDS = {
    '0': 'тэг', '1': 'нэг', '2': 'хоёр', '3': 'гурав', '4': 'дөрөв',
    '5': 'тав', '6': 'зургаа', '7': 'долоо', '8': 'найм', '9': 'ес'
}

def number_to_mongolian(n):
    """
    Тоог монгол үг рүү хөрвүүлнэ.
    """
    if not isinstance(n, int):
        try:
            n = int(n)
        except ValueError:
            return "Буруу оролт"
    
    if n < 0:
        return "сөрөг " + number_to_mongolian(abs(n))
    
    if n == 0:
        return "тэг"
    
    # Үндсэн тоонууд (ганц бие)
    ones = ["", "нэг", "хоёр", "гурав", "дөрөв", "тав", "зургаа", "долоо", "найм", "ес"]
    
    # Холбох хэлбэр (нэгэн, хоёр, гурван, дөрвөн, таван, зургаан, долоон, найман, есөн)
    ones_combined = ["", "нэгэн", "хоёр", "гурван", "дөрвөн", "таван", "зургаан", "долоон", "найман", "есөн"]
    
    # Аравтууд
    tens = ["", "арав", "хорь", "гуч", "дөч", "тавь", "жар", "дал", "ная", "ер"]
    
    # Аравтуудын холбох хэлбэр (арван, хорин, гучин, ...)
    tens_combined = ["", "арван", "хорин", "гучин", "дөчин", "тавин", "жаран", "далан", "наян", "ерэн"]
    
    def convert_below_hundred(num, is_combined=False):
        """100-аас доош тоог хөрвүүлнэ"""
        if num == 0:
            return ""
        elif num < 10:
            return ones_combined[num] if is_combined else ones[num]
        elif num == 10:
            return "арван" if is_combined else "арав"
        elif num < 20:
            return "арван " + ones[num % 10]
        else:
            ten_digit = num // 10
            one_digit = num % 10
            if one_digit == 0:
                return tens_combined[ten_digit] if is_combined else tens[ten_digit]
            else:
                return tens_combined[ten_digit] + " " + (ones_combined[one_digit] if is_combined else ones[one_digit])
        return ""
    
    def convert_below_thousand(num, is_combined=False):
        """1000-аас доош тоог хөрвүүлнэ"""
        if num == 0:
            return ""
        elif num < 100:
            return convert_below_hundred(num, is_combined)
        else:
            hundred_part = num // 100
            remainder = num % 100
            # Зуутай хэлбэр: зуу/зуун
            if remainder == 0 and not is_combined:
                hundred_suffix = "зуу"
            else:
                hundred_suffix = "зуун"
            
            if hundred_part == 1:
                result = hundred_suffix
            else:
                result = ones_combined[hundred_part] + " " + hundred_suffix
            
            if remainder > 0:
                result += " " + convert_below_hundred(remainder, is_combined)
            return result
    
    # Том тоонуудыг хөрвүүлэх
    result = []
    
    # Тэрбум (billion)
    if n >= 1_000_000_000:
        billion_part = n // 1_000_000_000
        n %= 1_000_000_000
        if billion_part == 1:
            result.append("тэрбум")
        else:
            result.append(convert_below_thousand(billion_part, is_combined=True) + " тэрбум")
    
    # Сая (million)
    if n >= 1_000_000:
        million_part = n // 1_000_000
        n %= 1_000_000
        if million_part == 1:
            result.append("сая")
        else:
            result.append(convert_below_thousand(million_part, is_combined=True) + " сая")
    
    # Мянга (thousand) - "мянга" л байна, "мянган" гэж байхгүй
    if n >= 1000:
        thousand_part = n // 1000
        n %= 1000
        if thousand_part == 1:
            result.append("мянга")
        else:
            result.append(convert_below_thousand(thousand_part, is_combined=True) + " мянга")
    
    # Үлдсэн хэсэг
    if n > 0:
        result.append(convert_below_thousand(n, is_combined=False))
    
    return " ".join(result)
 
 
def phone_number_to_mongolian(phone):
    """
    Утасны дугаарыг (8 оронтой тоо) хоёр хоёр оронгоор нь салгаж монгол үгээр хөрвүүлнэ.
    Жишээ: 99938453 эсвэл 9993-8453 → "ерэн ес, гучин гурав, наян дөрөв, тавин гурав"
    """
    # Зураас болон хоосон зайг арилгаж зөвхөн цифрүүдийг авах
    digits = re.sub(r'[-\s]', '', str(phone))
    
    # 8 оронтой тоо эсэхийг шалгах
    if not digits.isdigit() or len(digits) != 8:
        return None  # Утасны дугаар биш
    
    # Хоёр хоёр оронгоор салгах
    pairs = [digits[i:i+2] for i in range(0, 8, 2)]
    
    # Хоёр оронтой тоог монгол үгээр хөрвүүлэх
    ones = ["тэг", "нэг", "хоёр", "гурав", "дөрөв", "тав", "зургаа", "долоо", "найм", "ес"]
    tens = ["", "арван", "хорин", "гучин", "дөчин", "тавин", "жаран", "далан", "наян", "ерэн"]
    
    def two_digit_to_mongolian(num_str):
        num = int(num_str)
        if num == 0:
            return "тэг тэг"
        elif num < 10:
            # 01, 02, ... гэсэн тохиолдолд "тэг нэг", "тэг хоёр" гэх мэт
            return "тэг " + ones[num]
        elif num == 10:
            return "арав"
        elif num < 20:
            return "арван " + ones[num % 10]
        else:
            ten_digit = num // 10
            one_digit = num % 10
            if one_digit == 0:
                return tens[ten_digit][:-1] if tens[ten_digit].endswith('н') else tens[ten_digit]  # арван->арав
            else:
                return tens[ten_digit] + " " + ones[one_digit]
    
    result_parts = [two_digit_to_mongolian(pair) for pair in pairs]
    return ", ".join(result_parts)
 
 
def convert_numbers_in_text(text):
    """
    Текст дотроос бүх тоонуудыг олж монгол үгээр хөрвүүлнэ.
    
    - 8 оронтой тоог (утасны дугаар) хоёр хоёр оронгоор салгаж хөрвүүлнэ
    - Бусад тоонуудыг ердийн журмаар хөрвүүлнэ
    
    Жишээ:
    - "Миний утас 9993-8453 юм" → "Миний утас ерэн ес, ерэн гурав, наян дөрөв, тавин гурав юм"
    - "2024 онд 150 хүн ирсэн" → "хоёр мянга хорин дөрөв онд зуун тавь хүн ирсэн"
    """
    
    # Эхлээд 8 оронтой утасны дугааруудыг (зураас/зайтай) олж хөрвүүлэх
    # Pattern: 4 орон + (зураас эсвэл зай) + 4 орон
    phone_pattern = r'\b(\d{4})([-\s])(\d{4})\b'
    
    def replace_phone_with_separator(match):
        digits = match.group(1) + match.group(3)
        result = phone_number_to_mongolian(digits)
        if result:
            return result
        return match.group(0)
    
    text = re.sub(phone_pattern, replace_phone_with_separator, text)
    
    # Дараа нь бүх тоонуудыг олж хөрвүүлэх
    # 8 оронтой зүгээр тоог утасны дугаар гэж үзэх
    number_pattern = r'\b(\d+)\b'
    
    def replace_number(match):
        num_str = match.group(1)
        
        # 8 оронтой тоог утасны дугаар гэж үзэх
        if len(num_str) == 8:
            result = phone_number_to_mongolian(num_str)
            if result:
                return result
        
        # Бусад тоонуудыг ердийн журмаар хөрвүүлэх
        try:
            num = int(num_str)
            if num > 1_000_000_000:
                return ''
            return number_to_mongolian(num)
        except (ValueError, IndexError):
            return match.group(0)
    
    return re.sub(number_pattern, replace_number, text)

    

# Backwards-compatible wrapper names (so rest of refactor code is unchanged)
def int_to_mn(n: int) -> str:
    return number_to_mongolian(n)

def digits_to_mn_pairs_8(digits: str) -> str:
    """
    Only used for 8+ digit numbers (phone-like):
    reads as 2-digit pairs:
      99112233 -> ерэн ес арван нэг хорин хоёр гучин гурав
    """
    parts = []
    start = len(digits) % 2
    if start:
        parts.append(DIGIT_WORDS[digits[0]])
    for i in range(start, len(digits), 2):
        pair = digits[i:i + 2]
        if pair[0] == '0':
            parts.append(DIGIT_WORDS['0'] + ' ' + DIGIT_WORDS[pair[1]])
        else:
            parts.append(int_to_mn(int(pair)))
    return ' '.join(parts)

def ablative(word: str) -> str:
    """word + аас/ээс with simple vowel harmony."""
    if word.endswith('ь'):
        return word[:-1] + 'иас'
    back_vowels = set('аоуАОУ')
    for ch in reversed(word):
        if ch in back_vowels:
            return word + 'аас'
        if ch in set('эөүиеёЭӨҮИЕЁ'):
            return word + 'ээс'
    return word + 'аас'

_CYR = re.compile(r'[А-ЯӨҮЁа-яөүё]')

def _pad(text: str, start: int, end: int, word: str) -> str:
    pre = text[start - 1] if start > 0 else ''
    post = text[end] if end < len(text) else ''
    if pre and _CYR.match(pre):
        word = ' ' + word
    if post and _CYR.match(post):
        word = word + ' '
    return word

# ── Fractions & decimals ────────────────────────────────────────────────────

def fraction_to_mn(numer: int, denom: int) -> str | None:
    if denom == 0:
        return None
    return f"{int_to_mn(denom)}ны {int_to_mn(numer)}"

def decimal_to_mn(int_part: int, frac_digits: str) -> str:
    frac_digits = frac_digits.strip()
    if not frac_digits:
        return int_to_mn(int_part)
    trimmed = frac_digits.lstrip('0')
    if trimmed == '':
        return int_to_mn(int_part)

    denom = 10 ** len(frac_digits)
    numer = int(trimmed)
    return f"{int_to_mn(int_part)} {int_to_mn(denom)}ны {int_to_mn(numer)}"

# ── Date/time/legal/percent normalization ───────────────────────────────────

def _month_day_to_mn(mm: int, dd: int) -> str | None:
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return f"{int_to_mn(mm)} сарын {int_to_mn(dd)}"

def _year_month_day_to_mn(yyyy: int, mm: int, dd: int) -> str | None:
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return f"{int_to_mn(yyyy)} оны {int_to_mn(mm)} сарын {int_to_mn(dd)}"

def normalize_numbers(text: str) -> str:
    
    

    
    # Percent first so "25.1%" is not caught by decimals
    def repl_percent_decimal(m):
        word = f"{decimal_to_mn(int(m.group(1)), m.group(2))} хувь"
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d+)\.(\d+)\s*%(?!\d)', repl_percent_decimal, text)

    def repl_percent_int(m):
        word = f"{int_to_mn(int(m.group(1)))} хувь"
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d+)\s*%(?!\d)', repl_percent_int, text)

    # Time ranges 10:00-16:00
    def repl_time_range(m):
        h1, h2 = int(m.group(1)), int(m.group(2))
        return int_to_mn(h1) + 'өөс ' + int_to_mn(h2) + ' цаг хүртэл'
    text = re.sub(r'(\d{1,2}):\d{2}-(\d{1,2}):\d{2}', repl_time_range, text)

    # Single time 10:00
    def repl_time(m):
        return int_to_mn(int(m.group(1))) + ' цаг'
    text = re.sub(r'(\d{1,2}):\d{2}', repl_time, text)

    # Time with dot 09.30 цагт
    def repl_time_dot(m):
        hh = int(m.group(1))
        mm = int(m.group(2))
        word = f"{int_to_mn(hh)} цаг {int_to_mn(mm)} минутанд"
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d{1,2})\.(\d{2})\s*цагт\b', repl_time_dot, text)

    # Full date 2013.02.07ны
    def repl_ymd(m):
        yyyy = int(m.group(1))
        mm = int(m.group(2))
        dd = int(m.group(3))
        tail = m.group(4) or ''
        base = _year_month_day_to_mn(yyyy, mm, dd)
        if base is None:
            return m.group(0)
        return _pad(text, m.start(), m.end(), (base + tail).strip())
    text = re.sub(r'(?<!\d)(\d{4})\.(\d{2})\.(\d{2})(\s*(?:ны|нд| өдөр|он сар өдөр)?)', repl_ymd, text)

    # Month-day 03.14 (optionally "он сар өдөр")
    def repl_md(m):
        mm = int(m.group(1))
        dd = int(m.group(2))
        tail = m.group(3) or ''
        base = _month_day_to_mn(mm, dd)
        if base is None:
            return m.group(0)
        return _pad(text, m.start(), m.end(), (base + tail).strip())
    text = re.sub(r'(?<!\d)(\d{2})\.(\d{2})(\s*он сар өдөр)?', repl_md, text)

    # Legal numbering 7.1.11
    def repl_legal(m):
        a = int(m.group(1))
        b = int(m.group(2))
        c = int(m.group(3))
        word = f"{int_to_mn(a)}гийн {int_to_mn(b)}ийн {int_to_mn(c)}"
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{1,3})(?!\d)', repl_legal, text)

    # Fractions 1/10
    def repl_fraction(m):
        numer, denom = int(m.group(1)), int(m.group(2))
        word = fraction_to_mn(numer, denom)
        if word is None:
            return m.group(0)
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)', repl_fraction, text)

    # Ranges 50-55
    def repl_range(m):
        a, b = int(m.group(1)), int(m.group(2))
        return ablative(int_to_mn(a)) + ' ' + int_to_mn(b)
    text = re.sub(r'(?<!\d)(\d{1,3})-(\d{1,3})(?!\d)', repl_range, text)

    # Decimals 8.6
    def repl_decimal(m):
        word = decimal_to_mn(int(m.group(1)), m.group(2))
        return _pad(text, m.start(), m.end(), word)
    text = re.sub(r'(?<!\d)(\d+)\.(\d+)(?!\d)', repl_decimal, text)
    text = convert_numbers_in_text(text)
    return text

# ── Text cleaning ───────────────────────────────────────────────────────────

def clean_line(line: str) -> str:
    line = line.strip()
    line = line.strip('"')
    line = line.lstrip(', ').strip()
    return line

def normalize_sentence(sent: str) -> str:
    sent = sent.strip().strip('"').lstrip(', ').strip()
    sent = re.sub(r'\s+', ' ', sent)
    sent = normalize_numbers(sent)
    sent = re.sub(r'\s+', ' ', sent).strip()
    sent = sent.rstrip(',').strip()
    if sent:
        sent = sent[0].upper() + sent[1:]
    return sent

# ── Sentence reconstruction ─────────────────────────────────────────────────

MN_END = re.compile(r'[.?!]\s*$')

def is_continuation(prev: str, curr: str) -> bool:
    if not prev or not curr:
        return False
    if not MN_END.search(prev):
        return True
    if re.match(r'^[а-яөүёa-z]', curr):
        return True
    return False

def join_fragments(lines: list) -> list:
    cleaned = [clean_line(l) for l in lines]
    cleaned = [l for l in cleaned if l]
    if not cleaned:
        return []

    groups = []
    current = cleaned[0]
    for line in cleaned[1:]:
        if is_continuation(current, line):
            current = current + ' ' + line
        else:
            groups.append(current)
            current = line
    groups.append(current)
    return groups

_ENDINGS = [
    'болжээ', 'байлаа', 'байгаа', 'гэнэ', 'гэв', 'ажээ', 'билээ',
    'эхэллээ', 'өглөө', 'гарлаа', 'орлоо', 'болоод байна'
]
_ENDINGS_RE = re.compile(r'(' + '|'.join(re.escape(e) for e in _ENDINGS) + r')\.?\s+(?=[А-ЯӨҮЁA-Z])')

def split_sentences(text: str) -> list:
    text = re.sub(r'(?<=[а-яөүёa-z])\.(?=[А-ЯӨҮЁA-Z])', '. ', text)
    text = _ENDINGS_RE.sub(r'\1. ', text)
    parts = re.split(r'(?<=[.?!])\s+(?=[А-ЯӨҮЁA-Z])', text)
    return [p.strip() for p in parts if p.strip()]

# ── Noise detection ─────────────────────────────────────────────────────────

NOISE_PATTERNS = [
    re.compile(r'^Т\.Америк'),
    re.compile(r'^\d+$'),
    re.compile(r'^[^\w]+$'),
]
_ENGLISH_RE = re.compile(r'[a-zA-Z]')

def has_english(sent: str) -> bool:
    return bool(_ENGLISH_RE.search(sent))

def is_noise(sent: str) -> bool:
    return any(p.match(sent) for p in NOISE_PATTERNS)

MIN_WORDS = 3
MAX_WORDS = 20

_SPLIT_AT_PUNCT = re.compile(r'[,;]$')
_SPLIT_BEFORE_CONJ = re.compile(
    r'^(болон|бөгөөд|харин|тэгвэл|мөн|гэхдээ|учир|хэрэв|гэсэн|гэж|гэнэ|байна|байлаа|ажээ|аж|гэв|юм)$'
)

def split_long(sent: str) -> list:
    words = sent.split()
    if len(words) <= MAX_WORDS:
        return [sent]

    chunks = []
    while words:
        if len(words) <= MAX_WORDS:
            chunks.append(' '.join(words))
            break

        best = None
        for i in range(MAX_WORDS, 11, -1):
            if _SPLIT_AT_PUNCT.search(words[i - 1]):
                best = i
                break

        if best is None:
            for i in range(MAX_WORDS, 11, -1):
                if _SPLIT_BEFORE_CONJ.match(words[i - 1].strip(',.;')):
                    best = i - 1
                    break

        if best is None:
            best = MAX_WORDS

        chunks.append(' '.join(words[:best]))
        words = words[best:]

    _LONE_INITIAL = re.compile(r'(?iu)\b[а-яёөүa-z]\.$')

    merged = []
    for chunk in chunks:
        if merged and _LONE_INITIAL.search(merged[-1]):
            merged[-1] = merged[-1] + ' ' + chunk
        else:
            merged.append(chunk)

    result = []
    for chunk in merged:
        chunk = chunk.lstrip(', ').strip()
        if chunk:
            chunk = chunk[0].upper() + chunk[1:]
            result.append(chunk)
    return result

# ── Main pipeline ───────────────────────────────────────────────────────────

def main(input_path: str, output_path: str):
    raw_lines = []
    if Path(input_path).suffix.lower() == '.txt':
        with open(input_path, encoding='utf-8') as f:
            raw_lines = [line.strip() for line in f if line.strip()]
    else:
        with open(input_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row:
                    raw_lines.append(row[0])

    print(f"[1] Read         : {len(raw_lines):>6} raw rows")

    joined = join_fragments(raw_lines)
    print(f"[2] After joining: {len(joined):>6} groups")

    sentences = []
    for group in joined:
        sentences.extend(split_sentences(group))
    print(f"[3] After split  : {len(sentences):>6} sentences")

    seen = set()
    clean = []
    stats = {'noise': 0, 'english': 0, 'too_short': 0, 'dup': 0}

    for sent in sentences:
        if is_noise(sent):
            stats['noise'] += 1
            continue
        if has_english(sent):
            stats['english'] += 1
            continue

        normalized = normalize_sentence(sent)
        if not normalized:
            continue

        for chunk in split_long(normalized):
            words = chunk.split()
            if len(words) < MIN_WORDS:
                stats['too_short'] += 1
                continue

            if chunk in seen:
                stats['dup'] += 1
                continue

            seen.add(chunk)
            clean.append(chunk)

    print(f"[4] Filtered out : noise={stats['noise']}  english={stats['english']}  short={stats['too_short']}  dup={stats['dup']}")
    print(f"[5] Final output : {len(clean):>6} clean sentences")

    out_path = Path(output_path)
    if out_path.suffix.lower() == '.csv':
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['text'])
            for sent in clean:
                writer.writerow([sent])
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            for sent in clean:
                f.write(sent + '\n')

    print(f"[6] Saved to     : {output_path}")

"""if __name__ == '__main__':
    inp = sys.argv[1] if len(sys.argv) > 1 else 'test_input.txt'
    inp_path = Path(inp)

    if inp_path.is_dir():
        txt_files = sorted(inp_path.glob('*.txt'))
        if not txt_files:
            print(f"No .txt files found in {inp_path}")
            sys.exit(1)
        print(f"Found {len(txt_files)} .txt files in '{inp_path}'")
        for txt_file in txt_files:
            print(f"\n=== Processing: {txt_file.name} ===")
            final_out = str(txt_file.with_name(txt_file.stem + '_clean.txt'))
            pre_out   = str(txt_file.with_name(txt_file.stem + '_preclean.txt'))
            pre_clean_main(str(txt_file), pre_out)
            main(pre_out, final_out)
    else:
        final_out = sys.argv[2] if len(sys.argv) > 2 else str(inp_path.with_suffix('')) + '_clean.txt'
        pre_out   = str(Path(final_out).with_suffix('')) + '_preclean.txt'
        pre_clean_main(inp, pre_out)
        main(pre_out, final_out)"""