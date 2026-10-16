#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Накладывает OCR-слой на PDF/A-файлы, у которых текст был растеризован.
Использует ocrmypdf (Tesseract + Ghostscript + qpdf под капотом).

Что делает:
  * для файлов из TARGET_PREFIXES проверяет, есть ли уже текстовый слой
    через pdftotext (Poppler);
  * если текста нет -- запускает ocrmypdf с --output-type pdfa-2,
    --force-ocr, языками rus+eng;
  * результат заменяет исходный *_pdfa.pdf.

После запуска:
  * визуально файл не меняется;
  * поиск, выделение и копирование текста работают;
  * PDF/A-2b остаётся валидным.

Зависимости:
  pip install ocrmypdf
  tesseract с языками rus+eng
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# ============================================================
#  Настройки
# ============================================================
TARGET_PREFIXES = ("TextPart_",)     # какие файлы OCR-ить
LANG            = "rus+eng"          # языки Tesseract
WORK_DIR        = Path(".")
OCR_OPTIMIZE    = "1"                # уровень оптимизации ocrmypdf

# ============================================================
#  Служебные функции
# ============================================================
def has_text_layer(pdf: Path) -> bool:
    """Проверка через pdftotext (Poppler): есть ли уже реальный текст."""
    try:
        res = subprocess.run(
            ["pdftotext", "-l", "1", str(pdf), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        # >20 символов на первой странице -- считаем, что слой есть
        return len((res.stdout or "").strip()) > 20
    except FileNotFoundError:
        # pdftotext нет -- не можем проверить, идём в OCR
        return False
    except Exception:
        return False


def ocr_one(pdf: Path) -> bool:
    out = pdf.with_name(pdf.stem + "_ocr_tmp.pdf")
    print(f"[OCR] {pdf.name} ...")
    try:
        res = subprocess.run(
            [
                "ocrmypdf",
                "--output-type", "pdfa-2",
                "--language", LANG,
                "--force-ocr",       # OCR даже если что-то нашлось
                "--optimize", OCR_OPTIMIZE,
                "--skip-big", "50",  # не OCR-ить картинки больше 50 Мпк
                "--jobs", "2",
                str(pdf),
                str(out),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print("[FATAL] ocrmypdf не найден. Установите: pip install ocrmypdf")
        return False

    if res.returncode != 0:
        print(f"[FAIL] {pdf.name}")
        print(res.stdout[-800:])
        if out.exists():
            try:
                out.unlink()
            except Exception:
                pass
        return False

    shutil.move(str(out), str(pdf))
    print(f"[OK] {pdf.name} обновлён (OCR-слой добавлен)")
    return True


# ============================================================
#  Main
# ============================================================
def main() -> int:
    files = sorted(WORK_DIR.glob("*_pdfa.pdf"))
    targets = [
        f for f in files
        if any(f.name.startswith(p) for p in TARGET_PREFIXES)
    ]
    if not targets:
        print(f"[WARN] Не найдено файлов с префиксами {TARGET_PREFIXES}")
        return 1

    ok = skip = fail = 0
    for f in targets:
        if has_text_layer(f):
            print(f"[SKIP] {f.name}: текстовый слой уже есть")
            skip += 1
            continue
        if ocr_one(f):
            ok += 1
        else:
            fail += 1

    print()
    print("=" * 60)
    print(f"Обработано: {ok}, пропущено: {skip}, ошибок: {fail}")
    print("=" * 60)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        input("Press Enter to exit...")
        raise