import io
import os
import re
import logging
from typing import Optional

from telegram import Update, Document
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
]

MATH_TOPIC_HINTS = {
    "дроб": "Давай вспомним: у дроби есть числитель и знаменатель. Как ты думаешь, что показывает знаменатель?",
    "периметр": "Периметр — это сумма длин всех сторон. Какие стороны у фигуры нужно сложить?",
    "площад": "Площадь прямоугольника находят умножением длины на ширину. Какие числа в задаче отвечают за длину и ширину?",
    "уравн": "В уравнении нужно найти неизвестное число. Какое действие поможет проверить, что равенство верное?",
    "делен": "При делении важно понять, на сколько равных частей делим. Что в задаче делится и на сколько частей?",
    "умнож": "Умножение удобно, когда одинаковые числа повторяются несколько раз. Какие одинаковые слагаемые ты видишь?",
    "задач": "Давай сначала выделим главное: что известно и что нужно найти?",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())



def looks_like_provocation(text: str) -> bool:
    lowered = normalize_text(text)
    return any(re.search(pattern, lowered) for pattern in PROVOCATION_PATTERNS)



def detect_topic_hint(text: str) -> Optional[str]:
    lowered = normalize_text(text)
    for key, hint in MATH_TOPIC_HINTS.items():
        if key in lowered:
            return hint
    return None



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
        return "Не удалось распознать JPG: не установлены Pillow и/или pytesseract."
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image, lang="rus+eng").strip()
        return text if text else "На изображении не удалось распознать текст."
    except Exception as exc:
        logger.exception("Image OCR error: %s", exc)
        return "Не удалось обработать изображение."



def build_tutor_reply(user_text: str) -> str:
    cleaned = user_text.strip()
    topic_hint = detect_topic_hint(cleaned)

    if looks_like_provocation(cleaned):
        return (
            "Я помогу тебе разобраться, но не дам готовый ответ. 🙂\n\n"
            "Давай решим это по шагам, чтобы ты сам(а) понял(а), как делать такие задания.\n\n"
            "Подумай вот над чем:\n"
            "1) Что известно в задаче?\n"
            "2) Что нужно найти?\n"
            "3) Какое действие подходит первым?\n\n"
            "Напиши мне сначала, что известно в условии, и я помогу со следующим шагом."
        )

    if len(cleaned) < 8:
        return (
            "Давай разберёмся вместе. 🙂\n\n"
            "Напиши задачу полностью или пришли файл/фото задания.\n\n"
            "Сначала мы поймём условие, потом выберем действие и сделаем первый шаг вместе."
        )

    base_explanation = (
        topic_hint
        if topic_hint
        else "Давай сначала спокойно разберём условие и найдём первый шаг решения."
    )

    return (
        "Ты молодец, что пробуешь разобраться. 🙂\n\n"
        f"{base_explanation}\n\n"
        "Ответь себе или мне на вопросы:\n"
        "1) Какие числа или данные даны?\n"
        "2) Что именно нужно найти?\n"
        "3) Какое действие кажется самым подходящим сначала?\n\n"
        "Сделай только первый шаг и пришли мне его — я проверю и дам следующую подсказку."
    )



def truncate_text(text: str, max_len: int = 3500) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n[Текст сокращён]"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я помогу с математикой за 5 класс.\n\n"
        "Я не даю готовые ответы, зато объясняю тему простыми словами, задаю наводящие вопросы и помогаю прийти к решению самостоятельно.\n\n"
        "Ты можешь:\n"
        "- написать задачу текстом\n"
        "- отправить PDF\n"
        "- отправить Word-файл (.docx)\n"
        "- отправить фото задания (.jpg, .jpeg, .png)"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Как я работаю:\n\n"
        "1) читаю задачу или файл\n"
        "2) помогаю понять тему\n"
        "3) даю подсказку вместо готового ответа\n"
        "4) проверяю твой следующий шаг\n\n"
        "Пришли текст задания или файл, и начнём."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text or ""
    reply = build_tutor_reply(user_text)
    await update.message.reply_text(reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document: Document = update.message.document
    file_name = (document.file_name or "").lower()

    telegram_file = await context.bot.get_file(document.file_id)
    file_bytes = await telegram_file.download_as_bytearray()
    extracted_text = ""

    if file_name.endswith(".pdf"):
        extracted_text = extract_text_from_pdf(bytes(file_bytes))
    elif file_name.endswith(".docx"):
        extracted_text = extract_text_from_docx(bytes(file_bytes))
    else:
        await update.message.reply_text(
            "Я сейчас поддерживаю файлы PDF и DOCX.\n"
            "Если у тебя изображение задания, отправь его как фото или JPG/PNG."
        )
        return

    extracted_text = truncate_text(extracted_text)

    reply = (
        "Я прочитал файл и помогу тебе разобраться без готового ответа. 🙂\n\n"
        f"Что удалось извлечь из файла:\n\n{extracted_text}\n\n"
        "Теперь давай начнём с первого шага:\n"
        "1) О чём это задание?\n"
        "2) Что в нём уже известно?\n"
        "3) Что нужно найти?\n\n"
        "Напиши свои мысли, и я помогу дальше."
    )
    await update.message.reply_text(truncate_text(reply, 4000))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    file_bytes = await telegram_file.download_as_bytearray()

    extracted_text = truncate_text(extract_text_from_image(bytes(file_bytes)))
    reply = (
        "Я посмотрел фото задания. 🙂\n\n"
        f"Вот что удалось распознать:\n\n{extracted_text}\n\n"
        "Давай не искать готовый ответ, а сначала поймём задачу.\n"
        "Скажи, какие данные ты уже видишь в условии и что нужно найти?"
    )
    await update.message.reply_text(truncate_text(reply, 4000))


async def handle_image_as_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document: Document = update.message.document
    file_name = (document.file_name or "").lower()

    if not any(file_name.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
        return

    telegram_file = await context.bot.get_file(document.file_id)
    file_bytes = await telegram_file.download_as_bytearray()
    extracted_text = truncate_text(extract_text_from_image(bytes(file_bytes)))

    await update.message.reply_text(
        truncate_text(
            "Я обработал изображение из файла. 🙂\n\n"
            f"Распознанный текст:\n\n{extracted_text}\n\n"
            "Теперь попробуй сказать, какая тема здесь используется: дроби, деление, площадь, периметр или что-то другое?",
            4000,
        )
    )


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я могу помочь с текстом задачи, PDF, DOCX и JPG/PNG.\n"
        "Пришли задание, и мы разберём его по шагам."
    )



def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Set BOT_TOKEN in Railway Variables.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(MessageHandler(filters.Document.FileExtension("docx"), handle_document))
    application.add_handler(
        MessageHandler(
            filters.Document.FileExtension("jpg")
            | filters.Document.FileExtension("jpeg")
            | filters.Document.FileExtension("png"),
            handle_image_as_document,
        )
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.ALL, fallback))

    logger.info("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
