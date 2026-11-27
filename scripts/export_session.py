import asyncio
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import BASE_DIR, settings
from app.telegram.client import ensure_started, stop_client

OUTPUT_PATH = BASE_DIR / "sessions" / "railway-session.txt"


def _get_telethon_proxy():
    if os.getenv("PROXY_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return None
    import socks

    proxy_type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }
    proxy_type = proxy_type_map.get(os.getenv("PROXY_TYPE", "socks5").lower(), socks.SOCKS5)
    host = os.getenv("PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("PROXY_PORT", "12334"))
    username = os.getenv("PROXY_USERNAME") or None
    password = os.getenv("PROXY_PASSWORD") or None
    if username and password:
        return (proxy_type, host, port, True, username, password)
    return (proxy_type, host, port)


async def export_session(output_path: Path = OUTPUT_PATH) -> None:
    telethon_client: TelegramClient | None = None
    try:
        client = await ensure_started()
        if await client.is_bot():
            if not settings.api_id or not settings.api_hash:
                raise RuntimeError(
                    "برای استخراج سشن کاربری Telethon، تنظیم API_ID و API_HASH در فایل .env الزامی است."
                )
            telethon_client = TelegramClient(
                StringSession(),
                settings.api_id,
                settings.api_hash,
                proxy=_get_telethon_proxy(),
            )
            await telethon_client.connect()
            if not await telethon_client.is_user_authorized():
                mode = input(
                    "روش ورود را انتخاب کنید:\n"
                    "1. اسکن QR Code / لینک ورود (بدون نیاز به دریافت کد - پیشنهادی)\n"
                    "2. شماره تلفن و کد\n"
                    "انتخاب (1 یا 2): "
                ).strip()
                if mode == "1":
                    qr_login = await telethon_client.qr_login()
                    while True:
                        print("\nQR Code زیر را از بخش Settings -> Devices -> Link Desktop Device اسکن کنید:")
                        print(f"لینک: {qr_login.url}")
                        try:
                            import qrcode  # type: ignore

                            qr = qrcode.QRCode(border=1)
                            qr.add_data(qr_login.url)
                            qr.print_ascii(invert=True)
                        except ImportError:
                            print("(برای نمایش QR در ترمینال: pip install qrcode)")
                        print("\nدر حال انتظار برای تأیید در تلگرام شما...")
                        try:
                            await qr_login.wait(timeout=30)
                            break
                        except TimeoutError:
                            print("زمان QR Code تمام شد؛ در حال ساخت کد جدید...")
                            await qr_login.recreate()
                        except Exception as exc:
                            if "SessionPasswordNeededError" in type(exc).__name__ or "password" in str(exc).lower():
                                import getpass

                                password = getpass.getpass("Please enter your 2FA password: ")
                                await telethon_client.sign_in(password=password)
                                break
                            raise
                else:
                    phone = input("Please enter your phone (e.g. +989123456789): ").strip()
                    sent = await telethon_client.send_code_request(phone)
                    print(f"Code delivery method: {type(sent.type).__name__}")
                    code = input("Please enter the code you received: ").strip()
                    try:
                        await telethon_client.sign_in(phone, code)
                    except Exception as exc:
                        if "SessionPasswordNeededError" in type(exc).__name__ or "password" in str(exc).lower():
                            import getpass

                            password = getpass.getpass("Please enter your 2FA password: ")
                            await telethon_client.sign_in(password=password)
                        else:
                            raise
            client = telethon_client
            if await client.is_bot():
                raise RuntimeError("A Telegram user account session is required, not a bot session.")
        session_string = StringSession.save(client.session)
        if not session_string:
            raise RuntimeError("The session has no authorization key. Log in before exporting.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to overwrite an existing secret. On POSIX, restrict access to its owner.
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(session_string)
        print(f"Session saved to {output_path}. Copy its contents to TELETHON_STRING_SESSION.")
        print(
            "Keep this file private. Do not commit or share it. Stop the local bot before deploying."
        )
    finally:
        if telethon_client is not None:
            await telethon_client.disconnect()
        await stop_client()


if __name__ == "__main__":
    if OUTPUT_PATH.exists():
        raise SystemExit(
            f"{OUTPUT_PATH} already exists. Move or remove it before exporting a new session."
        )
    # Match the bot's Windows socket handling when Telethon uses a SOCKS proxy.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(export_session(), loop_factory=loop_factory)
