#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пакетная конвертация PDF -> PDF/A-2b (grayscale, 300 dpi) через Ghostscript.

Функциональность:
  * копирует ICC-профиль srgb.icc в локальную папку _icc (без пробелов в пути);
  * генерирует канонический PDFA_def.ps (OutputIntent через /type /stream);
  * для файлов с префиксами из FILTERTEXT_PREFIXES применяет -dFILTERTEXT;
  * постобработка через pikepdf:
      - вставка XMP PDF/A-2b identification;
      - strip /CIDSet из FontDescriptor;
      - FIX TrueType post/maxp (numberOfGlyphs == numGlyphs);
      - пересохранение (EOL у stream/endstream, spacing у obj/endobj).

Опционально в GS включаются -dEmbedAllFonts=true и -dSubsetFonts=true,
что заставляет Ghostscript пересобрать встроенные шрифты.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# ============================================================
#  Настройки -- правьте только этот блок
# ============================================================
GS        = Path(r"C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe")
SRC_ICC   = Path(r"C:\Program Files\gs\gs10.08.0\iccprofiles\srgb.icc")
PDFIMAGES = Path(r"..\pdfimages")
REPORT    = Path("otchet.txt")

WORK_DIR     = Path(".")
ICC_LOCAL_D  = WORK_DIR / "_icc"
ICC_LOCAL    = ICC_LOCAL_D / "srgb.icc"
PDFA_DEF     = WORK_DIR / "PDFA_def.ps"
SUFFIX_SKIP  = "_pdfa"

# --- Компромиссный режим для .notdef ---
FILTERTEXT_PREFIXES = ("TextPart_",)
FILTERTEXT_DPI      = 300

# --- Постобработка pikepdf ---
STRIP_CIDSET       = True   # удалять /CIDSet из FontDescriptor
FIX_TRUETYPE_POST  = True   # править numberOfGlyphs в post-таблице
RESUBSET_FONTS     = True   # просить Ghostscript пересобрать шрифты

# ============================================================
#  Опциональный импорт pikepdf
# ============================================================
try:
    import pikepdf
    HAVE_PIKEPDF = True
except ImportError:
    pikepdf = None
    HAVE_PIKEPDF = False


# ============================================================
#  Канонический шаблон PDFA_def.ps (Artifex)
# ============================================================
PDFA_DEF_TEMPLATE = r"""%!
% PDFA_def.ps -- generated automatically by compress_to_pdfa.py

/ICCProfile (__ICC_PATH__) def

[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark

[{icc_PDFA}
<<
  /N 3
>>
/PUT pdfmark

[{icc_PDFA} ICCProfile (r) file /PUT pdfmark

[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark
[{OutputIntent_PDFA}
<<
  /Type /OutputIntent
  /S /GTS_PDFA1
  /DestOutputProfile {icc_PDFA}
  /OutputConditionIdentifier (sRGB IEC61966-2.1)
  /Info (sRGB IEC61966-2.1)
>>
/PUT pdfmark

[{Catalog} <</OutputIntents [ {OutputIntent_PDFA} ]>> /PUT pdfmark
"""


