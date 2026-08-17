import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from openai import OpenAI


logging.basicConfig(level=logging.INFO)


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "180").strip())
OPENAI_SYSTEM_PROMPT = os.getenv(
    "OPENAI_SYSTEM_PROMPT",
    (
        "Ты смешной Telegram-бот. "
        "Отвечай всегда на русском языке. "
        "Стиль: коротко, живо, мемно, с легким абсурдом и разговорной подачей. "
        "Не пиши слишком длинно, обычно 1-3 предложения. "
        "Если пользователь задает странный вопрос, отвечай уверенно и с юмором. "
        "Если сообщения мало или оно непонятно, все равно дай забавный осмысленный ответ."
    ),
).strip()


INTRO_REPLIES = [
    "Привет. Я на связи и готов нести нейросетевой хаос.",
    "Залетаю в чат с умным лицом и сомнительными шутками.",
    "Пиши что угодно. Я отвечу по-русски и с вайбом странной уверенности.",
]

MANUAL_MODE_ACKS = [
    "Сообщение улетело админу. Ждем его мудрейший ответ.",
    "Принял. Вопрос уже у админа.",
    "Передал твое сообщение человеку с правом ручного вердикта.",
]


if ADMIN_ID_RAW:
    try:
        ADMIN_ID = int(ADMIN_ID_RAW)
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID должен быть числом.") from exc
else:
    ADMIN_ID = None


manual_mode_enabled = os.getenv("MANUAL_MODE_DEFAULT", "0").strip().lower() in {"1", "true", "yes", "on"}
forwarded_messages: dict[int, int] = {}
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def is_admin(message: Message) -> bool:
    return ADMIN_ID is not None and message.from_user is not None and message.from_user.id == ADMIN_ID


def extract_user_text(message: Message) -> str:
    if message.text:
        return message.text

    if message.caption:
        return message.caption

    if message.sticker:
        sticker_name = message.sticker.emoji or "без эмодзи"
        return f"Пользователь прислал стикер: {sticker_name}."

    if message.photo:
        return "Пользователь прислал фото без подписи."

    if message.voice:
        return "Пользователь прислал голосовое сообщение."

    if message.video:
        return "Пользователь прислал видео."

    if message.video_note:
        return "Пользователь прислал видеокружок."

    if message.animation:
        return "Пользователь прислал гифку."

    if message.document:
        return f"Пользователь прислал файл: {message.document.file_name or 'без названия'}."

    return "Пользователь прислал сообщение без текста. Ответь уместно и с юмором."


def format_user_card(message: Message, user_text: str) -> str:
    user = message.from_user
    if user is None:
        return "Пользователь не определен"

    username = f"@{user.username}" if user.username else "без username"
    full_name = user.full_name or "без имени"
    safe_text = html.escape(user_text)
    return (
        "Новое сообщение в ручной режим.\n"
        f"User ID: <code>{user.id}</code>\n"
        f"Username: {html.escape(username)}\n"
        f"Имя: {html.escape(full_name)}\n\n"
        f"Сообщение:\n{safe_text}\n\n"
        "Ответ админа нужно отправить reply на это сообщение."
    )


async def generate_ai_reply(user_text: str) -> str:
    if openai_client is None:
        raise RuntimeError("Не найден OPENAI_API_KEY. Добавь его в переменные окружения.")

    def _request() -> str:
        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
        )
        text = (response.output_text or "").strip()
        return text or "Я задумался слишком глубоко. Напиши еще раз, и я вернусь с новым приколом."

    return await asyncio.to_thread(_request)


async def start_handler(message: Message) -> None:
    await message.answer(INTRO_REPLIES[message.message_id % len(INTRO_REPLIES)])


async def admin_panel_handler(message: Message) -> None:
    if not is_admin(message):
        await message.answer("Эта команда только для админа.")
        return

    status = "ВКЛ" if manual_mode_enabled else "ВЫКЛ"
    await message.answer(
        "Админ-панель:\n"
        f"Ручной режим: {status}\n\n"
        "Команды:\n"
        "/manual_on - включить ручные ответы\n"
        "/manual_off - выключить ручные ответы\n"
        "/admin - показать эту панель\n\n"
        "Когда режим ВКЛ, просто отвечай reply на пересланное сообщение."
    )


async def manual_on_handler(message: Message) -> None:
    global manual_mode_enabled

    if not is_admin(message):
        await message.answer("Эта команда только для админа.")
        return

    manual_mode_enabled = True
    await message.answer("Ручной режим включен. Теперь сообщения пользователей будут приходить тебе.")


async def manual_off_handler(message: Message) -> None:
    global manual_mode_enabled

    if not is_admin(message):
        await message.answer("Эта команда только для админа.")
        return

    manual_mode_enabled = False
    await message.answer("Ручной режим выключен. Бот снова отвечает нейросетью сам.")


async def admin_reply_handler(message: Message) -> bool:
    if not is_admin(message):
        return False

    if not message.reply_to_message:
        return False

    reply_text = message.text or message.caption
    if not reply_text:
        return False

    target_user_id = forwarded_messages.get(message.reply_to_message.message_id)
    if target_user_id is None:
        return False

    await message.bot.send_message(target_user_id, reply_text)
    await message.answer("Ответ отправлен пользователю.")
    return True


async def message_handler(message: Message) -> None:
    user_text = extract_user_text(message)

    if is_admin(message):
        handled = await admin_reply_handler(message)
        if not handled and message.text and not message.text.startswith("/"):
            await message.answer("Если хочешь ответить пользователю вручную, сделай reply на его пересланное сообщение.")
        return

    if manual_mode_enabled and ADMIN_ID is not None:
        admin_message = await message.bot.send_message(
            ADMIN_ID,
            format_user_card(message, user_text),
            parse_mode="HTML",
        )
        if message.from_user is not None:
            forwarded_messages[admin_message.message_id] = message.from_user.id
        await message.answer(MANUAL_MODE_ACKS[message.message_id % len(MANUAL_MODE_ACKS)])
        return

    try:
        ai_reply = await generate_ai_reply(user_text)
    except Exception:
        logging.exception("Не удалось получить ответ от OpenAI")
        await message.answer("Нейросеть что-то задумалась и зависла. Попробуй еще раз через пару секунд.")
        return

    await message.answer(ai_reply)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Добавь его в переменные окружения.")
    if not OPENAI_API_KEY:
        raise RuntimeError("Не найден OPENAI_API_KEY. Добавь его в переменные окружения.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(admin_panel_handler, Command("admin"))
    dp.message.register(manual_on_handler, Command("manual_on"))
    dp.message.register(manual_off_handler, Command("manual_off"))
    dp.message.register(message_handler)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
