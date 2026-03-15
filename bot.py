import io
import os
import re
import logging
from typing import Optional

from telegram import Update, Document, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📘 Объясни тему"), KeyboardButton("🧠 Решим по шагам")],
        [KeyboardButton("📝 Проверить мой шаг"), KeyboardButton("📎 Отправить файл")],
        [KeyboardButton("🎯 Темы 5 класса"), KeyboardButton("🌟 Поддержка")],
    ],
    resize_keyboard=True,
)

TOPICS_MENU_TEXT = (
    "🎯 Темы, с которыми я могу помочь:\n\n"
    "• натуральные числа\n"
    "• сложение и вычитание\n"
    "• умножение и деление\n"
    "• порядок действий\n"
    "• уравнения\n"
    "• дроби\n"
    "• периметр\n"
    "• площадь\n"
    "• текстовые задачи\n\n"
    "Напиши тему или пришли задание, и мы разберём его по шагам."
)

PRAISES = [
    "Хорошее начало 🙂",
    "Ты молодец, что пытаешься разобраться 🌟",
    "Отличная работа, идём дальше маленькими шагами 👍",
    "Не спешим, у тебя получится 💛",
]

PROVOCATION_PATTERNS = [
    r"готовый ответ",
    r"просто ответ",
    r"дай ответ",
    r"без объяснений",
    r"реши за меня",
    r"сделай за меня",
    r"мне срочно",
    r"только результат",
    r"не объясняй",
    r"мне некогда",
    r"скажи правильный ответ",
    r"можно просто число",
]

TOPIC_HINTS = {
    "дроб": (
        "Дробь показывает часть целого. У неё есть числитель и знаменатель.",
        [
            "Что показывает знаменатель — на сколько частей разделили целое или сколько частей взяли?",
            "Что показывает числитель?",
        ],
        "Попробуй сначала назвать числитель и знаменатель.",
    ),
    "периметр": (
        "Периметр — это сумма длин всех сторон фигуры.",
        [
            "Сколько сторон у фигуры?",
            "Какие длины нужно сложить?",
        ],
        "Выпиши длины всех сторон, которые надо сложить.",
    ),
    "площад": (
        "Площадь прямоугольника обычно находят так: длину умножают на ширину.",
        [
            "Какие числа в задаче подходят на роль длины и ширины?",
            "Какое действие здесь нужно — сложение или умножение?",
        ],
        "Напиши, какие два числа нужно умножить.",
    ),
    "уравн": (
        "В уравнении нужно найти неизвестное число так, чтобы равенство стало верным.",
        [
            "Какое число неизвестно?",
            "Какой обратный шаг поможет его найти?",
        ],
        "Попробуй сначала назвать неизвестное и действие рядом с ним.",
    ),
    "делен": (
        "Деление помогает разделить число на равные части или узнать, сколько раз одно число содержится в другом.",
        [
            "Что в задаче делят?",
            "На сколько равных частей делят?",
        ],
        "Напиши, какое число делим и на что делим.",
    ),
    "умнож": (
        "Умножение удобно, когда одинаковые числа повторяются несколько раз.",
        [
            "Какие одинаковые слагаемые можно заменить умножением?",
            "Сколько раз повторяется число?",
        ],
        "Попробуй превратить повторяющееся сложение в умножение.",
    ),
    "порядок": (
        "В выражениях важно помнить порядок действий: сначала скобки, потом умножение и деление, потом сложение и вычитание.",
        [
            "Есть ли в выражении скобки?",
            "Какое действие нужно выполнить первым?",
        ],
        "Напиши, какое действие ты выполнишь первым.",
    ),
    "задач": (
        "В текстовой задаче сначала важно понять условие: что известно и что нужно найти.",
        [
            "Какие данные уже есть в задаче?",
            "Что именно нужно найти?",
        ],
        "Напиши отдельно: «известно» и «нужно найти».",
    ),
}

