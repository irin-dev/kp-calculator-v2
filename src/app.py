"""
app.py — локальный сервер калькулятора КП (версия 2)
====================================================

Зачем нужен сервер, если сайт статический?
  * Чтобы открыть index.html по адресу http://127.0.0.1:8000
    (браузер не даёт fetch() локальных .json из file:// из-за CORS).
  * Чтобы отдать РЕКВИЗИТЫ из .env — их нельзя класть в фронтенд-код.

Запуск (из папки edu/kp-calculator-v2):
    python src/app.py
    → http://127.0.0.1:8000

.env читается в две строчки:
  1. если переменной нет в окружении ОС — берём из файла .env
  2. отдаём как /data/config.json (псевдоним: /config.json)

Это «студенческий» вариант: без внешних библиотек (только стандартный
модуль http.server), чтобы ничего не пришлось устанавливать.
"""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from calculator import evaluate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # src/
ROOT = BASE_DIR
DATA_DIR = os.path.join(BASE_DIR, "..", "data")         # data/ (quiz.json)
ENV_PATH = os.path.join(BASE_DIR, "..", ".env")         # .env (реквизиты)

# Соответствие переменных окружения → полям конфига, который
# фронтенд будет показывать в шапке КП.
CONFIG_KEYS = {
    "name": "COMPANY_NAME",
    "tagline": "COMPANY_TAGLINE",
    "phone": "COMPANY_PHONE",
    "email": "COMPANY_EMAIL",
    "telegram": "COMPANY_TG",
    "legal": "COMPANY_LEGAL",
}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def load_env_file(path):
    """
    Примитивный парсер .env: строки вида `КЛЮЧ=значение`.
    Не трогаем уже заданные переменные окружения — у них приоритет.
    Комментарии (#) и пустые строки пропускаем.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # Отключаем кеш — чтобы правки index.html/main.js сразу виделись
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        # Главная страница
        if path == "/":
            self.path = "/static/index.html"
            super().do_GET()
            return

        # Конфиг с реквизитами — собирается из .env на лету
        if path in ("/config.json", "/data/config.json"):
            self._send_json({
                "company": {field: os.environ.get(env_key, "") for field, env_key in CONFIG_KEYS.items()}
            })
            return

        # Данные квиза из data/ (с защитой от path traversal)
        if path.startswith("/data/"):
            rel = path[len("/data/"):]
            full = os.path.realpath(os.path.join(DATA_DIR, rel))
            if not full.startswith(os.path.realpath(DATA_DIR)):
                self.send_error(403)
                return
            try:
                body = open(full, "rb").read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(os.path.splitext(full)[1], "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def _send_json(self, obj):
        """Отправляет JSON-ответ 200."""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """
        POST /api/estimate  — фронтенд присылает ответы, мы возвращаем
        полный результат расчёта (формула в calculator.py, JS её не дублирует).
        """
        if self.path.split("?")[0] != "/api/estimate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            answers = json.loads(raw) if raw else {}
        except (ValueError, UnicodeDecodeError):
            self.send_error(400, "Bad JSON")
            return
        self._send_json(evaluate(answers))


def main():
    load_env_file(ENV_PATH)                       # реквизиты из .env → os.environ
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Калькулятор КП v2: http://127.0.0.1:{port}")
    print("Ctrl+C для остановки")
    server.serve_forever()


if __name__ == "__main__":
    main()