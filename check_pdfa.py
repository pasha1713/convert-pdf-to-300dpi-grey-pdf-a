#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пакетная проверка файлов *.pdf:
  1) на соответствие PDF/A-2b через veraPDF;
  2) что эффективное разрешение изображений НЕ ПРЕВЫШАЕТ 300 dpi;
  3) что все изображения в grayscale.

DPI считается через `pdfimages -list` (Poppler) -- это даёт точный результат,
учитывающий реальный размер картинки на странице (матрицу cm в content stream).
Если pdfimages не найден, используется грубая fallback-формула (по MediaBox).

HTML-отчёты veraPDF кладутся рядом с PDF.
Сводный отчёт -- otchet_pdfa.txt.

Зависимости:
  pip install pikepdf        (для проверки grayscale)
  pdfimages из Poppler       (для точной проверки dpi)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import pikepdf
    HAVE_PIKEPDF = True
except ImportError:
    pikepdf = None
    HAVE_PIKEPDF = False


# ============================================================
#  Настройки -- правьте только этот блок
# ============================================================
VERAPDF  = Path(r"C:\Program Files\veraPDF\verapdf.bat")
PDFIMAGES = Path(r"..\pdfimages\pdfimages.exe")   # <-- при необходимости поправьте
FLAVOUR  = "2b"
REPORT   = Path("otchet_pdfa.txt")
WORK_DIR = Path(".")
SUFFIX   = "_pdfa.pdf"

# --- Требования к изображениям ---
MAX_DPI            = 300    # не должно ПРЕВЫШАТЬ это значение
DPI_TOLERANCE      = 5      # допуск: dpi <= MAX_DPI + tolerance
EXPECTED_GRAYSCALE = True   # все изображения должны быть в оттенках серого


