import asyncio
import inspect
from collections.abc import Iterable
from typing import Callable, NotRequired, Protocol, TypedDict, cast, overload

from quart import Quart, Response, request

from astrbot.api import logger  # pyright: ignore[reportMissingTypeStubs]
from platforms.base import PlatformProvider
from platforms.github import GitHubProvider


class PlatformConfig(TypedDict):
    platform: PlatformProvider
    path: str
    secret: NotRequired[str]


class HeadersLike(Protocol):
    def items(self) -> Iterable[tuple[str, str]]:
        ...


class WebhookPlugin(Protocol):
    @overload
    async def handle_webhook_event(self, event: dict[str, object]) -> None:
        ...

    @overload
    async def handle_webhook_event(
        self, event_type: str, payload: dict[str, object]
    ) -> None:
        ...


class MultiPlatformWebhookServer:
    """Run a Quart server to receive webhook callbacks."""

    def __init__(
        self,
        plugin: WebhookPlugin,
        host: str,
        port: int,
        platforms_config: list[PlatformConfig],
    ) -> None:
        self.plugin: WebhookPlugin = plugin
        self.host: str = host
        self.port: int = port
        self.platforms_config: list[PlatformConfig] = self._normalize_platforms_config(
            platforms_config
        )
        self.app: Quart = Quart(__name__)
        self._shutdown: asyncio.Event | None = None
        self._runner: asyncio.Task[None] | None = None
        self._configure_routes()

    def _configure_routes(self) -> None:
        for config in self.platforms_config:
            platform = config["platform"]
            path = config["path"]
            secret = config.get("secret", "")
            self._add_platform_route(platform, path, secret)

    def _add_platform_route(
        self, platform: PlatformProvider, path: str, secret: str
    ) -> None:
        normalized_path = self._normalize_path(path)
        secret_bytes = secret.encode("utf-8") if secret else None
        platform_name = platform.name

        async def webhook_handler():
            signature = self._extract_signature(request.headers)
            payload = await request.get_data()
            if isinstance(payload, (bytes, bytearray)):
                payload_bytes = bytes(payload)
            else:
                payload_bytes = str(payload).encode("utf-8")

            if secret_bytes:
                if not signature or not platform.verify_webhook_signature(
                    payload_bytes, signature, secret_bytes
                ):
                    logger.warning(f"收到无效的 {platform_name} Webhook 签名")
                    return Response("invalid signature", status=401)

            event_type = self._extract_event_type(request.headers)
            if not event_type:
                return Response("missing event", status=400)

            try:
                data = cast(
                    dict[object, object] | list[object] | None,
                    await request.get_json(),
                )
            except Exception:
                logger.warning(f"{platform_name} Webhook JSON 解析失败")
                return Response("invalid payload", status=400)

            if not isinstance(data, dict):
                logger.warning(f"{platform_name} Webhook payload 不是 JSON 对象")
                return Response("invalid payload", status=400)

            data_dict: dict[object, object] = data
            payload_data: dict[str, object] = {
                str(key): value for key, value in data_dict.items()
            }
            normalized_event = platform.parse_webhook_event(event_type, payload_data)
            if not normalized_event:
                logger.debug(
                    f"忽略 {platform_name} Webhook 事件 {event_type}: 未匹配解析规则"
                )
                return Response("ignored", status=200)

            normalized_event_data: dict[str, object] = dict(normalized_event)
            if "platform" not in normalized_event_data:
                normalized_event_data["platform"] = platform_name

            async def dispatch() -> None:
                try:
                    await self._dispatch_event(
                        event_type, payload_data, normalized_event_data
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        f"处理 {platform_name} Webhook 事件时出错: {exc}",
                        exc_info=True,
                    )

            _ = asyncio.create_task(dispatch())
            return Response("ok", status=200)

        async def webhook_health():
            return Response(f"{platform_name} webhook ok", status=200)

        endpoint_base = self._build_endpoint_name(platform_name, normalized_path)
        self.app.add_url_rule(
            normalized_path,
            endpoint=f"{endpoint_base}_post",
            view_func=webhook_handler,
            methods=["POST"],
        )
        self.app.add_url_rule(
            normalized_path,
            endpoint=f"{endpoint_base}_get",
            view_func=webhook_health,
            methods=["GET"],
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path if path.startswith("/") else f"/{path}"

    def _normalize_platforms_config(
        self, platforms_config: list[PlatformConfig]
    ) -> list[PlatformConfig]:
        normalized: list[PlatformConfig] = []
        for config in platforms_config:
            platform = config["platform"]
            path = self._normalize_path(config["path"])
            secret = config.get("secret") or ""
            normalized.append(
                {"platform": platform, "path": path, "secret": secret}
            )
        return normalized

    @staticmethod
    def _extract_signature(headers: HeadersLike) -> str | None:
        for key, value in headers.items():
            if "signature" in key.lower():
                return value
        return None

    @staticmethod
    def _extract_event_type(headers: HeadersLike) -> str:
        for key, value in headers.items():
            if key.lower().endswith("-event") and value:
                return value
        return ""

    @staticmethod
    def _build_endpoint_name(platform_name: str, path: str) -> str:
        slug = path.strip("/").replace("/", "_") or "root"
        return f"webhook_{platform_name}_{slug}"

    @staticmethod
    def _handler_expects_normalized(handler: Callable[..., object]) -> bool:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return False
        return len(signature.parameters) == 1

    async def _dispatch_event(
        self,
        event_type: str,
        payload: dict[str, object],
        normalized_event: dict[str, object],
    ) -> None:
        handler = self.plugin.handle_webhook_event
        if self._handler_expects_normalized(handler):
            await handler(normalized_event)
            return
        await handler(event_type, payload)

    def start(self) -> None:
        if self._runner:
            return
        self._shutdown = asyncio.Event()
        if not self.platforms_config:
            logger.warning("Webhook 未配置任何平台路由，服务仍会启动")
        for config in self.platforms_config:
            platform = config["platform"]
            path = config["path"]
            logger.info(
                f"启动 {platform.name} Webhook 服务: http://{self.host}:{self.port}{path}"
            )
            if not config.get("secret"):
                logger.warning(
                    f"{platform.name} Webhook 未设置 secret，建议在配置中设置以验证请求"
                )
        self._runner = asyncio.create_task(
            self.app.run_task(
                host=self.host,
                port=self.port,
                shutdown_trigger=self._wait_for_shutdown,
            )
        )

    async def _wait_for_shutdown(self) -> None:
        if self._shutdown is None:
            return
        _ = await self._shutdown.wait()

    async def stop(self) -> None:
        if not self._runner:
            return
        if self._shutdown:
            _ = self._shutdown.set()
        try:
            await self._runner
        finally:
            self._runner = None
            self._shutdown = None


class GitHubWebhookServer(MultiPlatformWebhookServer):
    """Backward compatible webhook server for GitHub."""

    def __init__(
        self,
        plugin: WebhookPlugin,
        host: str,
        port: int,
        secret: str | None,
        path: str,
    ) -> None:
        provider = GitHubProvider()
        platforms_config: list[PlatformConfig] = [
            {
                "platform": provider,
                "path": path,
                "secret": secret or "",
            }
        ]
        super().__init__(
            plugin=plugin,
            host=host,
            port=port,
            platforms_config=platforms_config,
        )