# ============================================================
#  XMP PDF/A-2b identification
# ============================================================
XMP_PDFA_ID = """<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>2</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


# ============================================================
#  Подготовка ICC и PDFA_def.ps
# ============================================================
def prepare_icc_and_pdfa_def() -> None:
    ICC_LOCAL_D.mkdir(exist_ok=True)
    if (not ICC_LOCAL.exists()) or (ICC_LOCAL.stat().st_size != SRC_ICC.stat().st_size):
        shutil.copyfile(SRC_ICC, ICC_LOCAL)
        print(f"[OK] Скопирован ICC: {SRC_ICC}  ->  {ICC_LOCAL}")
    else:
        print(f"[OK] Локальный ICC уже на месте: {ICC_LOCAL}")

    icc_ps_path = ICC_LOCAL.resolve().as_posix()
    content = PDFA_DEF_TEMPLATE.replace("__ICC_PATH__", icc_ps_path)

    if PDFA_DEF.exists():
        old = PDFA_DEF.read_text(encoding="ascii", errors="replace")
        if (f"/ICCProfile ({icc_ps_path})" in old
                and "/type /stream /OBJ pdfmark" in old
                and "/DOCINFO" not in old):
            print(f"[OK] Использую существующий {PDFA_DEF}")
            return
        PDFA_DEF.unlink()

    PDFA_DEF.write_text(content, encoding="ascii")
    print(f"[OK] Создан {PDFA_DEF} с ICC = {icc_ps_path}")


# ============================================================
#  Проверки перед запуском
# ============================================================
def preflight() -> None:
    if not GS.is_file():
        sys.exit(f"[FATAL] Ghostscript не найден: {GS}")
    if not SRC_ICC.is_file():
        icc_dir = SRC_ICC.parent
        available = sorted(p.name for p in icc_dir.glob("*.icc")) if icc_dir.is_dir() else []
        sys.exit(
            f"[FATAL] Исходный ICC-профиль не найден: {SRC_ICC}\n"
            f"        Содержимое {icc_dir}: {available}"
        )
    prepare_icc_and_pdfa_def()
    if not PDFIMAGES.exists():
        print(f"[WARN] pdfimages не найден: {PDFIMAGES} -- отчёт без списка изображений")
    if not HAVE_PIKEPDF:
        print("[WARN] pikepdf не установлен -- постобработка отключена.")
        print("       Установите:  pip install pikepdf")
    else:
        print("[OK] pikepdf найден -- постобработка включена.")
    print(f"[i] Файлы с префиксами {FILTERTEXT_PREFIXES} обрабатываются с -dFILTERTEXT.")


def needs_filtertext(name: str) -> bool:
    return any(name.startswith(p) for p in FILTERTEXT_PREFIXES)


# ============================================================
#  Конвертация через Ghostscript
# ============================================================
def gs_convert(src: Path, dst: Path, filtertext: bool) -> tuple[bool, str]:
    icc_dir_abs  = ICC_LOCAL_D.resolve().as_posix()
    icc_file_abs = ICC_LOCAL.resolve().as_posix()
    pdfadef_abs  = PDFA_DEF.resolve().as_posix()
    src_abs      = src.resolve().as_posix()
    dst_abs      = dst.resolve().as_posix()

    cmd = [
        str(GS),
        "-dNOSAFER",
        f"--permit-file-read={icc_file_abs}",
        f"--permit-file-read={icc_dir_abs}/",
        f"--permit-file-read={pdfadef_abs}",
        "-dPDFA=2",
        "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
        "-sColorConversionStrategy=Gray",
        "-sProcessColorModel=DeviceGray",
        f"-sOutputICCProfile={icc_file_abs}",
        "-dOverrideICC",
        "-dPDFACompatibilityPolicy=1",
        "-dPreserveAnnots=false",
    ]

    if RESUBSET_FONTS:
        cmd += [
            "-dEmbedAllFonts=true",
            "-dSubsetFonts=true",
            "-dCompressFonts=true",
            "-dCompatibilityLevel=1.7",
        ]

    if filtertext:
        cmd += ["-dFILTERTEXT", f"-r{FILTERTEXT_DPI}"]

    cmd += [
        "-dDownsampleGrayImages=true",
        "-dGrayImageResolution=300",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dDownsampleMonoImages=true",
        "-dMonoImageResolution=300",
        "-dMonoImageDownsampleType=/Bicubic",
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={dst_abs}",
        pdfadef_abs,
        src_abs,
    ]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="cp866",
            errors="replace",
        )
    except Exception as e:
        return (False, f"exception: {e}")

    if res.returncode != 0:
        return (False, res.stdout or f"rc={res.returncode}")
    if not dst.is_file() or dst.stat().st_size == 0:
        return (False, "output file missing or empty")
    if "PDF/A processing aborted" in res.stdout:
        return (False, "PDF/A processing aborted by GS")

    return (True, res.stdout or "")


# ============================================================
#  FIX TrueType post/maxp
# ============================================================
def fix_truetype_post_table(data: bytes) -> tuple[bytes, str]:
    """
    Правит numberOfGlyphs в таблице 'post' TrueType, чтобы он совпадал
    с numGlyphs из таблицы 'maxp'. Возвращает (bytes, статус).
    Если править нечего или нельзя -- возвращает исходные байты.
    """
    if len(data) < 12:
        return (data, "too small")

    try:
        sfnt_version = int.from_bytes(data[0:4], "big")
        # 0x00010000 = TrueType, 0x74727565 = 'true', 0x4F54544F = 'OTTO'
        if sfnt_version not in (0x00010000, 0x74727565):
            return (data, f"sfnt {sfnt_version:#x} not tt")
        num_tables = int.from_bytes(data[4:6], "big")
    except Exception as e:
        return (data, f"parse header: {e}")

    maxp_offset = post_offset = None
    for i in range(num_tables):
        base = 12 + i * 16
        if base + 16 > len(data):
            break
        tag = data[base:base + 4]
        offset = int.from_bytes(data[base + 8:base + 12], "big")
        if tag == b"maxp":
            maxp_offset = offset
        elif tag == b"post":
            post_offset = offset

    if maxp_offset is None:
        return (data, "no maxp")
    if post_offset is None:
        return (data, "no post")
    if maxp_offset + 6 > len(data):
        return (data, "maxp out of range")
    if post_offset + 34 > len(data):
        return (data, "post out of range")

    num_glyphs = int.from_bytes(data[maxp_offset + 4:maxp_offset + 6], "big")
    post_version = int.from_bytes(data[post_offset:post_offset + 4], "big")

    # numberOfGlyphs присутствует только в post v2.0
    if post_version != 0x00020000:
        return (data, f"post v{post_version:#x}, skip")

    old_num = int.from_bytes(data[post_offset + 32:post_offset + 34], "big")
    if old_num == num_glyphs:
        return (data, f"ok ({num_glyphs})")

    new_data = bytearray(data)
    new_data[post_offset + 32:post_offset + 34] = num_glyphs.to_bytes(2, "big")
    return (bytes(new_data), f"fixed {old_num} -> {num_glyphs}")


def fix_fonts_in_pdf(pdf) -> tuple[int, int, int]:
    """
    Возвращает (total_fonts, cidset_removed, post_fixed).
    """
    total = cidset_removed = post_fixed = 0

    # Проходим по всем объектам, ищем FontDescriptor
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary):
            continue
        if str(obj.get("/Type", "")) != "/FontDescriptor":
            continue

        # --- CIDSet ---
        if STRIP_CIDSET and "/CIDSet" in obj:
            try:
                del obj["/CIDSet"]
                cidset_removed += 1
            except Exception:
                pass

        # --- FontFile2 (TrueType) ---
        if FIX_TRUETYPE_POST and "/FontFile2" in obj:
            total += 1
            try:
                ff = obj["/FontFile2"]
                raw = bytes(ff.read_bytes())
                new_raw, status = fix_truetype_post_table(raw)
                if new_raw is not raw and len(new_raw) == len(raw):
                    # записываем обратно
                    ff.write(new_raw)
                    # синхронизируем Length1, если он есть
                    if "/Length1" in ff:
                        ff["/Length1"] = len(new_raw)
                    if status.startswith("fixed"):
                        post_fixed += 1
            except Exception:
                pass

    return (total, cidset_removed, post_fixed)


# ============================================================
#  Постобработка pikepdf
# ============================================================
def pikepdf_postprocess(pdf_path: Path) -> tuple[bool, str]:
    if not HAVE_PIKEPDF:
        return (True, "skipped (pikepdf not installed)")

    tmp_path = pdf_path.with_suffix(".tmp.pdf")
    try:
        with pikepdf.open(pdf_path) as pdf:
            # --- 1. Шрифты: strip CIDSet + fix post/maxp ---
            try:
                total_fonts, cid_removed, post_fixed = fix_fonts_in_pdf(pdf)
            except Exception:
                total_fonts = cid_removed = post_fixed = 0

            # --- 2. XMP PDF/A-2b identification ---
            try:
                with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                    meta.load(XMP_PDFA_ID)
            except Exception:
                try:
                    xmp_bytes = XMP_PDFA_ID.encode("utf-8")
                    stream = pdf.make_stream(xmp_bytes)
                    stream["/Type"] = pikepdf.Name("/Metadata")
                    stream["/Subtype"] = pikepdf.Name("/XML")
                    pdf.Root["/Metadata"] = pdf.make_indirect(stream)
                except Exception:
                    pass

            # --- 3. Пересохраняем ---
            pdf.save(
                tmp_path,
                linearize=False,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.disable,
                recompress_flate=True,
            )

        shutil.move(str(tmp_path), str(pdf_path))
        return (
            True,
            f"ok (FontFile2={total_fonts}, CIDSet removed={cid_removed}, post fixed={post_fixed})",
        )
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return (False, f"error: {e}")


# ============================================================
#  Полный цикл для одного файла
# ============================================================
def convert(src: Path, dst: Path, report_fh) -> bool:
    filtertext = needs_filtertext(src.name)
    tag = " [FILTERTEXT]" if filtertext else ""
    print(f"    -> {dst.name}{tag}")

    ok, msg = gs_convert(src, dst, filtertext)
    if not ok:
        report_fh.write(f"PDF/A ERROR: GS conversion failed for {src.name}\n")
        if msg:
            report_fh.write(msg + "\n")
        return False

    ok, msg = pikepdf_postprocess(dst)
    report_fh.write(f"[postprocess] {src.name}: {msg}\n")
    if not ok:
        report_fh.write(f"PDF/A WARNING: postprocess failed: {msg}\n")

    return True


# ============================================================
#  pdfimages -list для отчёта
# ============================================================
def list_images(pdf: Path, report_fh) -> None:
    if not PDFIMAGES.exists():
        return
    exe = PDFIMAGES
    if PDFIMAGES.is_dir():
        exe = PDFIMAGES / "pdfimages.exe"
        if not exe.is_file():
            return
    try:
        res = subprocess.run(
            [str(exe), "-list", str(pdf)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        report_fh.write(res.stdout)
    except Exception as e:
        report_fh.write(f"[pdfimages error] {e}\n")


# ============================================================
#  Main
# ============================================================
def main() -> int:
    preflight()

    if REPORT.exists():
        REPORT.unlink()

    sources = sorted(
        p for p in WORK_DIR.glob("*.pdf")
        if not p.stem.endswith(SUFFIX_SKIP)
    )

    total = len(sources)
    done = 0
    fail = 0

    with REPORT.open("w", encoding="utf-8") as report_fh:
        for i, src in enumerate(sources, start=1):
            print(f"[{i}] Processing: {src.name}")
            dst = src.with_name(f"{src.stem}_pdfa.pdf")

            if convert(src, dst, report_fh):
                done += 1
                report_fh.write(f"\n====\nFile: {dst.name}\n====\n")
                list_images(dst, report_fh)
                report_fh.write("\n")
            else:
                fail += 1

    print()
    print(f"Done. Total: {total}, OK: {done}, errors: {fail}.")
    print(f"Report saved to {REPORT}.")
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