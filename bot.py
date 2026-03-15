import io
import os
import re
import json
import html
import random
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegram import (
    Update,
    Document,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
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
DATA_FILE = Path(os.getenv("DATA_FILE", "user_progress.json"))
USER_PROGRESS: dict[str, dict] = {}

MAIN_REPLY_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🏠 Главное меню"), KeyboardButton("📎 Отправить файл")],
        [KeyboardButton("📝 Проверить мой шаг"), KeyboardButton("🌟 Поддержка")],
    ],
    resize_keyboard=True,
)

PRAISES = [
    "Отлично идёшь 🌟",
    "Очень хороший шаг 👍",
    "У тебя получается всё лучше и лучше ⭐",
    "Сильная попытка, продолжаем 💛",
    "Ты молодец, что думаешь сам(а) 🎉",
]

ENCOURAGEMENTS = [
    "Не страшно ошибиться — так и учатся 🙂",
    "Сделаем один маленький шаг, и станет понятнее 💛",
    "Ты не обязан(а) решить всё сразу. По шагам легче 🌈",
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
        ["Что показывает знаменатель?", "Что показывает числитель?"],
        "Назови числитель и знаменатель своей дроби.",
    ),
    "периметр": (
        "Периметр — это сумма длин всех сторон фигуры.",
        ["Сколько у фигуры сторон?", "Какие длины нужно сложить?"],
        "Выпиши длины всех сторон, которые надо сложить.",
    ),
    "площад": (
        "Площадь прямоугольника находят умножением длины на ширину.",
        ["Какие числа здесь длина и ширина?", "Какое действие подойдёт?"],
        "Напиши, какие два числа нужно умножить.",
    ),
    "уравн": (
        "В уравнении нужно найти неизвестное число, чтобы равенство стало верным.",
        ["Что здесь неизвестно?", "Какое обратное действие поможет?"],
        "Назови неизвестное и действие рядом с ним.",
    ),
    "делен": (
        "Деление помогает разделить на равные части или узнать, сколько раз одно число помещается в другом.",
        ["Что делят?", "На сколько частей делят?"],
        "Напиши, какое число делим и на что делим.",
    ),
    "умнож": (
        "Умножение удобно, когда одинаковые числа повторяются несколько раз.",
        ["Какое число повторяется?", "Сколько раз оно повторяется?"],
        "Замени повторяющееся сложение умножением.",
    ),
    "порядок": (
        "Сначала скобки, потом умножение и деление, потом сложение и вычитание.",
        ["Есть ли скобки?", "Какое действие первое?"],
        "Напиши, какое действие выполнишь первым.",
    ),
    "задач": (
        "В текстовой задаче сначала важно понять, что известно и что нужно найти.",
        ["Что уже известно?", "Что нужно найти?"],
        "Напиши отдельно: «известно» и «нужно найти».",
    ),
}

TOPICS_MENU_TEXT = (
    "🎯 Темы 5 класса:\n\n"
    "• натуральные числа\n"
    "• сложение и вычитание\n"
    "• умножение и деление\n"
    "• порядок действий\n"
    "• уравнения\n"
    "• дроби\n"
    "• периметр\n"
    "• площадь\n"
    "• текстовые задачи\n\n"
    "Выбери режим ниже или пришли своё задание."
)

@dataclass
class ExampleTask:
    text: str
    answer: int
    hint: str
    topic: str


def main_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📘 Объясни тему", callback_data="menu_topic"),
                InlineKeyboardButton("🧠 Решим по шагам", callback_data="menu_steps"),
            ],
            [
                InlineKeyboardButton("🏋️ Тренировка примеров", callback_data="train_start"),
                InlineKeyboardButton("🎯 Мини-викторина", callback_data="quiz_start"),
            ],
            [
                InlineKeyboardButton("🌟 Мой прогресс", callback_data="show_progress"),
                InlineKeyboardButton("👨‍👩‍👧 Для родителей", callback_data="parents_info"),
            ],
        ]
    )


