"""
FastAPI приложение: REST API + раздача WebApp страницы.
"""

import uuid
import time
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import load_config
from xui_client import XUIClient, generate_sub_id, ClientInfo

logger = logging.getLogger(__name__)

config = load_config()

app = FastAPI(
    title="X-UI Manager API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# Путь к шаблонам
TEMPLATES_DIR = Path(__file__).parent / "templates"


# --- Модели ---


class AddClientRequest(BaseModel):
    """Запрос на добавление клиента."""

    username: str = Field(..., min_length=1, max_length=64, description="Имя клиента")
    days: int = Field(0, description="Количество дней подписки (0 - навсегда)")


class ServerResult(BaseModel):
    """Результат для одного сервера."""

    server_name: str
    success: bool
    message: str


class AddClientResponseModel(BaseModel):
    """Ответ API после добавления клиента."""

    success: bool
    username: str
    client_uuid: str
    sub_id: str
    subscription_url: str
    servers: list[ServerResult]
    message: str


class ClientInfoModel(BaseModel):
    """Модель информации о клиенте для фронтенда."""

    id: str
    email: str
    sub_id: str
    expiry_time: int
    enable: bool
    total_gb: int
    up: int
    down: int


class UpdateClientRequest(BaseModel):
    """Запрос на продление подписки."""

    client_uuid: str
    days: int


class UpdateClientResponseModel(BaseModel):
    """Ответ API после обновления клиента."""

    success: bool
    message: str
    servers: list[ServerResult]


class DeleteClientRequest(BaseModel):
    """Запрос на удаление клиента."""

    client_uuid: str


class DeleteClientResponseModel(BaseModel):
    """Ответ API после удаления клиента."""

    success: bool
    message: str
    servers: list[ServerResult]


class ToggleClientRequest(BaseModel):
    """Запрос на включение/выключение клиента."""

    client_uuid: str
    enable: bool


class ToggleClientResponseModel(BaseModel):
    """Ответ API после включения/выключения клиента."""

    success: bool
    message: str
    servers: list[ServerResult]


class DashboardModel(BaseModel):
    """Модель данных дашборда."""

    total_clients: int
    active_clients: int
    expired_clients: int
    total_traffic_gb: float


# --- Эндпоинты ---


@app.get("/", response_class=HTMLResponse)
async def serve_webapp():
    """Отдаёт HTML-страницу WebApp."""
    html_path = TEMPLATES_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="WebApp page not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/add_client", response_model=AddClientResponseModel)
async def add_client(request: AddClientRequest):
    """
    Добавление клиента на оба сервера 3x-ui.

    1. Генерирует UUID и subId
    2. Авторизуется на обоих серверах
    3. Добавляет клиента с идентичным payload
    4. Возвращает ссылку подписки
    """
    username = request.username.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Имя клиента не может быть пустым")

    # Расчет expiry_time
    expiry_time = 0
    if request.days > 0:
        expiry_time = int((time.time() + (request.days * 24 * 3600)) * 1000)

    # Генерация credentials
    client_uuid = str(uuid.uuid4())
    sub_id = generate_sub_id(username)
    subscription_url = f"{config.subscription_base_url}/{sub_id}"

    logger.info(
        f"📝 Создание клиента: {username} | UUID: {client_uuid} | SubID: {sub_id}"
    )

    # Создаём клиенты для каждого сервера
    xui_clients = [XUIClient(server) for server in config.servers]
    server_results = []

    try:
        # Авторизация на всех серверах параллельно
        login_tasks = [client.login() for client in xui_clients]
        login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

        for i, (xui_client, login_result) in enumerate(zip(xui_clients, login_results)):
            if isinstance(login_result, Exception):
                logger.error(
                    f"❌ Исключение при авторизации на {xui_client.server.name}: {login_result}"
                )
                server_results.append(
                    ServerResult(
                        server_name=xui_client.server.name,
                        success=False,
                        message=f"Ошибка подключения: {str(login_result)}",
                    )
                )
                continue

            if not login_result:
                server_results.append(
                    ServerResult(
                        server_name=xui_client.server.name,
                        success=False,
                        message="Не удалось авторизоваться",
                    )
                )
                continue

            # Добавляем клиента на сервер
            result = await xui_client.add_client(
                client_uuid=client_uuid,
                email=username,
                sub_id=sub_id,
                expiry_time=expiry_time,
            )
            server_results.append(
                ServerResult(
                    server_name=result.server_name,
                    success=result.success,
                    message=result.message,
                )
            )

    finally:
        # Закрываем все сессии
        close_tasks = [client.close() for client in xui_clients]
        await asyncio.gather(*close_tasks, return_exceptions=True)

    # Определяем общий успех
    all_success = all(r.success for r in server_results)
    any_success = any(r.success for r in server_results)

    if all_success:
        message = f"✅ Клиент '{username}' успешно добавлен на все серверы!"
    elif any_success:
        failed = [r.server_name for r in server_results if not r.success]
        message = f"⚠️ Клиент добавлен частично. Ошибка на: {', '.join(failed)}"
    else:
        message = "❌ Не удалось добавить клиента ни на один сервер"

    logger.info(f"Результат: {message}")

    return AddClientResponseModel(
        success=any_success,
        username=username,
        client_uuid=client_uuid,
        sub_id=sub_id,
        subscription_url=subscription_url,
        servers=server_results,
        message=message,
    )


