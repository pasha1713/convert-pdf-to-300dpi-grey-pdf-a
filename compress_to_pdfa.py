#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пакетная конвертация PDF -> PDF/A-2b через Ghostscript.

Возможности:
  * ASCII-песочница (C:\\Temp\\pdfa_work_*);
  * -dNOSAFER + --permit-file-read=* -- снимают sandbox;
  * даунсэмплинг всего, что > 300 dpi;
  * авто-обесцвечивание content streams (rg/RG/k/K -> g/G);
  * исключения: для файлов из KEEP_COLOR_PREFIXES
      - Ghostscript запускается с -sColorConversionStrategy=LeaveColorUnchanged
        (GS НЕ трогает цвета),
      - pikepdf-шаг обесцвечивания пропускается;
  * постобработка pikepdf: XMP PDF/A-2b, strip /CIDSet,
    fix TrueType post/maxp, пересохранение.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ============================================================
#  Настройки
# ============================================================
GS        = Path(r"C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe")
SRC_ICC   = Path(r"C:\Program Files\gs\gs10.08.0\iccprofiles\srgb.icc")
PDFIMAGES = Path(r"..\pdfimages")
REPORT    = Path("otchet.txt")

WORK_DIR     = Path(".")
ICC_LOCAL_D  = WORK_DIR / "_icc"
ICC_LOCAL    = ICC_LOCAL_D / "srgb.icc"
SUFFIX_SKIP  = "_pdfa"

ASCII_TMP_CANDIDATES = [
    r"C:\Temp",
    r"C:\Windows\Temp",
    r"C:\ProgramData\Temp",
]

# --- Растеризация текста (не применяется) ---
FILTERTEXT_PREFIXES: tuple[str, ...] = ()
FILTERTEXT_DPI = 300

# --- Постобработка pikepdf ---
STRIP_CIDSET       = True
FIX_TRUETYPE_POST  = True
RESUBSET_FONTS     = True

# --- Даунсэмплинг ---
DOWNSAMPLE_THRESHOLD = 1.0

# --- Обесцвечивание ---
# Файлы, которые обесцвечивать НЕ надо.
# Для них:
#   * Ghostscript запускается с LeaveColorUnchanged
#   * pikepdf-обесцвечивание пропускается
KEEP_COLOR_PREFIXES: tuple[str, ...] = (
    "SchemeDisposition",
)

# ============================================================
#  Импорт pikepdf
# ============================================================
try:
    import pikepdf
    HAVE_PIKEPDF = True
except ImportError:
    pikepdf = None
    HAVE_PIKEPDF = False


# ============================================================
#  Шаблон PDFA_def.ps
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
#  XMP PDF/A-2b
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
#  Утилиты
# ============================================================
def _is_strict_ascii(p: str) -> bool:
    try:
        p.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def get_ascii_tempdir() -> Path:
    for cand_str in ASCII_TMP_CANDIDATES:
        cand = Path(cand_str)
        try:
            if not _is_strict_ascii(cand_str):
                continue
            cand.mkdir(parents=True, exist_ok=True)
            resolved = cand.resolve()
            if not _is_strict_ascii(str(resolved)):
                continue
            probe = resolved / f".pdfa_probe_{os.getpid()}"
            probe.write_bytes(b"x")
            probe.unlink()
            return resolved
        except Exception:
            continue
    sys.exit("[FATAL] Нет ASCII-совместимой временной папки. Создайте C:\\Temp.")


def prepare_local_icc() -> None:
    ICC_LOCAL_D.mkdir(exist_ok=True)
    if (not ICC_LOCAL.exists()) or (ICC_LOCAL.stat().st_size != SRC_ICC.stat().st_size):
        shutil.copyfile(SRC_ICC, ICC_LOCAL)
        print(f"[OK] Скопирован ICC: {SRC_ICC}  ->  {ICC_LOCAL}")
    else:
        print(f"[OK] Локальный ICC уже на месте: {ICC_LOCAL}")


