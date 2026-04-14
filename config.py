"""
Конфигурация проекта X-UI Manager.
Все чувствительные данные загружаются из переменных окружения.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ServerConfig:
    """Конфигурация одного сервера 3x-ui."""

    name: str
    url: str
    username: str
    password: str
    inbound_id: int


@dataclass
class AppConfig:
    """Главная конфигурация приложения."""

    bot_token: str
    admin_id: int
    webapp_url: str
    webapp_host: str
    webapp_port: int
    subscription_base_url: str
    servers: list[ServerConfig] = field(default_factory=list)


def load_config() -> AppConfig:
    """Загрузка конфигурации из .env файла."""
    bot_token = os.getenv("BOT_TOKEN", "")
    admin_id = int(os.getenv("ADMIN_ID", "0"))
    webapp_url = os.getenv("WEBAPP_URL", "https://nyxvpnde.port0.org:8442")
    webapp_host = os.getenv("WEBAPP_HOST", "0.0.0.0")
    webapp_port = int(os.getenv("WEBAPP_PORT", "3000"))
    subscription_base_url = os.getenv(
        "SUBSCRIPTION_BASE_URL", "https://nyxvpnnl.home.kg:15498/sub"
    )

    servers = [
        ServerConfig(
            name=os.getenv("SERVER1_NAME", "Сервер 1"),
            url=os.getenv("SERVER1_URL", ""),
            username=os.getenv("SERVER1_USERNAME", ""),
            password=os.getenv("SERVER1_PASSWORD", ""),
            inbound_id=int(os.getenv("SERVER1_INBOUND_ID", "1")),
        ),
        ServerConfig(
            name=os.getenv("SERVER2_NAME", "Сервер 2"),
            url=os.getenv("SERVER2_URL", ""),
            username=os.getenv("SERVER2_USERNAME", ""),
            password=os.getenv("SERVER2_PASSWORD", ""),
            inbound_id=int(os.getenv("SERVER2_INBOUND_ID", "1")),
        ),
    ]

    return AppConfig(
        bot_token=bot_token,
        admin_id=admin_id,
        webapp_url=webapp_url,
        webapp_host=webapp_host,
        webapp_port=webapp_port,
        subscription_base_url=subscription_base_url,
        servers=servers,
    )
