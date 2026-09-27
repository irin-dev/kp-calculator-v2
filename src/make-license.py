#!/usr/bin/env python3
"""
Генератор LICENSE (MIT) из переменной окружения LICENSE_HOLDER.

Зачем так, а не хранить LICENSE руками:
- имя правообладателя не зашито в публичный репозиторий, а берётся из .env;
- файл лицензии воспроизводим: заполнил .env → запустил скрипт;
- в .env.example лежит пустое значение, поэтому в git не попадает ничьё имя.

Запуск:
    python src/make-license.py

Переменные окружения ОС имеют приоритет над .env — это поведение
load_env_file() из app.py, здесь оно продублировано намеренно, чтобы
скрипт не зависел от порядка импорта.

Только стандартная библиотека — как и в остальном проекте.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, "..", ".env")
LICENSE_PATH = os.path.join(BASE_DIR, "..", "LICENSE")

HOLDER_ENV_KEY = "LICENSE_HOLDER"
FALLBACK_YEAR = "2026"

TEMPLATE = """MIT License

Copyright (c) {year} {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def strip_wrapping_quotes(value):
    """
    Снимает обрамляющие кавычки: в .env значение пишут как LICENSE_HOLDER="Имя",
    и без этого шага кавычки попали бы прямо в строку Copyright.
    Вызывается в обоих путях — и для .env, и для переменной окружения ОС.
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def load_env_file(path):
    """
    Примитивный парсер .env: строки вида `КЛЮЧ=значение`.
    Уже заданные переменные окружения не перебиваем — у них приоритет.
    """
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = strip_wrapping_quotes(value)
            if key and key not in os.environ:
                os.environ[key] = value
    return True


def resolve_holder():
    """
    Возвращает (имя, год) для строки Copyright.

    Имя обязательное: молча подставлять заглушку нельзя — в репозитории
    окажется лицензия с чужим или выдуманным правообладателем.
    """
    holder = strip_wrapping_quotes(os.environ.get(HOLDER_ENV_KEY, ""))
    if not holder:
        return None, None
    year = os.environ.get("LICENSE_YEAR", "").strip() or FALLBACK_YEAR
    return holder, year


def main():
    found = load_env_file(ENV_PATH)
    if not found:
        print("[FAIL] Файл .env не найден:", ENV_PATH, file=sys.stderr)
        print("       Создайте его из .env.example и заполните.", file=sys.stderr)
        return 1

    holder, year = resolve_holder()
    if not holder:
        print("[FAIL] Переменная %s пустая." % HOLDER_ENV_KEY, file=sys.stderr)
        print("       Впишите имя в .env (строка LICENSE_HOLDER=) и повторите.", file=sys.stderr)
        print("       Лицензия не создана — выдумывать правообладателя нельзя.", file=sys.stderr)
        return 2

    text = TEMPLATE.format(year=year, holder=holder)
    with open(LICENSE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print("[OK] LICENSE создан: %s" % LICENSE_PATH)
    print("     Правообладатель: %s (%s)" % (holder, year))
    print("     Лицензия: MIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