# ============================================================
#  Проверки
# ============================================================
def preflight() -> Path:
    if not GS.is_file():
        sys.exit(f"[FATAL] Ghostscript не найден: {GS}")
    if not SRC_ICC.is_file():
        sys.exit(f"[FATAL] ICC не найден: {SRC_ICC}")
    prepare_local_icc()
    ascii_tmp = get_ascii_tempdir()
    print(f"[OK] Рабочая ASCII-папка для GS: {ascii_tmp}")
    if not PDFIMAGES.exists():
        print(f"[WARN] pdfimages не найден: {PDFIMAGES}")
    if not HAVE_PIKEPDF:
        print("[WARN] pikepdf не установлен.")
    else:
        print("[OK] pikepdf найден.")
    print("[i] FILTERTEXT не применяется.")
    print(f"[i] Файлы, где цвет СОХРАНЯЕТСЯ: {KEEP_COLOR_PREFIXES}")
    return ascii_tmp


def needs_filtertext(name: str) -> bool:
    return any(name.startswith(p) for p in FILTERTEXT_PREFIXES)


def keep_color(name: str) -> bool:
    return any(name.startswith(p) for p in KEEP_COLOR_PREFIXES)


# ============================================================
#  Ghostscript
# ============================================================
def gs_convert(src: Path, dst: Path, ascii_tmp: Path, report_fh) -> tuple[bool, str]:
    work_name = f"pdfa_work_{os.getpid()}_{int(time.time() * 1000) % 10**9}"
    work_dir = ascii_tmp / work_name

    if not _is_strict_ascii(str(work_dir)):
        return (False, f"work_dir is not ASCII: {work_dir!r}")

    filtertext = needs_filtertext(src.name)
    keep_c     = keep_color(src.name)

    try:
        work_dir.mkdir(parents=True, exist_ok=False)

        tmp_src = work_dir / "input.pdf"
        shutil.copyfile(src, tmp_src)

        tmp_icc = work_dir / "srgb.icc"
        shutil.copyfile(ICC_LOCAL, tmp_icc)

        if not tmp_icc.is_file() or tmp_icc.stat().st_size == 0:
            return (False, f"ICC copy is empty: {tmp_icc}")

        icc_ps_path = tmp_icc.as_posix()

        tmp_def = work_dir / "PDFA_def.ps"
        def_content = PDFA_DEF_TEMPLATE.replace("__ICC_PATH__", icc_ps_path)
        tmp_def.write_bytes(def_content.encode("ascii"))

        tmp_out = work_dir / "output.pdf"
        out_ps_path = tmp_out.as_posix()

        cmd = [
            str(GS),
            "-dNOSAFER",
            "--permit-file-read=*",
            "-dPDFA=2",
            "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
        ]

        # --- Цветовая стратегия ---
        if keep_c:
            # Не трогаем цвет -- оставляем RGB как есть
            cmd += ["-sColorConversionStrategy=LeaveColorUnchanged"]
            report_fh.write(f"[color-strategy] {src.name}: LeaveColorUnchanged\n")
        else:
            # Всё в оттенки серого
            cmd += [
                "-sColorConversionStrategy=Gray",
                "-sProcessColorModel=DeviceGray",
            ]
            report_fh.write(f"[color-strategy] {src.name}: Gray\n")

        cmd += [
            f"-sOutputICCProfile={icc_ps_path}",
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
            f"-dGrayImageDownsampleThreshold={DOWNSAMPLE_THRESHOLD}",

            "-dDownsampleMonoImages=true",
            "-dMonoImageResolution=300",
            "-dMonoImageDownsampleType=/Bicubic",
            f"-dMonoImageDownsampleThreshold={DOWNSAMPLE_THRESHOLD}",

            "-dDownsampleColorImages=true",
            "-dColorImageResolution=300",
            "-dColorImageDownsampleType=/Bicubic",
            f"-dColorImageDownsampleThreshold={DOWNSAMPLE_THRESHOLD}",

            "-sDEVICE=pdfwrite",
            f"-sOutputFile={out_ps_path}",
            tmp_def.name,
            tmp_src.name,
        ]

        report_fh.write(f"[cmd] {subprocess.list2cmdline(cmd)}\n")

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="cp866",
                errors="replace",
                cwd=str(work_dir),
            )
        except Exception as e:
            return (False, f"subprocess exception: {e}")

        output = res.stdout or ""
        report_fh.write(output)
        report_fh.write("\n")

        if "Failed to open the supplied ICCProfile" in output:
            return (False, output + "\n[ICC not readable]")
        if "PDF/A processing aborted" in output:
            return (False, output + "\n[PDF/A aborted]")
        if res.returncode != 0:
            return (False, output + f"\n[rc={res.returncode}]")
        if not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            return (False, output + "\n[empty output]")

        shutil.copyfile(tmp_out, dst)
        return (True, output)

    except Exception as e:
        return (False, f"workflow exception: {e}")
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


