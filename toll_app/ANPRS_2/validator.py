from config import *

def validate(results, lang):
    if lang == 'en':
        return validate_english(results)
    elif lang == 'ne':
        return validate_nepali(results)
    else:
        return None


def validate_english(results):
    # TTT NNNN
    # State TTT NNNN

    if not results:
        return None

    all_char = []
    state = ""
    text_part = ""
    num_part = ""

    for item in results:
        text = clean_english_text(item[1])
        if len(text) > 4 and text.isalpha() and item[2] >= OCR_THRESHOLD:
            state = text
        elif item[2] >= OCR_THRESHOLD:
            all_char.extend(list(text))

    for item in all_char:
        if len(text_part) < 3 and item.isalpha():
            text_part += item.upper()
        elif len(num_part) < 4 and item.isdigit():
            num_part += item

    if len(text_part) != 3:
        text_part = (text_part + "⨉⨉⨉")[:3]
    if len(num_part) != 4:
        num_part = (num_part + "∎∎∎∎")[:4]

    return f"{state} {text_part} {num_part}".strip()


def validate_nepali(results):
    # T NN T NNNN
    # State NNN T NNNN
    if not results:
        return None

    all_char = []
    state = ""
    text_part = ""
    num_part = ""

    for item in results:
        text = item[1]
        if len(text) > 4 and '-' in text and item[2] >= OCR_THRESHOLD:
            state = text
        elif item[2] >= OCR_THRESHOLD:
            all_char.extend(list(text))

    all_char = [clean_nepali_text(c) for c in all_char]

    for item in all_char:
        if item in NEP_ALPHA_CHAR_LIST:
            text_part += item
        elif item in NEP_DIGIT_CHAR_LIST:
            num_part += item

    number_plate_pattern = 'new' if len(text_part) < 2 else 'old'

    if len(text_part) != 2:
        text_part = (text_part + "⨉⨉")[:2]
    if len(num_part) != 7:
        num_part = ("∎∎∎∎∎∎∎" + num_part)[-7:]

    if number_plate_pattern == 'old':
        return f"{state} {text_part[0]} {num_part[1:3]} {text_part[1]} {num_part[3:]}".strip()
    else:
        return f"{state} {num_part[0:3]} {text_part[0]} {num_part[3:]}".strip()


def clean_nepali_text(text):
    translation_table = str.maketrans({
        '0': '०',
        '8': '४',
        'o': '०',
        'O': '०',
        'c': '८',
        'C': '८',
    })
    return text.translate(translation_table)


def clean_english_text(text):
    # replace characters that are commonly misread as numbers.
    # if 1 char is numeric out of 3. change it to alpha
    if sum(c.isdigit() for c in text) == 1 and len(text) == 3:
        translation_table = str.maketrans({
            '4': 'A',
            '8': 'B',
            '3': 'B',
            '0': 'D',
            # '1': 'I',
            # '2': 'Z',
            # '5': 'S',
            # '6': 'G',
            # '7': 'T',
            # '9': 'G',
        })
        return text.translate(translation_table)
    return text