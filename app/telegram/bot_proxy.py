import logging
import os

logger = logging.getLogger(__name__)


def get_bot_api_proxy_url() -> str | None:
    if os.getenv("PROXY_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return None

    scheme_map = {
        "socks5": "socks5h",
        "socks4": "socks4",
        "http": "http",
    }
    proxy_type_name = os.getenv("PROXY_TYPE", "socks5").lower()
    scheme = scheme_map.get(proxy_type_name, "socks5h")

    host = os.getenv("PROXY_HOST", "127.0.0.1")
    port = os.getenv("PROXY_PORT", "12334")
    username = os.getenv("PROXY_USERNAME") or None
    password = os.getenv("PROXY_PASSWORD") or None

    if username and password:
        url = f"{scheme}://{username}:{password}@{host}:{port}"
    else:
        url = f"{scheme}://{host}:{port}"

    logger.info(
        "اتصال Bot API (python-telegram-bot) از طریق پروکسی %s://%s:%s",
        proxy_type_name,
        host,
        port,
    )
    return url
