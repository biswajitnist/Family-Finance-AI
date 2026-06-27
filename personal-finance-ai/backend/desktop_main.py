import os
import socket
import threading
import time
import webbrowser

import uvicorn

os.environ.setdefault("FINANCE_DESKTOP", "1")

from app.main import app  # noqa: E402


def _available_port(start: int = 8765, attempts: int = 25) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Ledger Local could not find an available local port.")


def _open_application(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    port = _available_port()
    url = f"http://127.0.0.1:{port}"
    if os.getenv("FINANCE_NO_BROWSER") != "1":
        threading.Thread(target=_open_application, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