# ============================================================
#  Поиск pdfimages
# ============================================================
def find_pdfimages() -> Path | None:
    """Ищет pdfimages.exe по типичным путям."""
    if PDFIMAGES.is_file():
        return PDFIMAGES
    candidates = [
        Path(r"..\pdfimages\pdfimages.exe"),
        Path(r"..\pdfimages\bin\pdfimages.exe"),
        Path(r"C:\Program Files\poppler\Library\bin\pdfimages.exe"),
        Path(r"C:\Program Files\poppler\bin\pdfimages.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    on_path = shutil.which("pdfimages")
    if on_path:
        return Path(on_path)
    return None


# ============================================================
#  veraPDF
# ============================================================
def validate_pdfa(pdf: Path, html_out: Path) -> tuple[int, str]:
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

    try:
        html_out.write_text(res.stdout, encoding="utf-8")
    except Exception as e:
        return (98, f"cannot write html: {e}")

    tail = (res.stderr or "").strip()
    return (res.returncode, tail)


# ============================================================
#  Проверка dpi через pdfimages -list
# ============================================================
# Пример строки вывода:
#   1     0 image    3565  2561  gray    1   8  jpeg   no        24  0   300   300  750K 8.4%
# Поля: page num type width height color comp bpc enc interp object ID x-ppi y-ppi size ratio

def parse_pdfimages_list(text: str) -> list[dict]:
    """
    Возвращает список словарей:
      {"page": int, "num": int, "type": str, "width": int, "height": int,
       "color": str, "x_ppi": float, "y_ppi": float}
    Строки, где x-ppi или y-ppi равны 0 (неизвестно), пропускаются.
    """
    items: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("page") or line.startswith("-"):
            continue
        # Разбиваем по пробелам (могут быть \r)
        parts = line.split()
        # Минимум 15 полей: page num type width height color comp bpc enc interp objid objgen xppi yppi size ratio
        if len(parts) < 15:
            continue
        try:
            page  = int(parts[0])
            num   = int(parts[1])
            typ   = parts[2]
            w     = int(parts[3])
            h     = int(parts[4])
            color = parts[5]
            x_ppi = float(parts[12])
            y_ppi = float(parts[13])
        except ValueError:
            continue
        if x_ppi <= 0 or y_ppi <= 0:
            continue
        items.append({
            "page": page,
            "num": num,
            "type": typ,
            "width": w,
            "height": h,
            "color": color,
            "x_ppi": x_ppi,
            "y_ppi": y_ppi,
        })
    return items


def check_images_via_pdfimages(pdf: Path, exe: Path) -> dict:
    """
    Возвращает:
      {"count": N, "dpi_ok": M, "gray_ok": K, "max_dpi_seen": ..., "issues": [...]}
    или None при ошибке вызова pdfimages.
    """
    try:
        res = subprocess.run(
            [str(exe), "-list", str(pdf)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        return {"error": f"pdfimages exception: {e}"}

    if res.returncode != 0:
        return {"error": f"pdfimages rc={res.returncode}"}

    items = parse_pdfimages_list(res.stdout)
    result = {
        "count": 0,
        "dpi_ok": 0,
        "gray_ok": 0,
        "max_dpi_seen": 0.0,
        "issues": [],
    }

    lo_lim = MAX_DPI + DPI_TOLERANCE
    for it in items:
        # Пропускаем smask -- это маски, у них своя логика
        if it["type"] == "smask":
            continue
        result["count"] += 1
        dpi_eff = max(it["x_ppi"], it["y_ppi"])
        if dpi_eff > result["max_dpi_seen"]:
            result["max_dpi_seen"] = dpi_eff
        if dpi_eff <= lo_lim:
            result["dpi_ok"] += 1
        else:
            result["issues"].append(
                f"стр.{it['page']} #{it['num']} "
                f"({it['width']}x{it['height']}): "
                f"dpi ≈ {dpi_eff:.0f} (лимит ≤ {lo_lim})"
            )
        if it["color"] == "gray":
            result["gray_ok"] += 1
        else:
            result["issues"].append(
                f"стр.{it['page']} #{it['num']}: цвет={it['color']} (не gray)"
            )
    return result


# ============================================================
#  Fallback-проверка через pikepdf (грубо, по MediaBox)
# ============================================================
def _obj_str_name(o) -> str:
    try:
        return str(o)
    except Exception:
        return "?"


def _is_gray_colorspace(cs) -> bool:
    if isinstance(cs, pikepdf.Name):
        return str(cs) in ("/DeviceGray", "/G")
    if isinstance(cs, pikepdf.Array):
        if len(cs) >= 1:
            head = cs[0]
            if isinstance(head, pikepdf.Name):
                s = str(head)
                if s in ("/DeviceGray", "/CalGray", "/G"):
                    return True
                if s == "/ICCBased" and len(cs) >= 2:
                    try:
                        icc_stream = cs[1]
                        n = icc_stream.get("/N", None)
                        return int(n) == 1
                    except Exception:
                        return False
    return False


def check_images_via_pikepdf(pdf: Path) -> dict:
    """
    Грубая проверка (учитывает только MediaBox, без content stream).
    Используется, если pdfimages недоступен.
    """
    result = {
        "count": 0, "dpi_ok": 0, "gray_ok": 0,
        "max_dpi_seen": 0.0, "issues": [],
        "fallback": True,
    }
    if not HAVE_PIKEPDF:
        return result
    try:
        with pikepdf.open(pdf) as doc:
            for page_index, page in enumerate(doc.pages, start=1):
                res = page.get("/Resources", None)
                if res is None:
                    continue
                xo = res.get("/XObject", None)
                if xo is None:
                    continue
                mb = page.get("/MediaBox", None)
                if mb is None or len(mb) < 4:
                    continue
                page_w_pt = float(mb[2]) - float(mb[0])
                page_h_pt = float(mb[3]) - float(mb[1])

                for xname, xobj in xo.items():
                    try:
                        if xobj.get("/Subtype", None) != pikepdf.Name("/Image"):
                            continue
                    except Exception:
                        continue
                    result["count"] += 1
                    cs = xobj.get("/ColorSpace", None)
                    if _is_gray_colorspace(cs):
                        result["gray_ok"] += 1
                    else:
                        result["issues"].append(
                            f"стр.{page_index} {xname}: ColorSpace={_obj_str_name(cs)}"
                        )
                    try:
                        w_px = int(xobj.get("/Width", 0))
                        h_px = int(xobj.get("/Height", 0))
                    except Exception:
                        continue
                    if page_w_pt <= 0 or page_h_pt <= 0:
                        continue
                    dpi = max(w_px / (page_w_pt / 72), h_px / (page_h_pt / 72))
                    if dpi > result["max_dpi_seen"]:
                        result["max_dpi_seen"] = dpi
                    if dpi <= MAX_DPI + DPI_TOLERANCE:
                        result["dpi_ok"] += 1
                    else:
                        result["issues"].append(
                            f"стр.{page_index} {xname}: dpi ≈ {dpi:.0f} "
                            f"(эвристика, лимит ≤ {MAX_DPI + DPI_TOLERANCE})"
                        )
    except Exception as e:
        result["issues"].append(f"pikepdf error: {e}")
    return result


# ============================================================
#  Проверки перед запуском
# ============================================================
def preflight() -> Path | None:
    if not VERAPDF.is_file():
        sys.exit(f"[FATAL] veraPDF не найден: {VERAPDF}")
    if not WORK_DIR.is_dir():
        sys.exit(f"[FATAL] Рабочая папка не найдена: {WORK_DIR.resolve()}")
    if EXPECTED_GRAYSCALE and not HAVE_PIKEPDF:
        sys.exit(
            "[FATAL] Для проверки grayscale нужен pikepdf:\n"
            "        pip install pikepdf"
        )
    pdfimages = find_pdfimages()
    if pdfimages is None:
        print("[WARN] pdfimages не найден, dpi будет проверяться эвристикой по MediaBox")
        print("       (точность ниже, возможны ложные срабатывания)")
    else:
        print(f"[OK] pdfimages найден: {pdfimages}")
    return pdfimages


# ============================================================
#  Main
# ============================================================
def main() -> int:
    pdfimages = preflight()

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
        rep.write(f" + проверка dpi (≤ {MAX_DPI}) и grayscale\n")
        rep.write(f" Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        rep.write("=" * 60 + "\n\n")

        for pdf in files:
            count += 1
            print(f"[{count}] Проверка: {pdf.name}")

            html_out = pdf.with_suffix(".html")

            rep.write("-" * 60 + "\n")
            rep.write(f"Файл: {pdf.name}\n")

            rc, tail = validate_pdfa(pdf, html_out)
            if tail:
                rep.write(f"[veraPDF stderr]\n{tail}\n")

            if rc == 0:
                pdfa_ok = True
                rep.write("PDF/A-2b: PASS\n")
                print("    PDF/A-2b: PASS")
            elif rc == 1:
                pdfa_ok = False
                rep.write("PDF/A-2b: FAIL\n")
                print("    PDF/A-2b: FAIL")
            else:
                pdfa_ok = False
                rep.write(f"PDF/A-2b: ERROR (rc={rc})\n")
                print(f"    PDF/A-2b: ERROR (rc={rc})")
            rep.write(f"HTML-отчёт: {html_out.name}\n")

            # --- Изображения: dpi + grayscale ---
            img = None
            if pdfimages is not None:
                img = check_images_via_pdfimages(pdf, pdfimages)
                if "error" in img:
                    rep.write(f"[pdfimages] {img['error']}, fallback to pikepdf\n")
                    img = None
            if img is None:
                img = check_images_via_pikepdf(pdf)

            max_dpi_str = (
                f"{img['max_dpi_seen']:.0f}"
                if img["count"] > 0 and img["max_dpi_seen"] > 0
                else "—"
            )
            extra = " (fallback)" if img.get("fallback") else ""
            rep.write(
                f"Изображений: {img['count']}  "
                f"(dpi OK: {img['dpi_ok']}, gray: {img['gray_ok']}, "
                f"max dpi: {max_dpi_str}){extra}\n"
            )
            for issue in img["issues"]:
                rep.write(f"  ! {issue}\n")

            imgs_ok = (
                img["count"] == 0
                or (
                    img["dpi_ok"] == img["count"]
                    and (not EXPECTED_GRAYSCALE or img["gray_ok"] == img["count"])
                )
            )

            if pdfa_ok and imgs_ok:
                n_pass += 1
                rep.write("Результат: PASS\n")
                print("    Images: OK")
            elif not pdfa_ok:
                n_fail += 1
                rep.write("Результат: FAIL (PDF/A-2b)\n")
                print("    Result: FAIL")
            else:
                n_fail += 1
                rep.write("Результат: FAIL (dpi/grayscale)\n")
                print("    Images: FAIL")
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