QUICK_TOPIC_RESPONSES = {
    "📘 объясни тему": "Напиши тему, например: дроби, периметр, площадь, уравнения или порядок действий.",
    "🧠 решим по шагам": "Пришли задачу текстом или файлом. Я не дам готовый ответ, но помогу сделать первый шаг.",
    "📝 проверить мой шаг": "Напиши свой первый шаг или вычисление, а я мягко проверю и дам следующую подсказку.",
    "📎 отправить файл": "Отправь PDF, DOCX, JPG или PNG. Я помогу понять условие и начать решение.",
    "🎯 темы 5 класса": TOPICS_MENU_TEXT,
    "🌟 поддержка": "Ты не обязан(а) решить всё сразу. Давай сделаем только один маленький шаг, и дальше станет легче 🙂",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())



def looks_like_provocation(text: str) -> bool:
    lowered = normalize_text(text)
    return any(re.search(pattern, lowered) for pattern in PROVOCATION_PATTERNS)



def choose_praise(text: str) -> str:
    text = normalize_text(text)
    if any(word in text for word in ["не понимаю", "сложно", "не получается", "трудно"]):
        return "Ничего страшного, это нормально, когда тема кажется сложной 💛"
    if any(word in text for word in ["я сделал", "мой шаг", "я думаю", "получилось"]):
        return "Здорово, что ты попробовал(а) сам(а) 🌟"
    return PRAISES[0]



def detect_topic_pack(text: str):
    lowered = normalize_text(text)
    for key, pack in TOPIC_HINTS.items():
        if key in lowered:
            return pack
    return None



def truncate_text(text: str, max_len: int = 3500) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n[Текст сокращён]"



def extract_text_from_pdf(file_bytes: bytes) -> str:
    if fitz is None:
        return "Не удалось прочитать PDF: библиотека PyMuPDF не установлена."
    try:
        text_parts = []
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                text_parts.append(page.get_text())
        text = "\n".join(text_parts).strip()
        return text if text else "В PDF не найден текст. Возможно, это скан."
    except Exception as exc:
        logger.exception("PDF parse error: %s", exc)
        return "Не удалось прочитать PDF-файл."



def extract_text_from_docx(file_bytes: bytes) -> str:
    if DocxDocument is None:
        return "Не удалось прочитать Word-файл: библиотека python-docx не установлена."
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        return text if text else "В Word-файле не найден текст."
    except Exception as exc:
        logger.exception("DOCX parse error: %s", exc)
        return "Не удалось прочитать Word-файл."



def extract_text_from_image(file_bytes: bytes) -> str:
    if Image is None or pytesseract is None:
        return "Не удалось распознать изображение: не установлены Pillow и/или pytesseract."
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image, lang="rus+eng").strip()
        return text if text else "На изображении не удалось распознать текст."
    except Exception as exc:
        logger.exception("Image OCR error: %s", exc)
        return "Не удалось обработать изображение."



def build_provocation_reply() -> str:
    return (
        "Я не дам готовый ответ, но обязательно помогу тебе разобраться 🙂\n\n"
        "Давай сделаем по-честному и по-умному:\n"
        "1) найдём, что известно;\n"
        "2) поймём, что нужно найти;\n"
        "3) выберем первое действие.\n\n"
        "Напиши сначала, что дано в задаче, и я помогу с первым шагом."
    )