def build_progress_bar(stars: int) -> str:
    filled = min(stars // 5, 10)
    return "★" * filled + "☆" * (10 - filled)



def default_stats() -> dict:
    return {
        "stars": 0,
        "level": 1,
        "solved_training": 0,
        "quiz_correct": 0,
        "streak": 0,
    }



def load_progress() -> None:
    global USER_PROGRESS
    if not DATA_FILE.exists():
        USER_PROGRESS = {}
        return
    try:
        USER_PROGRESS = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.exception("Failed to load progress: %s", exc)
        USER_PROGRESS = {}



def save_progress() -> None:
    try:
        DATA_FILE.write_text(
            json.dumps(USER_PROGRESS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.exception("Failed to save progress: %s", exc)



def get_user_key(update: Update) -> str:
    user = update.effective_user
    return str(user.id if user else "unknown")



def get_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    user_key = get_user_key(update)
    stored = USER_PROGRESS.setdefault(user_key, default_stats())
    stats = context.user_data.setdefault("stats", stored.copy())
    USER_PROGRESS[user_key] = stats.copy()
    return stats



def sync_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    user_key = get_user_key(update)
    stats = context.user_data.setdefault("stats", default_stats())
    USER_PROGRESS[user_key] = stats.copy()
    save_progress()
    return stats



def add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int) -> dict:
    stats = get_user_stats(update, context)
    stats["stars"] += amount
    stats["level"] = max(1, stats["stars"] // 10 + 1)
    return sync_user_stats(update, context)



def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())



def looks_like_provocation(text: str) -> bool:
    lowered = normalize_text(text)
    return any(re.search(pattern, lowered) for pattern in PROVOCATION_PATTERNS)



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



def random_praise() -> str:
    return random.choice(PRAISES)



def random_encouragement() -> str:
    return random.choice(ENCOURAGEMENTS)



def build_provocation_reply() -> str:
    return (
        "Я не дам готовый ответ, но с радостью помогу тебе дойти до него самому 🙂\n\n"
        "Давай сделаем так:\n"
        "1) найдём, что известно;\n"
        "2) поймём, что нужно найти;\n"
        "3) выберем первое действие.\n\n"
        "Напиши, что дано в задаче, и начнём с первого шага."
    )



def build_tutor_reply(user_text: str) -> str:
    cleaned = user_text.strip()
    lowered = normalize_text(cleaned)

    quick = {
        "🏠 главное меню": "Нажми кнопку ниже и выбери, чем хочешь заняться 👇",
        "📎 отправить файл": "Отправь PDF, DOCX, JPG или PNG. Я помогу понять условие и начать решение.",
        "📝 проверить мой шаг": "Напиши свой шаг или вычисление. Я проверю очень мягко и подскажу следующий шаг.",
        "🌟 поддержка": random_encouragement(),
    }
    if lowered in quick:
        return quick[lowered]

    if looks_like_provocation(cleaned):
        return build_provocation_reply()

    if len(cleaned) < 6:
        return (
            "Давай разберёмся вместе 🙂\n\n"
            "Напиши задачу полностью или пришли файл/фото.\n"
            "Сначала поймём условие, потом выберем первый шаг."
        )

    topic_pack = detect_topic_pack(cleaned)
    if topic_pack:
        explanation, questions, next_step = topic_pack
        return (
            f"{random_praise()}\n\n"
            f"{explanation}\n\n"
            "Подумай вот над чем:\n"
            f"1) {questions[0]}\n"
            f"2) {questions[1]}\n\n"
            f"Твой следующий шаг: {next_step}"
        )

    if any(word in lowered for word in ["мой шаг", "я сделал", "я думаю", "получилось", "ответил"]):
        return (
            "Здорово, что ты показал(а) свой ход мысли 🌟\n\n"
            "Проверим его спокойно:\n"
            "1) Все ли данные из условия использованы?\n"
            "2) Подходит ли выбранное действие к вопросу задачи?\n"
            "3) Нет ли пропущенного промежуточного шага?\n\n"
            "Пришли один свой шаг ещё раз, и я помогу проверить именно его."
        )

    return (
        f"{random_praise()}\n\n"
        "Давай сначала поймём условие задачи.\n\n"
        "Ответь на 3 вопроса:\n"
        "1) Что известно?\n"
        "2) Что нужно найти?\n"
        "3) Какое действие кажется первым?\n\n"
        "Сделай только первый шаг и пришли мне его — я помогу дальше."
    )



def generate_training_tasks() -> list[ExampleTask]:
    tasks = []
    for _ in range(2):
        a, b = random.randint(10, 99), random.randint(10, 99)
        tasks.append(ExampleTask(f"Сколько будет {a} + {b}?", a + b, "Сложи десятки, потом единицы.", "сложение"))
    for _ in range(1):
        a, b = random.randint(20, 99), random.randint(2, 19)
        if a < b:
            a, b = b + 20, a
        tasks.append(ExampleTask(f"Сколько будет {a} - {b}?", a - b, "Подумай, сколько нужно убрать из первого числа.", "вычитание"))
    for _ in range(1):
        a, b = random.randint(2, 9), random.randint(2, 9)
        tasks.append(ExampleTask(f"Сколько будет {a} × {b}?", a * b, "Вспомни таблицу умножения или повторяющееся сложение.", "умножение"))
    for _ in range(1):
        b = random.randint(2, 9)
        ans = random.randint(2, 9)
        a = b * ans
        tasks.append(ExampleTask(f"Сколько будет {a} ÷ {b}?", ans, "Подумай, сколько раз число делитель помещается в делимом.", "деление"))
    random.shuffle(tasks)
    return tasks



def generate_quiz_question() -> dict:
    variants = [
        {
            "question": "Что такое периметр?",
            "options": ["Сумма длин всех сторон", "Длина одной стороны", "Площадь фигуры"],
            "correct": 0,
            "explain": "Периметр — это сумма длин всех сторон фигуры.",
        },
        {
            "question": "Что делаем первым в выражении со скобками?",
            "options": ["Сложение", "Действия в скобках", "Умножение всегда первым"],
            "correct": 1,
            "explain": "Сначала выполняют действия в скобках.",
        },
        {
            "question": "Что показывает знаменатель дроби?",
            "options": ["Сколько частей взяли", "На сколько частей разделили целое", "Ответ задачи"],
            "correct": 1,
            "explain": "Знаменатель показывает, на сколько равных частей разделили целое.",
        },
        {
            "question": "Как найти площадь прямоугольника?",
            "options": ["Сложить все стороны", "Длину умножить на ширину", "Длину разделить на ширину"],
            "correct": 1,
            "explain": "Площадь прямоугольника находят умножением длины на ширину.",
        },
    ]
    return random.choice(variants)



def format_progress_text(stats: dict) -> str:
    return (
        "🌟 Твой прогресс\n\n"
        f"Уровень: <b>{stats['level']}</b>\n"
        f"Звёздочки: <b>{stats['stars']}</b>\n"
        f"Тренировок решено: <b>{stats['solved_training']}</b>\n"
        f"Верных ответов в викторине: <b>{stats['quiz_correct']}</b>\n"
        f"Серия удачных шагов: <b>{stats['streak']}</b>\n\n"
        f"Прогресс уровня: <code>{build_progress_bar(stats['stars'])}</code>"
    )



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


async def send_main_menu(target, text: str, edit: bool = False):
    if edit:
        await target.edit_message_text(text, reply_markup=main_inline_menu(), parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=main_inline_menu(), parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_user_stats(update, context)
    sync_user_stats(update, context)
    await update.message.reply_text(
        "Привет! Я твой помощник по математике за 5 класс 🙂\n\n"
        "Я объясняю тему простыми словами, помогаю решать по шагам, даю тренировку и мини-викторины.\n"
        "Я не даю готовые ответы, зато помогаю понять, как дойти до решения самому.\n\n"
        "Нажми на кнопку ниже.",
        reply_markup=MAIN_REPLY_MENU,
    )
    await update.message.reply_text(
        "<b>Главное меню</b>\n\nВыбери, чем хочешь заняться 👇",
        reply_markup=main_inline_menu(),
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Как со мной заниматься:\n\n"
        "• пришли задачу текстом\n"
        "• или отправь PDF / DOCX / JPG / PNG\n"
        "• я помогу понять условие\n"
        "• дам подсказку вместо готового ответа\n"
        "• проверю твой шаг\n"
        "• дам тренировку или мини-викторину\n\n"
        "Давай начнём с одного маленького шага 🙂",
        reply_markup=MAIN_REPLY_MENU,
    )


async def topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(TOPICS_MENU_TEXT, reply_markup=main_inline_menu())


async def parents_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Для родителей:\n\n"
        "Этот бот не даёт готовые ответы и не помогает списывать.\n"
        "Он объясняет тему простыми словами, разбивает задачу на шаги, проверяет ход мысли ребёнка и поддерживает мотивацию через звёздочки, уровни и мягкую похвалу.\n\n"
        "Поддерживаются текст, PDF, DOCX, JPG и PNG.",
        reply_markup=MAIN_REPLY_MENU,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    stats = get_user_stats(update, context)

    if data == "menu_topic":
        await send_main_menu(query, TOPICS_MENU_TEXT, edit=True)
        return

    if data == "menu_steps":
        await send_main_menu(
            query,
            "<b>Решим по шагам</b>\n\nПришли задачу текстом или файлом. Я помогу понять условие и сделать только первый шаг.",
            edit=True,
        )
        return

    if data == "show_progress":
        await send_main_menu(query, format_progress_text(stats), edit=True)
        return

    if data == "parents_info":
        await send_main_menu(
            query,
            "<b>Для родителей</b>\n\nБот не выдаёт готовые ответы. Он мягко ведёт ребёнка вопросами, подсказками и маленькими шагами. Ошибки не ругает, а превращает в обучение.",
            edit=True,
        )
        return

    if data == "train_start":
        tasks = generate_training_tasks()
        context.user_data["training_tasks"] = tasks
        context.user_data["training_index"] = 0
        context.user_data["mode"] = "training"
        first = tasks[0]
        await send_main_menu(
            query,
            f"<b>Тренировка из 5 примеров</b>\n\nПример 1 из 5\n{html.escape(first.text)}\n\nНапиши только ответ числом. Если трудно, напиши <code>подсказка</code>.",
            edit=True,
        )
        return

    if data == "quiz_start":
        q = generate_quiz_question()
        context.user_data["mode"] = "quiz"
        context.user_data["quiz_question"] = q
        buttons = [[InlineKeyboardButton(opt, callback_data=f"quiz_answer:{i}")] for i, opt in enumerate(q["options"])]
        buttons.append([InlineKeyboardButton("🏠 В меню", callback_data="home")])
        await query.edit_message_text(
            f"<b>Мини-викторина</b>\n\n{html.escape(q['question'])}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
        return

    if data.startswith("quiz_answer:"):
        q = context.user_data.get("quiz_question")
        if not q:
            await send_main_menu(query, "Вопрос уже закончился. Выбери новый режим 👇", edit=True)
            return
        idx = int(data.split(":", 1)[1])
        correct = idx == q["correct"]
        if correct:
            stats["quiz_correct"] += 1
            stats["streak"] += 1
            sync_user_stats(update, context)
            add_stars(update, context, 2)
            text = (
                f"{random_praise()}\n\n"
                f"Верно! {html.escape(q['explain'])}\n\n"
                f"Ты получаешь 2 ⭐\n"
                f"Теперь у тебя {stats['stars']} звёздочек и уровень {stats['level']}."
            )
        else:
            stats["streak"] = 0
            sync_user_stats(update, context)
            text = (
                f"{random_encouragement()}\n\n"
                f"Пока неверно. {html.escape(q['explain'])}\n\n"
                "Ничего страшного — ошибки помогают учиться. Попробуй ещё одну викторину или перейди в тренировку."
            )
        context.user_data.pop("quiz_question", None)
        await send_main_menu(query, text, edit=True)
        return

    if data == "home":
        await send_main_menu(query, "<b>Главное меню</b>\n\nВыбери, чем хочешь заняться 👇", edit=True)
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = (update.message.text or "").strip()
    stats = get_user_stats(update, context)

    if normalize_text(user_text) == "🏠 главное меню":
        await update.message.reply_text("<b>Главное меню</b>\n\nВыбери, чем хочешь заняться 👇", reply_markup=main_inline_menu(), parse_mode="HTML")
        return

    mode = context.user_data.get("mode")
    if mode == "training":
        tasks: list[ExampleTask] = context.user_data.get("training_tasks", [])
        idx = context.user_data.get("training_index", 0)
        if idx < len(tasks):
            task = tasks[idx]
            if normalize_text(user_text) == "подсказка":
                await update.message.reply_text(
                    f"Подсказка 💡\n\n{task.hint}\n\nПопробуй ответить сам(а).",
                    reply_markup=MAIN_REPLY_MENU,
                )
                return
            if not re.fullmatch(r"-?\d+", user_text):
                await update.message.reply_text(
                    "Напиши ответ числом. Если трудно, напиши слово: подсказка",
                    reply_markup=MAIN_REPLY_MENU,
                )
                return
            answer = int(user_text)
            if answer == task.answer:
                stats["solved_training"] += 1
                stats["streak"] += 1
                sync_user_stats(update, context)
                add_stars(update, context, 1)
                idx += 1
                context.user_data["training_index"] = idx
                if idx >= len(tasks):
                    add_stars(update, context, 3)
                    context.user_data["mode"] = None
                    await update.message.reply_text(
                        f"🎉 Тренировка завершена!\n\nТы решил(а) 5 из 5 примеров.\n"
                        f"Получаешь 3 дополнительные ⭐\n"
                        f"Всего звёздочек: {stats['stars']}\n"
                        f"Твой уровень: {stats['level']}\n\n"
                        "Ты отлично поработал(а)! Возвращайся ещё за новой тренировкой.",
                        reply_markup=MAIN_REPLY_MENU,
                    )
                    await update.message.reply_text(format_progress_text(stats), parse_mode="HTML", reply_markup=main_inline_menu())
                    return
                next_task = tasks[idx]
                await update.message.reply_text(
                    f"{random_praise()}\n\nВерно! +1 ⭐\n"
                    f"Теперь пример {idx + 1} из 5:\n{next_task.text}\n\n"
                    "Напиши ответ числом. Если трудно, напиши: подсказка",
                    reply_markup=MAIN_REPLY_MENU,
                )
                return
            else:
                stats["streak"] = 0
                sync_user_stats(update, context)
                await update.message.reply_text(
                    f"{random_encouragement()}\n\nПока неверно.\n"
                    f"Подсказка: {task.hint}\n\n"
                    "Попробуй ещё раз. Я верю, что у тебя получится.",
                    reply_markup=MAIN_REPLY_MENU,
                )
                return

    reply = build_tutor_reply(user_text)
    await update.message.reply_text(reply, reply_markup=MAIN_REPLY_MENU)
    if normalize_text(user_text) in ["🏠 главное меню", "📎 отправить файл", "📝 проверить мой шаг", "🌟 поддержка"]:
        await update.message.reply_text("<b>Главное меню</b>", reply_markup=main_inline_menu(), parse_mode="HTML")


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
            "Я сейчас поддерживаю PDF, DOCX, JPG и PNG.\nПопробуй отправить файл в одном из этих форматов.",
            reply_markup=MAIN_REPLY_MENU,
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
    await update.message.reply_text(truncate_text(reply, 4000), reply_markup=MAIN_REPLY_MENU)
    await update.message.reply_text("<b>Главное меню</b>", reply_markup=main_inline_menu(), parse_mode="HTML")


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
    await update.message.reply_text(truncate_text(reply, 4000), reply_markup=MAIN_REPLY_MENU)
    await update.message.reply_text("<b>Главное меню</b>", reply_markup=main_inline_menu(), parse_mode="HTML")


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я могу помочь с задачей, темой, тренировкой, викториной или файлом 🙂",
        reply_markup=MAIN_REPLY_MENU,
    )
    await update.message.reply_text("<b>Главное меню</b>\n\nВыбери режим 👇", reply_markup=main_inline_menu(), parse_mode="HTML")



def main() -> None:
    load_progress()
    if not BOT_TOKEN:
        raise ValueError("Set BOT_TOKEN in Railway Variables.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("topics", topics_command))
    application.add_handler(CommandHandler("parents", parents_command))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.ALL, fallback))

    logger.info("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