@app.get("/api/clients", response_model=list[ClientInfoModel])
async def get_clients():
    """Получение списка клиентов (берём с первого сервера)."""
    if not config.servers:
        return []

    xui_client = XUIClient(config.servers[0])
    try:
        if await xui_client.login():
            clients = await xui_client.get_clients()
            return [
                ClientInfoModel(
                    id=c.id,
                    email=c.email,
                    sub_id=c.sub_id,
                    expiry_time=c.expiry_time,
                    enable=c.enable,
                    total_gb=c.total_gb,
                    up=c.up,
                    down=c.down,
                )
                for c in clients
            ]
        return []
    finally:
        await xui_client.close()


@app.post("/api/update_client", response_model=UpdateClientResponseModel)
async def update_client(request: UpdateClientRequest):
    """Добавление дней к подписке на обоих серверах."""
    if request.days <= 0:
        raise HTTPException(
            status_code=400, detail="Количество дней должно быть больше 0"
        )

    if not config.servers:
        raise HTTPException(status_code=500, detail="Серверы не настроены")

    # Сначала узнаем текущий expiry_time с первого сервера
    current_expiry = 0
    xui_client = XUIClient(config.servers[0])
    try:
        if await xui_client.login():
            clients = await xui_client.get_clients()
            client = next((c for c in clients if c.id == request.client_uuid), None)
            if not client:
                raise HTTPException(status_code=404, detail="Клиент не найден")
            current_expiry = client.expiry_time
    finally:
        await xui_client.close()

    # Считаем новый expiry_time
    now_ms = int(time.time() * 1000)
    add_ms = request.days * 24 * 3600 * 1000

    if current_expiry > now_ms:
        # У клиента еще есть активное время, прибавляем к нему
        new_expiry_time = current_expiry + add_ms
    else:
        # Клиент истек или безлимитный (0), прибавляем к сегодняшнему дню
        new_expiry_time = now_ms + add_ms

    xui_clients = [XUIClient(server) for server in config.servers]
    server_results = []

    try:
        login_tasks = [client.login() for client in xui_clients]
        login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

        for xui, login_ok in zip(xui_clients, login_results):
            if isinstance(login_ok, Exception) or not login_ok:
                server_results.append(
                    ServerResult(
                        server_name=xui.server.name,
                        success=False,
                        message="Ошибка подключения",
                    )
                )
                continue

            res = await xui.update_client_expiry(request.client_uuid, new_expiry_time)
            server_results.append(
                ServerResult(
                    server_name=res.server_name,
                    success=res.success,
                    message=res.message,
                )
            )

    finally:
        close_tasks = [client.close() for client in xui_clients]
        await asyncio.gather(*close_tasks, return_exceptions=True)

    all_success = all(r.success for r in server_results)
    any_success = any(r.success for r in server_results)

    if all_success:
        message = f"✅ Срок подписки успешно продлен на {request.days} дней!"
    elif any_success:
        message = f"⚠️ Срок подписки продлен частично. Проверьте серверы."
    else:
        message = "❌ Не удалось продлить подписку"

    return UpdateClientResponseModel(
        success=any_success, message=message, servers=server_results
    )