# ============================================================
#  Обесцвечивание content streams
# ============================================================
COLOR_OPS = {"rg", "RG", "k", "K"}


def _luma(r: float, g: float, b: float) -> float:
    """ITU-R BT.601."""
    return 0.299 * r + 0.587 * g + 0.114 * b


def _scan_color_operators(pdf_path: Path) -> tuple[int, int]:
    if not HAVE_PIKEPDF:
        return (0, 0)
    total = 0
    color = 0
    try:
        with pikepdf.open(pdf_path) as doc:
            for page in doc.pages:
                try:
                    cs = list(pikepdf.parse_content_stream(page))
                except Exception:
                    continue
                for _ops, op in cs:
                    total += 1
                    if str(op) in COLOR_OPS:
                        color += 1
    except Exception:
        pass
    return (total, color)


def grayscale_content_streams(pdf_path: Path) -> tuple[int, int]:
    if not HAVE_PIKEPDF:
        return (0, 0)

    total = 0
    changed_total = 0
    try:
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as doc:
            for page in doc.pages:
                try:
                    cs = pikepdf.parse_content_stream(page)
                except Exception:
                    continue

                new_cs = []
                changed = 0
                for operands, operator in cs:
                    total += 1
                    op = str(operator)
                    if op in ("rg", "RG") and len(operands) == 3:
                        try:
                            r = float(operands[0])
                            g = float(operands[1])
                            b = float(operands[2])
                            y = _luma(r, g, b)
                            new_op = "g" if op == "rg" else "G"
                            new_cs.append(([y], new_op))
                            changed += 1
                            continue
                        except Exception:
                            pass
                    elif op in ("k", "K") and len(operands) == 4:
                        try:
                            c = float(operands[0])
                            m = float(operands[1])
                            yy = float(operands[2])
                            k = float(operands[3])
                            r = (1 - c) * (1 - k)
                            g = (1 - m) * (1 - k)
                            b = (1 - yy) * (1 - k)
                            y = _luma(r, g, b)
                            new_op = "g" if op == "k" else "G"
                            new_cs.append(([y], new_op))
                            changed += 1
                            continue
                        except Exception:
                            pass
                    new_cs.append((operands, operator))

                if changed:
                    try:
                        new_bytes = pikepdf.unparse_content_stream(new_cs)
                        page.Contents = doc.make_stream(new_bytes)
                        changed_total += changed
                    except Exception:
                        pass

            if changed_total:
                doc.save(pdf_path, linearize=False)
    except Exception:
        return (total, 0)
    return (total, changed_total)