def build_tutor_reply(user_text: str) -> str:
    cleaned = user_text.strip()
    lowered = normalize_text(cleaned)

    if lowered in QUICK_TOPIC_RESPONSES:
        return QUICK_TOPIC_RESPONSES[lowered]

    if looks_like_provocation(cleaned):
        return build_provocation_reply()

    if len(cleaned) < 6:
        return (
            "Давай разберёмся вместе 🙂\n\n"
            "Напиши задачу полностью или пришли файл/фото.\n"
            "Сначала мы поймём условие, а потом выберем первый шаг."
        )

    praise = choose_praise(cleaned)
    topic_pack = detect_topic_pack(cleaned)

    if topic_pack:
        explanation, questions, next_step = topic_pack
        return (
            f"{praise}\n\n"
            f"{explanation}\n\n"
            "Подумай вот над чем:\n"
            f"1) {questions[0]}\n"
            f"2) {questions[1]}\n\n"
            f"Твой следующий шаг: {next_step}"
        )

    if any(word in lowered for word in ["мой шаг", "я сделал", "я думаю", "получилось", "ответил"]):
        return (
            "Здорово, что ты показал свой ход мысли 🌟\n\n"
            "Теперь давай проверим его спокойно:\n"
            "1) Все ли данные из условия ты использовал(а)?\n"
            "2) Подходит ли выбранное действие к вопросу задачи?\n"
            "3) Не пропущен ли какой-то промежуточный шаг?\n\n"
            "Пришли один свой шаг ещё раз, и я помогу проверить именно его."
        )

    return (
        f"{praise}\n\n"
        "Давай сначала спокойно поймём условие задачи.\n\n"
        "Ответь на 3 вопроса:\n"
        "1) Что известно?\n"
        "2) Что нужно найти?\n"
        "3) Какое действие кажется первым: сложение, вычитание, умножение или деление?\n\n"
        "Сделай только первый шаг и пришли мне его — я помогу дальше."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я твой помощник по математике за 5 класс 🙂\n\n"
        "Я объясняю тему простыми словами, задаю наводящие вопросы и помогаю решать по шагам.\n"
        "Я не даю готовые ответы, зато помогаю понять, как решать самому.\n\n"
        "Выбери кнопку ниже или пришли задачу.",
        reply_markup=MAIN_MENU,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Как со мной заниматься:\n\n"
        "• пришли задачу текстом\n"
        "• или отправь PDF / DOCX / JPG / PNG\n"
        "• я помогу понять условие\n"
        "• дам подсказку вместо готового ответа\n"
        "• проверю твой шаг\n\n"
        "Давай начнём с одного маленького шага 🙂",
        reply_markup=MAIN_MENU,
    )


async def topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TOPICS_MENU_TEXT, reply_markup=MAIN_MENU)


async def parents_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Для родителей:\n\n"
        "Этот бот не даёт готовые ответы и не помогает списывать.\n"
        "Он объясняет тему простыми словами, разбивает задачу на шаги и помогает ребёнку прийти к решению самостоятельно.\n\n"
        "Поддерживаются текст, PDF, DOCX, JPG и PNG.",
        reply_markup=MAIN_MENU,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text or ""
    reply = build_tutor_reply(user_text)
    await update.message.reply_text(reply, reply_markup=MAIN_MENU)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document: Document = update.message.document
    file_name = (document.file_name or "").lower()

    telegram_file = await context.bot.get_file(document.file_id)
    file_bytes = await telegram_file.download_as_bytearray()

    if file_name.endswith(".pdf"):
        extracted_text = extract_text_from_pdf(bytes(file_bytes))
    elif file_name.endswith(".docx"):
        extracted_text = extract_text_from_docx(bytes(file_bytes))
    elif any(file_name.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
        extracted_text = extract_text_from_image(bytes(file_bytes))
    else:
        await update.message.reply_text(
            "Я сейчас поддерживаю PDF, DOCX, JPG и PNG.\n"
            "Попробуй отправить файл в одном из этих форматов.",
            reply_markup=MAIN_MENU,
        )
        return

    extracted_text = truncate_text(extracted_text)
    reply = (
        "Я посмотрел файл 🙂\n\n"
        f"Вот что удалось прочитать:\n\n{extracted_text}\n\n"
        "Теперь давай начнём с понимания задания:\n"
        "1) О чём эта задача?\n"
        "2) Что в ней уже известно?\n"
        "3) Что нужно найти?\n\n"
        "Напиши только первый шаг, а я помогу дальше."
    )
    await update.message.reply_text(truncate_text(reply, 4000), reply_markup=MAIN_MENU)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    file_bytes = await telegram_file.download_as_bytearray()

    extracted_text = truncate_text(extract_text_from_image(bytes(file_bytes)))
    reply = (
        "Я посмотрел фото задания 🙂\n\n"
        f"Вот что удалось распознать:\n\n{extracted_text}\n\n"
        "Давай не искать готовый ответ, а поймём условие.\n"
        "Какие данные ты уже видишь и что нужно найти?"
    )
    await update.message.reply_text(truncate_text(reply, 4000), reply_markup=MAIN_MENU)


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я могу помочь с задачей, темой или файлом 🙂\n"
        "Выбери кнопку ниже или пришли задание.",
        reply_markup=MAIN_MENU,
    )



def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Set BOT_TOKEN in Railway Variables.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("topics", topics_command))
    application.add_handler(CommandHandler("parents", parents_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.ALL, fallback))

    logger.info("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
