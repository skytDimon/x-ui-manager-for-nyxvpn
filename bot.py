import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import load_config

logger = logging.getLogger(__name__)
config = load_config()

# Инициализация бота
bot = Bot(
    token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Обработчик команды /start.
    Проверяет права (только ADMIN_ID) и выдает кнопку для открытия WebApp.
    """
    user_id = message.from_user.id

    if user_id != config.admin_id:
        logger.warning(f"Несанкционированный доступ от пользователя {user_id}")
        await message.answer("⛔ У вас нет прав для доступа к этому боту.")
        return

    # URL для WebApp. В случае локального тестирования или ngrok,
    # здесь должен быть реальный публичный HTTPS адрес
    # При локальном тесте Telegram API может потребовать HTTPS.
    # В production здесь должен быть ваш HTTPS домен.
    webapp_url = config.webapp_url

    # Кнопка открытия Web App
    web_app_btn = InlineKeyboardButton(
        text="🌐 Управление VPN", web_app=WebAppInfo(url=webapp_url)
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[web_app_btn]])

    text = (
        "👋 <b>Панель управления VPN</b>\n\n"
        f"🖥 Нод: <b>{len(config.servers)}</b>\n\n"
        "Дашборд, создание и управление клиентами — внутри."
    )

    await message.answer(text, reply_markup=keyboard)


async def start_bot():
    """Запуск polling бота."""
    logger.info("Запуск Telegram бота...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
