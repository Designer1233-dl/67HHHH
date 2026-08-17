import asyncio
import html
import logging
import os
import random

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message


logging.basicConfig(level=logging.INFO)


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
PHRASE_SEPARATOR = "||"

DEFAULT_INTRO_REPLIES = [
    "Ya na meste. Pishi vopros, a ya vydam maksimalno strannyy verdikt.",
    "Rezhim haotichnyh otvetov vklyuchen. Davai svoy vopros.",
    "Privet. Ya bot s somnitelnoy ekspertizoy i bolshoy lyubovyu k absurdnim otvetam.",
]

DEFAULT_QUESTION_OPENERS = [
    "Nu konechno",
    "Sto procentov",
    "AHAHAH, da",
    "Ne, nu eto ochevidno",
    "Sekundu... da",
    "Moya ekspertnaia komissiya reshila: da",
]

DEFAULT_QUESTION_CHAOS = [
    "tyyyyy chego voobshe sprashivaesh",
    "eto uzhe baza",
    "tut bez variantov",
    "ves chat eto podtverzhdaet",
    "kosmos lichno odobril etot otvet",
    "eto dazhe ne obsuzhdaetsya",
]

DEFAULT_STATEMENT_REPLIES = [
    "Zvuchit moshchno. Ya odobryayu etot haos.",
    "Eto soobshchenie ofitsialno proshlo proverku na smeshnyavost.",
    "Ya by otvetil umno, no vybral absurd.",
    "Silno. Gromko. Nemnogo podozritelno.",
    "Moy professionalnyy vyvod: lol.",
]

DEFAULT_MANUAL_MODE_ACKS = [
    "Tvoye soobshchenie uletelo adminu. Zhdem otvet.",
    "Prinyato. Admin uzhe smotrit i dumaet chto skazat.",
    "Ya peredal vopros glavnomu cheloveku po haosu.",
]


def load_phrase_list(env_name: str, fallback: list[str]) -> list[str]:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return fallback

    phrases = [item.strip() for item in raw_value.split(PHRASE_SEPARATOR)]
    phrases = [item for item in phrases if item]
    return phrases or fallback


INTRO_REPLIES = load_phrase_list("INTRO_REPLIES", DEFAULT_INTRO_REPLIES)
QUESTION_OPENERS = load_phrase_list("QUESTION_OPENERS", DEFAULT_QUESTION_OPENERS)
QUESTION_CHAOS = load_phrase_list("QUESTION_CHAOS", DEFAULT_QUESTION_CHAOS)
STATEMENT_REPLIES = load_phrase_list("STATEMENT_REPLIES", DEFAULT_STATEMENT_REPLIES)
MANUAL_MODE_ACKS = load_phrase_list("MANUAL_MODE_ACKS", DEFAULT_MANUAL_MODE_ACKS)


if ADMIN_ID_RAW:
    try:
        ADMIN_ID = int(ADMIN_ID_RAW)
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID dolzhen byt chislom.") from exc
else:
    ADMIN_ID = None


manual_mode_enabled = os.getenv("MANUAL_MODE_DEFAULT", "0").strip().lower() in {"1", "true", "yes", "on"}
forwarded_messages: dict[int, int] = {}


def is_admin(message: Message) -> bool:
    return ADMIN_ID is not None and message.from_user is not None and message.from_user.id == ADMIN_ID


def build_funny_answer(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return "Ty poteryal soobshchenie po doroge ili eto byl sekretnyy shifr?"

    if "?" in cleaned:
        base = cleaned.rstrip(" ?!.,")
        return f"{random.choice(QUESTION_OPENERS)}, {base.lower()}? {random.choice(QUESTION_CHAOS)}."

    return random.choice(STATEMENT_REPLIES)


def format_user_card(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Polzovatel ne opredelen"

    username = f"@{user.username}" if user.username else "bez username"
    full_name = user.full_name or "bez imeni"
    text = message.text or "[ne tekstovoe soobshchenie]"
    safe_text = html.escape(text)
    return (
        "Novoe soobshchenie v ruchnoy rezhim.\n"
        f"User ID: <code>{user.id}</code>\n"
        f"Username: {html.escape(username)}\n"
        f"Imya: {html.escape(full_name)}\n\n"
        f"Vopros:\n{safe_text}\n\n"
        "Otvet admina nuzhno otpravit reply na eto soobshchenie."
    )


async def start_handler(message: Message) -> None:
    await message.answer(random.choice(INTRO_REPLIES))


async def admin_panel_handler(message: Message) -> None:
    if not is_admin(message):
        await message.answer("Eta komanda tolko dlya admina.")
        return

    status = "VKL" if manual_mode_enabled else "VYKL"
    await message.answer(
        "Admin-panel:\n"
        f"Ruchnoy rezhim: {status}\n\n"
        "Komandy:\n"
        "/manual_on - vklyuchit peresylku voprosov adminu\n"
        "/manual_off - vyklyuchit peresylku i vernut randomnye otvety\n"
        "/admin - pokazat etu panel\n\n"
        "Kogda rezhim VKL, prosto otvechay reply na pereslannoe soobshchenie."
    )


async def manual_on_handler(message: Message) -> None:
    global manual_mode_enabled

    if not is_admin(message):
        await message.answer("Eta komanda tolko dlya admina.")
        return

    manual_mode_enabled = True
    await message.answer("Ruchnoy rezhim VKL. Teper soobshcheniya polzovateley budut prihodit tebe.")


async def manual_off_handler(message: Message) -> None:
    global manual_mode_enabled

    if not is_admin(message):
        await message.answer("Eta komanda tolko dlya admina.")
        return

    manual_mode_enabled = False
    await message.answer("Ruchnoy rezhim VYKL. Bot snova otvechaet sam svoim randomom.")


async def admin_reply_handler(message: Message) -> None:
    if not is_admin(message):
        return

    if not message.reply_to_message or not message.text:
        return

    target_user_id = forwarded_messages.get(message.reply_to_message.message_id)
    if target_user_id is None:
        return

    await message.bot.send_message(target_user_id, message.text)
    await message.answer("Otpravil otvet polzovatelyu.")


async def user_text_handler(message: Message) -> None:
    if not message.text:
        await message.answer("Ya poka druzhu tolko s tekstom. Kidai slovami.")
        return

    if is_admin(message):
        await admin_reply_handler(message)
        return

    if manual_mode_enabled and ADMIN_ID is not None:
        admin_message = await message.bot.send_message(
            ADMIN_ID,
            format_user_card(message),
            parse_mode="HTML",
        )
        forwarded_messages[admin_message.message_id] = message.from_user.id
        await message.answer(random.choice(MANUAL_MODE_ACKS))
        return

    await message.answer(build_funny_answer(message.text))


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Ne nayden BOT_TOKEN. Dobav ego v peremennye okruzheniya.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(admin_panel_handler, Command("admin"))
    dp.message.register(manual_on_handler, Command("manual_on"))
    dp.message.register(manual_off_handler, Command("manual_off"))
    dp.message.register(user_text_handler, F.text)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
