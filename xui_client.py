"""
Асинхронный клиент для API 3x-ui панелей.
Использует aiohttp для HTTP-запросов.
"""

import json
import uuid
import string
import random
import logging
from dataclasses import dataclass

import aiohttp

from config import ServerConfig

logger = logging.getLogger(__name__)


@dataclass
class ClientResult:
    """Результат операции с клиентом."""

    server_name: str
    success: bool
    message: str


@dataclass
class ClientInfo:
    """Информация о клиенте."""

    id: str
    email: str
    sub_id: str
    expiry_time: int
    enable: bool
    total_gb: int
    up: int
    down: int
    server_name: str


@dataclass
class AddClientResponse:
    """Полный ответ после добавления клиента на все серверы."""

    username: str
    client_uuid: str
    sub_id: str
    subscription_url: str
    results: list[ClientResult]
    all_success: bool


def generate_sub_id(username: str) -> str:
    """Генерация subId в формате: {username}_{6 случайных символов}."""
    chars = string.ascii_lowercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"{username}_{suffix}"


class XUIClient:
    """Клиент для взаимодействия с API 3x-ui."""

    def __init__(self, server: ServerConfig):
        self.server = server
        self._session: aiohttp.ClientSession | None = None
        self._cookie_jar = aiohttp.CookieJar(unsafe=True)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать HTTP-сессию."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=self._cookie_jar,
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def login(self) -> bool:
        """Авторизация на панели 3x-ui."""
        try:
            session = await self._get_session()
            url = f"{self.server.url}/login"
            payload = {
                "username": self.server.username,
                "password": self.server.password,
            }

            logger.info(f"Авторизация на {self.server.name} ({self.server.url})...")

            async with session.post(url, data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info(f"✅ Авторизация на {self.server.name} успешна")
                        return True
                    else:
                        logger.error(
                            f"❌ Ошибка авторизации на {self.server.name}: {data.get('msg', 'unknown')}"
                        )
                        return False
                else:
                    logger.error(
                        f"❌ HTTP {resp.status} при авторизации на {self.server.name}"
                    )
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к {self.server.name}: {e}")
            return False

    async def add_client(
        self, client_uuid: str, email: str, sub_id: str, expiry_time: int = 0
    ) -> ClientResult:
        """Добавление клиента в inbound на сервере."""
        try:
            session = await self._get_session()
            url = f"{self.server.url}/panel/api/inbounds/addClient"

            settings = json.dumps(
                {
                    "clients": [
                        {
                            "id": client_uuid,
                            "email": email,
                            "subId": sub_id,
                            "enable": True,
                            "flow": "",
                            "limitIp": 0,
                            "totalGB": 0,
                            "expiryTime": expiry_time,
                            "tgId": "",
                            "reset": 0,
                        }
                    ]
                }
            )

            payload = {
                "id": self.server.inbound_id,
                "settings": settings,
            }

            logger.info(f"Добавление клиента '{email}' на {self.server.name}...")

            async with session.post(url, data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info(
                            f"✅ Клиент '{email}' добавлен на {self.server.name}"
                        )
                        return ClientResult(
                            server_name=self.server.name,
                            success=True,
                            message="Клиент успешно добавлен",
                        )
                    else:
                        msg = data.get("msg", "Неизвестная ошибка")
                        logger.error(
                            f"❌ Ошибка добавления на {self.server.name}: {msg}"
                        )
                        return ClientResult(
                            server_name=self.server.name,
                            success=False,
                            message=msg,
                        )
                else:
                    logger.error(
                        f"❌ HTTP {resp.status} при добавлении на {self.server.name}"
                    )
                    return ClientResult(
                        server_name=self.server.name,
                        success=False,
                        message=f"HTTP ошибка: {resp.status}",
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении на {self.server.name}: {e}")
            return ClientResult(
                server_name=self.server.name,
                success=False,
                message=str(e),
            )

    async def get_clients(self) -> list[ClientInfo]:
        """Получение списка клиентов сервера для заданного inbound."""
        clients = []
        try:
            session = await self._get_session()
            url = f"{self.server.url}/panel/api/inbounds/list"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        inbounds = data.get("obj", [])
                        for inbound in inbounds:
                            if inbound.get("id") == self.server.inbound_id:
                                settings_str = inbound.get("settings", "{}")
                                settings = json.loads(settings_str)
                                clients_data = settings.get("clients", [])

                                for c in clients_data:
                                    clients.append(
                                        ClientInfo(
                                            id=c.get("id", ""),
                                            email=c.get("email", ""),
                                            sub_id=c.get("subId", ""),
                                            expiry_time=c.get("expiryTime", 0),
                                            enable=c.get("enable", True),
                                            total_gb=c.get("totalGB", 0),
                                            up=c.get("up", 0),
                                            down=c.get("down", 0),
                                            server_name=self.server.name,
                                        )
                                    )
                                break
                    else:
                        logger.error(
                            f"Ошибка получения inbounds на {self.server.name}: {data.get('msg')}"
                        )
                else:
                    logger.error(
                        f"HTTP {resp.status} при получении inbounds на {self.server.name}"
                    )

        except Exception as e:
            logger.error(f"Ошибка get_clients на {self.server.name}: {e}")

        return clients

    async def update_client_expiry(
        self, client_uuid: str, new_expiry_time: int
    ) -> ClientResult:
        """Обновление даты истечения (expiryTime) для конкретного клиента."""
        try:
            # 1. Сначала нужно получить текущие данные клиента, чтобы не затереть остальные поля
            session = await self._get_session()
            url = f"{self.server.url}/panel/api/inbounds/list"

            client_data = None
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for inbound in data.get("obj", []):
                        if inbound.get("id") == self.server.inbound_id:
                            settings = json.loads(inbound.get("settings", "{}"))
                            for c in settings.get("clients", []):
                                if c.get("id") == client_uuid:
                                    client_data = c
                                    break
                        if client_data:
                            break

            if not client_data:
                return ClientResult(
                    server_name=self.server.name,
                    success=False,
                    message="Клиент не найден",
                )

            # 2. Обновляем expiryTime и отправляем запрос на update
            client_data["expiryTime"] = new_expiry_time

            update_url = (
                f"{self.server.url}/panel/api/inbounds/updateClient/{client_uuid}"
            )

            settings_payload = json.dumps({"clients": [client_data]})

            payload = {"id": self.server.inbound_id, "settings": settings_payload}

            async with session.post(update_url, data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return ClientResult(
                            server_name=self.server.name,
                            success=True,
                            message="Срок клиента обновлен",
                        )
                    else:
                        return ClientResult(
                            server_name=self.server.name,
                            success=False,
                            message=data.get("msg", "Ошибка обновления"),
                        )
                else:
                    return ClientResult(
                        server_name=self.server.name,
                        success=False,
                        message=f"HTTP {resp.status}",
                    )
        except Exception as e:
            logger.error(f"Ошибка обновления клиента на {self.server.name}: {e}")
            return ClientResult(
                server_name=self.server.name, success=False, message=str(e)
            )

    async def delete_client(self, client_uuid: str) -> ClientResult:
        """Удаление клиента из inbound на сервере."""
        try:
            session = await self._get_session()
            url = f"{self.server.url}/panel/api/inbounds/delClient/{client_uuid}"

            payload = {
                "id": self.server.inbound_id,
            }

            logger.info(f"Удаление клиента '{client_uuid}' на {self.server.name}...")

            async with session.post(url, data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info(
                            f"✅ Клиент '{client_uuid}' удален на {self.server.name}"
                        )
                        return ClientResult(
                            server_name=self.server.name,
                            success=True,
                            message="Клиент успешно удален",
                        )
                    else:
                        msg = data.get("msg", "Неизвестная ошибка")
                        logger.error(f"❌ Ошибка удаления на {self.server.name}: {msg}")
                        return ClientResult(
                            server_name=self.server.name,
                            success=False,
                            message=msg,
                        )
                else:
                    logger.error(
                        f"❌ HTTP {resp.status} при удалении на {self.server.name}"
                    )
                    return ClientResult(
                        server_name=self.server.name,
                        success=False,
                        message=f"HTTP ошибка: {resp.status}",
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка при удалении на {self.server.name}: {e}")
            return ClientResult(
                server_name=self.server.name,
                success=False,
                message=str(e),
            )

    async def toggle_client(self, client_uuid: str, enable: bool) -> ClientResult:
        """Включение/выключение клиента на сервере."""
        try:
            session = await self._get_session()
            url = f"{self.server.url}/panel/api/inbounds/list"

            client_data = None
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for inbound in data.get("obj", []):
                        if inbound.get("id") == self.server.inbound_id:
                            settings = json.loads(inbound.get("settings", "{}"))
                            for c in settings.get("clients", []):
                                if c.get("id") == client_uuid:
                                    client_data = c
                                    break
                        if client_data:
                            break

            if not client_data:
                return ClientResult(
                    server_name=self.server.name,
                    success=False,
                    message="Клиент не найден",
                )

            client_data["enable"] = enable

            update_url = (
                f"{self.server.url}/panel/api/inbounds/updateClient/{client_uuid}"
            )

            settings_payload = json.dumps({"clients": [client_data]})

            payload = {"id": self.server.inbound_id, "settings": settings_payload}

            action = "включен" if enable else "выключен"
            async with session.post(update_url, data=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return ClientResult(
                            server_name=self.server.name,
                            success=True,
                            message=f"Клиент {action}",
                        )
                    else:
                        return ClientResult(
                            server_name=self.server.name,
                            success=False,
                            message=data.get("msg", "Ошибка обновления"),
                        )
                else:
                    return ClientResult(
                        server_name=self.server.name,
                        success=False,
                        message=f"HTTP {resp.status}",
                    )
        except Exception as e:
            logger.error(f"Ошибка toggle клиента на {self.server.name}: {e}")
            return ClientResult(
                server_name=self.server.name, success=False, message=str(e)
            )

    async def close(self):
        """Закрытие HTTP-сессии."""
        if self._session and not self._session.closed:
            await self._session.close()
