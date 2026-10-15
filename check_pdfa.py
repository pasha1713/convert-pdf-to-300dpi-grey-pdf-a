#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пакетная проверка файлов *_pdfa.pdf на соответствие PDF/A-2b через veraPDF.
Аналог старого .bat-скрипта, но на Python.

Особенности:
  * корректная работа с кириллицей в именах файлов;
  * HTML-отчёты кладутся рядом с PDF (имя: <исходник>.html);
  * сводный отчёт -- otchet_pdfa.txt;
  * три статуса: PASS (rc=0), FAIL (rc=1), ERROR (rc>=2).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# ============================================================
#  Настройки -- правьте только этот блок
# ============================================================
VERAPDF = Path(r"C:\Program Files\veraPDF\verapdf.bat")
FLAVOUR = "2b"                          # PDF/A-2b
REPORT  = Path("otchet_pdfa.txt")
WORK_DIR = Path(".")
SUFFIX  = "_pdfa.pdf"                   # какие файлы валидировать

# ============================================================
#  Проверка перед запуском
# ============================================================
def preflight() -> None:
    if not VERAPDF.is_file():
        sys.exit(f"[FATAL] veraPDF не найден: {VERAPDF}")
    if not WORK_DIR.is_dir():
        sys.exit(f"[FATAL] Рабочая папка не найдена: {WORK_DIR.resolve()}")


# ============================================================
#  Запуск veraPDF на одном файле
# ============================================================
def validate(pdf: Path, html_out: Path) -> tuple[int, str]:
    """
    Запускает veraPDF, пишет HTML в html_out.
    Возвращает (returncode, stderr_or_stdout).
    """
    cmd = [
        str(VERAPDF),
        "--flavour", FLAVOUR,
        "--format", "html",
        str(pdf),
    ]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        return (99, f"exception: {e}")

    # HTML попадает в stdout, пишем его в файл
    try:
        html_out.write_text(res.stdout, encoding="utf-8")
    except Exception as e:
        return (98, f"cannot write html: {e}")

    # Для отчёта -- stderr (обычно содержит warnings veraPDF)
    tail = (res.stderr or "").strip()
    return (res.returncode, tail)


# ============================================================
#  Main
# ============================================================
def main() -> int:
    preflight()

    # Список PDF/A-файлов
    files = sorted(p for p in WORK_DIR.glob(f"*{SUFFIX}"))
    if not files:
        print(f"[WARN] Не найдено ни одного файла *{SUFFIX} в {WORK_DIR.resolve()}")
        return 1

    if REPORT.exists():
        REPORT.unlink()

    count = 0
    n_pass = 0
    n_fail = 0
    n_err = 0

    with REPORT.open("w", encoding="utf-8") as rep:
        rep.write("=" * 60 + "\n")
        rep.write(f" Отчёт о проверке PDF/A (veraPDF, PDF/A-{FLAVOUR})\n")
        rep.write(f" Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        rep.write("=" * 60 + "\n\n")

        for pdf in files:
            count += 1
            print(f"[{count}] Проверка: {pdf.name}")

            html_out = pdf.with_suffix(".html")   # СОПД_pdfa.pdf -> СОПД_pdfa.html

            rep.write("-" * 60 + "\n")
            rep.write(f"Файл: {pdf.name}\n")

            rc, tail = validate(pdf, html_out)

            if tail:
                rep.write(f"[veraPDF stderr]\n{tail}\n")

            if rc == 0:
                n_pass += 1
                rep.write("Результат: PASS\n")
                print("    PASS")
            elif rc == 1:
                n_fail += 1
                rep.write("Результат: FAIL\n")
                print("    FAIL")
            else:
                n_err += 1
                rep.write(f"Результат: ERROR (rc={rc}, инструмент не смог проверить)\n")
                print(f"    ERROR (rc={rc})")

            rep.write(f"HTML-отчёт: {html_out.name}\n")
            rep.write("\n")

    print()
    print("=" * 60)
    print(f"Всего проверено: {count}")
    print(f"PASS:  {n_pass}")
    print(f"FAIL:  {n_fail}")
    print(f"ERROR: {n_err}")
    print("=" * 60)
    print(f"Подробный отчёт сохранён в: {REPORT}")

    return 0 if (n_fail == 0 and n_err == 0) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        input("Press Enter to exit...")
        raise