@app.post("/api/delete_client", response_model=DeleteClientResponseModel)
async def delete_client(request: DeleteClientRequest):
    """Удаление клиента на обоих серверах."""
    if not config.servers:
        raise HTTPException(status_code=500, detail="Серверы не настроены")

    xui_clients = [XUIClient(server) for server in config.servers]
    server_results = []

    try:
        login_tasks = [client.login() for client in xui_clients]
        login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

        for xui, login_ok in zip(xui_clients, login_results):
            if isinstance(login_ok, Exception) or not login_ok:
                server_results.append(
                    ServerResult(
                        server_name=xui.server.name,
                        success=False,
                        message="Ошибка подключения",
                    )
                )
                continue

            res = await xui.delete_client(request.client_uuid)
            server_results.append(
                ServerResult(
                    server_name=res.server_name,
                    success=res.success,
                    message=res.message,
                )
            )

    finally:
        close_tasks = [client.close() for client in xui_clients]
        await asyncio.gather(*close_tasks, return_exceptions=True)

    any_success = any(r.success for r in server_results)

    if any_success:
        message = f"✅ Клиент удален со всех серверов где был найден"
    else:
        message = "❌ Не удалось удалить клиента"

    return DeleteClientResponseModel(
        success=any_success, message=message, servers=server_results
    )


@app.post("/api/toggle_client", response_model=ToggleClientResponseModel)
async def toggle_client(request: ToggleClientRequest):
    """Включение/выключение клиента на обоих серверах."""
    if not config.servers:
        raise HTTPException(status_code=500, detail="Серверы не настроены")

    xui_clients = [XUIClient(server) for server in config.servers]
    server_results = []

    try:
        login_tasks = [client.login() for client in xui_clients]
        login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

        for xui, login_ok in zip(xui_clients, login_results):
            if isinstance(login_ok, Exception) or not login_ok:
                server_results.append(
                    ServerResult(
                        server_name=xui.server.name,
                        success=False,
                        message="Ошибка подключения",
                    )
                )
                continue

            res = await xui.toggle_client(request.client_uuid, request.enable)
            server_results.append(
                ServerResult(
                    server_name=res.server_name,
                    success=res.success,
                    message=res.message,
                )
            )

    finally:
        close_tasks = [client.close() for client in xui_clients]
        await asyncio.gather(*close_tasks, return_exceptions=True)

    any_success = any(r.success for r in server_results)
    action = "включен" if request.enable else "выключен"

    if any_success:
        message = f"✅ Клиент {action} на серверах"
    else:
        message = (
            f"❌ Не удалось {('включить' if request.enable else 'выключить')} клиента"
        )

    return ToggleClientResponseModel(
        success=any_success, message=message, servers=server_results
    )


@app.get("/api/dashboard", response_model=DashboardModel)
async def get_dashboard():
    """Получение сводной статистики для дашборда."""
    if not config.servers:
        return DashboardModel(
            total_clients=0, active_clients=0, expired_clients=0, total_traffic_gb=0.0
        )

    xui_client = XUIClient(config.servers[0])
    try:
        if not await xui_client.login():
            return DashboardModel(
                total_clients=0,
                active_clients=0,
                expired_clients=0,
                total_traffic_gb=0.0,
            )

        clients = await xui_client.get_clients()
        now_ms = int(time.time() * 1000)

        total = len(clients)
        expired = 0
        total_bytes = 0

        for c in clients:
            if c.expiry_time > 0 and c.expiry_time < now_ms:
                expired += 1
            elif not c.enable:
                expired += 1
            total_bytes += c.up + c.down

        active = total - expired
        total_gb = round(total_bytes / (1024**3), 2)

        return DashboardModel(
            total_clients=total,
            active_clients=active,
            expired_clients=expired,
            total_traffic_gb=total_gb,
        )
    finally:
        await xui_client.close()


@app.get("/health")
async def health_check():
    """Проверка работоспособности API."""
    return {"status": "ok", "servers_configured": len(config.servers)}
