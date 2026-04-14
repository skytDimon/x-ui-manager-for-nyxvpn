"""
Точка входа для запуска всего приложения.
Запускает FastAPI через Uvicorn и Telegram бота (aiogram) параллельно.
"""

import sys
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from config import load_config
from api import app as fastapi_app
from bot import bot, dp, start_bot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

config = load_config()

# Интеграция жизненного цикла Aiogram внутрь FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Действия при запуске
    logger.info("Инициализация приложения...")
    
    # Запускаем бота как фоновую задачу
    bot_task = asyncio.create_task(start_bot())
    
    yield
    
    # Действия при выключении
    logger.info("Остановка приложения...")
    
    bot_task.cancel()
    
    # Корректное закрытие сессий бота
    await bot.session.close()

# Привязываем lifespan к существующему приложению FastAPI
fastapi_app.router.lifespan_context = lifespan

if __name__ == "__main__":
    if not config.bot_token:
        logger.error("BOT_TOKEN не задан! Пожалуйста, проверьте .env файл.")
        sys.exit(1)
        
    logger.info(f"Запуск WebApp сервера на {config.webapp_host}:{config.webapp_port}")
    
    uvicorn.run(
        "main:fastapi_app",
        host=config.webapp_host,
        port=config.webapp_port,
        reload=False  # В production reload=False
    )