# ============================================================
#  FIX TrueType post/maxp
# ============================================================
def fix_truetype_post_table(data: bytes) -> tuple[bytes, str]:
    if len(data) < 12:
        return (data, "too small")
    try:
        sfnt_version = int.from_bytes(data[0:4], "big")
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

    if maxp_offset is None or post_offset is None:
        return (data, "no maxp/post")
    if maxp_offset + 6 > len(data) or post_offset + 34 > len(data):
        return (data, "out of range")

    num_glyphs = int.from_bytes(data[maxp_offset + 4:maxp_offset + 6], "big")
    post_version = int.from_bytes(data[post_offset:post_offset + 4], "big")

    if post_version != 0x00020000:
        return (data, f"post v{post_version:#x}, skip")

    old_num = int.from_bytes(data[post_offset + 32:post_offset + 34], "big")
    if old_num == num_glyphs:
        return (data, f"ok ({num_glyphs})")

    new_data = bytearray(data)
    new_data[post_offset + 32:post_offset + 34] = num_glyphs.to_bytes(2, "big")
    return (bytes(new_data), f"fixed {old_num} -> {num_glyphs}")


def fix_fonts_in_pdf(pdf) -> tuple[int, int, int]:
    total = cidset_removed = post_fixed = 0
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary):
            continue
        if str(obj.get("/Type", "")) != "/FontDescriptor":
            continue
        if STRIP_CIDSET and "/CIDSet" in obj:
            try:
                del obj["/CIDSet"]
                cidset_removed += 1
            except Exception:
                pass
        if FIX_TRUETYPE_POST and "/FontFile2" in obj:
            total += 1
            try:
                ff = obj["/FontFile2"]
                raw = bytes(ff.read_bytes())
                new_raw, status = fix_truetype_post_table(raw)
                if new_raw is not raw and len(new_raw) == len(raw):
                    ff.write(new_raw)
                    if "/Length1" in ff:
                        ff["/Length1"] = len(new_raw)
                    if status.startswith("fixed"):
                        post_fixed += 1
            except Exception:
                pass
    return (total, cidset_removed, post_fixed)


# ============================================================
#  pikepdf-постобработка
# ============================================================
def pikepdf_postprocess(pdf_path: Path) -> tuple[bool, str]:
    if not HAVE_PIKEPDF:
        return (True, "skipped (pikepdf not installed)")

    tmp_path = pdf_path.with_suffix(".tmp.pdf")
    try:
        with pikepdf.open(pdf_path) as pdf:
            try:
                total_fonts, cid_removed, post_fixed = fix_fonts_in_pdf(pdf)
            except Exception:
                total_fonts = cid_removed = post_fixed = 0

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
#  Полный цикл
# ============================================================
def convert(src: Path, dst: Path, report_fh, ascii_tmp: Path) -> bool:
    filtertext = needs_filtertext(src.name)
    keep_c     = keep_color(src.name)
    tag = ""
    if filtertext:
        tag += " [FILTERTEXT]"
    if keep_c:
        tag += " [KEEP-COLOR]"
    print(f"    -> {dst.name}{tag}")

    ok, msg = gs_convert(src, dst, ascii_tmp, report_fh)
    if not ok:
        report_fh.write(f"PDF/A ERROR: GS conversion failed for {src.name}\n")
        return False

    if keep_c:
        report_fh.write(
            f"[decolor-content] {src.name}: пропущен (KEEP_COLOR_PREFIXES)\n"
        )
    else:
        try:
            total, color = _scan_color_operators(dst)
            if color > 0:
                total2, changed = grayscale_content_streams(dst)
                report_fh.write(
                    f"[decolor-content] {src.name}: "
                    f"ops={total}, color={color}, заменено={changed}\n"
                )
            else:
                report_fh.write(
                    f"[decolor-content] {src.name}: "
                    f"ops={total}, цветных операторов нет\n"
                )
        except Exception as e:
            report_fh.write(f"[decolor-content] {src.name}: ошибка {e}\n")

    ok, msg = pikepdf_postprocess(dst)
    report_fh.write(f"[postprocess] {src.name}: {msg}\n")
    if not ok:
        report_fh.write(f"PDF/A WARNING: postprocess failed: {msg}\n")

    return True


# ============================================================
#  pdfimages
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
    ascii_tmp = preflight()

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
            report_fh.write(f"\n====\n[{i}] Processing: {src.name}\n====\n")
            dst = src.with_name(f"{src.stem}_pdfa.pdf")

            if convert(src, dst, report_fh, ascii_tmp):
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