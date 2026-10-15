# PDF → PDF/A-2b конвейер

Пакетная конвертация PDF в архивный формат **PDF/A-2b** (grayscale, 300 dpi)
через Ghostscript с постобработкой `pikepdf` и последующей валидацией
через **veraPDF**.

Проверено на:
- Ghostscript 10.08.0 (Windows)
- pikepdf 9.x
- veraPDF 1.30 (GreenField)
- Windows 10/11, Python 3.10+

Результат на реальном наборе из 11 файлов: **11/11 PASS, 0 WARNING**.

---

## Содержание

- [Зачем это нужно](#зачем-это-нужно)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Структура проекта](#структура-проекта)
- [Настройки](#настройки)
- [Что делает `compress_to_pdfa.py`](#что-делает-compress_to_pdfapy)
- [Что делает `validate_pdfa.py`](#что-делает-validate_pdfapy)
- [Как читать отчёты](#как-читать-отчёты)
- [Известные проблемы и их решения](#известные-проблемы-и-их-решения)
- [FAQ](#faq)
- [Ограничения](#ограничения)

---

## Зачем это нужно

Формат PDF/A — это стандарт ISO 19005 для долгосрочного архивного хранения
электронных документов. Обычный PDF может «поплыть» через 5–10 лет: не найдётся
шрифт, изменится цветопередача, отвалится встроенный профиль. PDF/A фиксирует:

- все шрифты **встроены** в файл;
- описано **целевое цветовое пространство** (`OutputIntent` + ICC-профиль);
- метаданные XMP явно указывают версию PDF/A;
- запрещены небезопасные элементы (шифрование, внешние ссылки, JavaScript).

Этот проект — **готовый конвейер**, который:

1. Прогоняет каждый исходный PDF через Ghostscript и превращает его в PDF/A-2b;
2. Дополнительно чистит артефакты, которые Ghostscript оставляет (XMP, CIDSet,
   EOL у `stream`/`endstream`, `post`/`maxp` в TrueType);
3. Для особо «больных» файлов применяет растеризацию текста как крайний случай;
4. Валидирует результат через veraPDF и делает сводный отчёт.

---

## Требования

### Обязательно

| Компонент | Мин. версия | Ссылка |
|---|---|---|
| **Python** | 3.10 | https://www.python.org/downloads/ |
| **Ghostscript** | 10.0 | https://www.ghostscript.com/releases/gsdnld.html |
| **veraPDF** | 1.26 | https://verapdf.org/software/ |

### Python-пакеты

```cmd
pip install pikepdf
```

`pikepdf` — единственная внешняя зависимость. Она нужна для:
- вставки XMP PDF/A-схемы;
- удаления `/CIDSet` из дескрипторов шрифтов;
- правки таблиц `post`/`maxp` во встроенных TrueType-шрифтах;
- пересохранения PDF (EOL у `stream`, `spacing` у `obj`/`endobj`).

### Опционально

| Компонент | Зачем | Ссылка |
|---|---|---|
| **Poppler** (`pdfimages.exe`) | для вывода списка изображений в `otchet.txt` | https://github.com/oschwartz10612/poppler-windows/releases |

### ICC-профиль

Нужен файл `srgb.icc` (или `.icm`) — обычный sRGB-профиль.

Если в вашей установке Ghostscript папка `iccprofiles` пуста, возьмите
профиль из стандартной папки Windows:

```
C:\Windows\System32\spool\drivers\color\sRGB Color Space Profile.icm
```

или скачайте официальный от Artifex:

```
https://github.com/saucecontrol/Compact-ICC-Profiles/raw/master/profiles/sRGB-v2-magic.icc
```

Путь к профилю задаётся переменной `SRC_ICC` в `compress_to_pdfa.py`.

---

## Установка

1. **Установите Ghostscript** и запомните путь к `gswin64c.exe`.
   По умолчанию это:
   ```
   C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe
   ```

2. **Установите veraPDF** (просто распакуйте архив). Путь к `verapdf.bat`
   обычно:
   ```
   C:\Program Files\veraPDF\verapdf.bat
   ```

3. **Установите Python-зависимости**:
   ```cmd
   pip install pikepdf
   ```

4. **Скопируйте `compress_to_pdfa.py` и `validate_pdfa.py`** в ту папку, где
   лежат ваши исходные PDF.

5. **Проверьте пути** в начале `compress_to_pdfa.py` и `validate_pdfa.py`:
   ```python
   GS       = Path(r"C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe")
   SRC_ICC  = Path(r"C:\Program Files\gs\gs10.08.0\iccprofiles\srgb.icc")
   ```
   и
   ```python
   VERAPDF = Path(r"C:\Program Files\veraPDF\verapdf.bat")
   ```

---

## Быстрый старт

### Шаг 1. Конвертация

```cmd
cd /d D:\path\to\pdfs
python compress_to_pdfa.py
```

Скрипт:
- создаст `_icc\srgb.icc` (локальную копию профиля без пробелов в пути);
- сгенерирует `PDFA_def.ps` (шаблон OutputIntent для Ghostscript);
- обработает все `*.pdf` в текущей папке;
- положит результаты рядом с исходниками: `<имя>_pdfa.pdf`;
- напишет лог в `otchet.txt`.

**Готовые файлы `*_pdfa.pdf` при повторном запуске пропускаются.**

### Шаг 2. Валидация

```cmd
python validate_pdfa.py
```

Скрипт:
- найдёт все `*_pdfa.pdf`;
- прогонит каждый через veraPDF с `--flavour 2b`;
- положит HTML-отчёты рядом: `<имя>_pdfa.html`;
- напишет сводку в `otchet_pdfa.txt`.

### Шаг 3. Просмотр результатов

Откройте `otchet_pdfa.txt` — там таблица «PASS / FAIL / ERROR». HTML-отчёты
открываются в браузере, там детально видно все проверки.

---

## Структура проекта

```
my_pdfs/
├── compress_to_pdfa.py         ← конвертация
├── validate_pdfa.py            ← валидация
│
├── PDFA_def.ps                 ← генерируется автоматически
├── _icc/                       ← генерируется автоматически
│   └── srgb.icc
│
├── otchet.txt                  ← лог конвертации
├── otchet_pdfa.txt             ← сводка валидации
│
├── input1.pdf
├── input1_pdfa.pdf             ← результат
├── input1_pdfa.html            ← отчёт veraPDF
├── input2.pdf
├── input2_pdfa.pdf
├── input2_pdfa.html
└── ...
```

---

## Настройки

Все параметры собраны в шапке каждого скрипта.

### `compress_to_pdfa.py`

```python
GS        = Path(r"C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe")
SRC_ICC   = Path(r"C:\Program Files\gs\gs10.08.0\iccprofiles\srgb.icc")
PDFIMAGES = Path(r"..\pdfimages")          # опционально
REPORT    = Path("otchet.txt")

# Какие файлы НЕ трогать (уже сконвертированные)
SUFFIX_SKIP = "_pdfa"

# Файлы, для которых применить растеризацию текста (см. раздел
# "Проблема .notdef" ниже)
FILTERTEXT_PREFIXES = ("TextPart_",)
FILTERTEXT_DPI      = 300

# Постобработка pikepdf
STRIP_CIDSET      = True   # удалять /CIDSet из FontDescriptor
FIX_TRUETYPE_POST = True   # править numberOfGlyphs в post-таблице
RESUBSET_FONTS    = True   # просить Ghostscript пересобрать шрифты
```

### `validate_pdfa.py`

```python
VERAPDF  = Path(r"C:\Program Files\veraPDF\verapdf.bat")
FLAVOUR  = "2b"                # профиль PDF/A (1a/1b/2a/2b/2u/3a/3b/3u)
REPORT   = Path("otchet_pdfa.txt")
SUFFIX   = "_pdfa.pdf"         # что искать
```

---

## Что делает `compress_to_pdfa.py`

Скрипт состоит из четырёх логических блоков.

### 1. Подготовка ICC и `PDFA_def.ps`

- Копирует `SRC_ICC` в `./_icc/srgb.icc` — **без пробелов в пути**, потому
  что Ghostscript 10.x на Windows спотыкается о пробелы в путях для
  `--permit-file-read`.
- Генерирует `PDFA_def.ps` — PostScript-файл, который описывает
  `OutputIntent` для PDF/A. Формат — канонический шаблон Artifex с
  `icc_PDFA` объявленным как `/type /stream` (это важно, `dict` не работает).

### 2. Вызов Ghostscript

Для каждого PDF:

```
gswin64c -dNOSAFER
  --permit-file-read=... (страховка)
  -dPDFA=2 -dBATCH -dNOPAUSE -dNOOUTERSAVE
  -sColorConversionStrategy=Gray
  -sProcessColorModel=DeviceGray
  -sOutputICCProfile=srgb.icc
  -dOverrideICC
  -dPDFACompatibilityPolicy=1
  -dPreserveAnnots=false
  -dEmbedAllFonts=true -dSubsetFonts=true -dCompressFonts=true
  -dCompatibilityLevel=1.7
  [-dFILTERTEXT -r300]                  # только для FILTERTEXT_PREFIXES
  -dDownsampleGrayImages=true -dGrayImageResolution=300
  -dDownsampleMonoImages=true  -dMonoImageResolution=300
  -sDEVICE=pdfwrite -sOutputFile=<out>
  PDFA_def.ps <input>
```

Ключевые параметры:

| Параметр | Зачем |
|---|---|
| `-dNOSAFER` | отключает sandbox, чтобы Ghostscript мог открыть ICC-профиль |
| `-dPDFA=2` | включает режим PDF/A-2 (не PDF/A-1!) |
| `-sColorConversionStrategy=Gray` | переводит всё в градации серого |
| `-sOutputICCProfile` | явно задаёт профиль для конвертации |
| `-dOverrideICC` | заставляет использовать именно этот профиль |
| `-dPDFACompatibilityPolicy=1` | при невозможности PDF/A — пишет обычный PDF (policy 3 — падает) |
| `-dPreserveAnnots=false` | удаляет аннотации — они приносят DeviceRGB и валят валидацию |
| `-dEmbedAllFonts -dSubsetFonts` | пересобирает шрифты, лечит мелкие дефекты |
| `-dFILTERTEXT` | удаляет текстовый слой, растеризует текст (крайняя мера) |

### 3. Постобработка pikepdf

Каждый `<файл>_pdfa.pdf` проходит через `pikepdf`:

| Действие | Что лечит |
|---|---|
| Вставка XMP PDF/A-2b identification | ошибка `6.6.4-1`: нет PDF/A-схемы в метаданных |
| Удаление `/CIDSet` из FontDescriptor | ошибка `6.2.11.4.2-2`: CIDSet не покрывает все глифы |
| Правка `post.numberOfGlyphs = maxp.numGlyphs` | WARNING: несоответствие таблиц `post`/`maxp` |
| Пересохранение файла | ошибки `6.1.7.1-2` (EOL у `stream`) и `6.1.9-1` (spacing у `obj`/`endobj`) |

В лог пишется строка вида:
```
[postprocess] имя.pdf: ok (FontFile2=3, CIDSet removed=2, post fixed=1)
```

- `FontFile2` — сколько TrueType-шрифтов найдено;
- `CIDSet removed` — сколько дескрипторов очищено;
- `post fixed` — сколько таблиц `post` исправлено.

### 4. Отчёт `otchet.txt`

Содержит:
- полный stdout Ghostscript по каждому файлу;
- строку `[postprocess]` по каждому файлу;
- список изображений (если найден `pdfimages`);
- итоговое `Done. Total: N, OK: M, errors: K.`.

---

## Что делает `validate_pdfa.py`

Для каждого `*_pdfa.pdf`:

1. Запускает veraPDF:
   ```
   verapdf.bat --flavour 2b --format html <файл>
   ```
2. Кладёт HTML в `<файл>.html`.
3. По коду возврата определяет статус:
   - `0` → PASS
   - `1` → FAIL (файл не соответствует PDF/A)
   - `>= 2` → ERROR (инструмент не смог проверить)
4. Пишет в сводный `otchet_pdfa.txt`.

Возможные значения `FLAVOUR`:

| Значение | Профиль |
|---|---|
| `1a`, `1b` | PDF/A-1 |
| `2a`, `2b`, `2u` | PDF/A-2 |
| `3a`, `3b`, `3u` | PDF/A-3 |
| `0` | автоопределение по XMP |

Для конвейера, который создаёт PDF/A-2b, **правильное значение — `2b`**.

---

## Как читать отчёты

### `otchet.txt` (лог конвертации)

Хорошо:
```
[postprocess] file.pdf: ok (FontFile2=3, CIDSet removed=0, post fixed=0)
```

Плохо:
```
PDF/A ERROR: file.pdf (rc=1)
PDF/A WARNING: ICCProfile не прочитан
PDF/A WARNING: GS отменил PDF/A
```

### `otchet_pdfa.txt` (сводка валидации)

```
============================================================
 Отчёт о проверке PDF/A (veraPDF, PDF/A-2b)
 Дата: 2026-10-16 01:32:49
============================================================

------------------------------------------------------------
Файл: document_pdfa.pdf
Результат: PASS
HTML-отчёт: document_pdfa.html

------------------------------------------------------------
Файл: bad_pdfa.pdf
Результат: FAIL
HTML-отчёт: bad_pdfa.html
[veraPDF stderr]
...

Всего проверено: 11
PASS:  11
FAIL:  0
ERROR: 0
```

### HTML-отчёт veraPDF

Откройте в браузере. Внутри:

- **Validation Profile** — должен быть `PDF/A-2B validation profile`;
- **Compliance** — `Passed` или `Failed`;
- **Failed Checks** — количество нарушенных правил (0 = всё хорошо);
- внизу — список конкретных нарушений с указанием объекта в PDF.

---

## Известные проблемы и их решения

Этот раздел — концентрат того, что вылечено в проекте. Если что-то пошло
не так, скорее всего ответ здесь.

### 1. `Failed to open the supplied ICCProfile for reading`

**Симптом.** Ghostscript пишет:
```
Failed to open the supplied ICCProfile for reading.
PDF/A processing aborted, output may not be a PDF/A file.
```

**Причина.** Sandbox Ghostscript 10.x (`-dSAFER` по умолчанию) не даёт
PostScript-программе открыть ICC-профиль. Флаг `--permit-file-read` часто не
срабатывает на путях с пробелами (`Program Files`).

**Решение.** В скрипте:
- копируется ICC в `./_icc/srgb.icc` (без пробелов в пути);
- добавляется `-dNOSAFER`;
- параллельно передаётся `--permit-file-read` с четырьмя вариантами пути.

### 2. `Error: /typecheck in --pdfmark--` про `icc_PDFA`

**Симптом.** Ghostscript падает на строке `DestOutputProfile ... PUT`.

**Причина.** В `PDFA_def.ps` объект `icc_PDFA` объявлен как `/type /dict`.
Нужен `/type /stream`.

**Решение.** Используется канонический шаблон Artifex: `icc_PDFA` — поток,
в который вливаются байты ICC через `ICCProfile (r) file /PUT pdfmark`.

### 3. `PDF/A processing aborted`

**Симптом.** Ghostscript отказывается делать PDF/A.

**Причина.** Какая-то из проверок GS не прошла (обычно — из-за `-dPDFACompatibilityPolicy=3`
или из-за неподдерживаемого шрифта).

**Решение.** `-dPDFACompatibilityPolicy=1` — при невозможности PDF/A
Ghostscript всё равно пишет обычный PDF, а `pikepdf` доводит его до канона.

### 4. veraPDF: `The document metadata stream doesn't contain PDF/A Identification Schema`

**Симптом.** `6.6.4-1` в отчёте veraPDF.

**Причина.** Ghostscript не всегда пишет XMP-схему PDF/A.

**Решение.** `pikepdf.open_metadata().load(XMP_PDFA_ID)` в постобработке.

### 5. veraPDF: `Xref streams shall not be used`

**Симптом.** `6.1.4-3` в отчёте.

**Причина.** Файл валидируется против **PDF/A-1B**, а сделан как **PDF/A-2B**.

**Решение.** В `validate_pdfa.py` явно передан `--flavour 2b`.

### 6. veraPDF: `Extra spacings or missing EOL characters`

**Симптом.** `6.1.7.1-2` (у `stream`) или `6.1.9-1` (у `obj`/`endobj`).

**Причина.** Особенность записи PDF у Ghostscript 10.x.

**Решение.** `pikepdf` пересохраняет файл, выравнивая все EOL и spacing по
канону.

### 7. veraPDF: `A CIDSet entry in the Font descriptor does not correctly identify all glyphs`

**Симптом.** `6.2.11.4.2-2`.

**Причина.** В исходном PDF у встроенных шрифтов неправильный `/CIDSet`.

**Решение.** Постобработка удаляет ключ `/CIDSet` из всех `FontDescriptor`.
Если CIDSet нет, правило не применяется.

### 8. veraPDF: `reference to the .notdef glyph`

**Симптом.** `6.2.11.8-1`, встречается у файлов из Word/LibreOffice.

**Причина.** В исходном PDF есть текстовые операторы, ссылающиеся на
«пустой» глиф `.notdef`. PDF/A-2 это запрещает.

**Решение.** Для конкретных файлов применяется `-dFILTERTEXT` — текст
растеризуется, текстовый слой удаляется вместе с `.notdef`-ссылками.

Управляется через переменную `FILTERTEXT_PREFIXES` в `compress_to_pdfa.py`.
По умолчанию растеризуются файлы, начинающиеся с `TextPart_`.

**Цена:** текст в таких файлах перестаёт быть выделяемым и искомым. Для
архива это приемлемо, но не идеально.

### 9. WARNING veraPDF: `post` table does not match `maxp`

**Симптом.** В `otchet_pdfa.txt` строка `[veraPDF stderr] WARNING: ...`.
На результат валидации не влияет.

**Причина.** Во встроенном TrueType-шрифте `post.numberOfGlyphs` не совпадает
с `maxp.numGlyphs`.

**Решение.** Постобработка `fix_truetype_post_table()` читает `maxp` и
переписывает `numberOfGlyphs` в `post`. См. `otchet.txt` — там будет
`post fixed=N`.

### 10. Кириллица в именах файлов превращается в `–Λ–Α–Ι–Μ`

**Симптом.** bat-скрипт с `chcp 1251` пишет в отчёт нечитаемые символы.

**Причина.** veraPDF выводит UTF-8, а bat-консоль — cp1251.

**Решение.** Python-скрипт `validate_pdfa.py` читает stdout/stderr как UTF-8
и пишет отчёт в UTF-8. Проблема исчезает.

---

## FAQ

**Можно ли использовать это для PDF/A-3 или PDF/A-1?**

Да. В `compress_to_pdfa.py` поменяйте `-dPDFA=2` на `-dPDFA=3` или `-dPDFA=1`.
В `validate_pdfa.py` поменяйте `FLAVOUR = "2b"` на `"3b"` или `"1b"` соответственно.
Правки XMP-схемы в `XMP_PDFA_ID` тоже нужно синхронизировать.

**Что делать, если нужно сохранить цвет (не grayscale)?**

Уберите из `gs_convert`:
```python
"-sColorConversionStrategy=Gray",
"-sProcessColorModel=DeviceGray",
```
и используйте `srgb.icc` без конвертации в `N=3` (RGB).

**Как обрабатывать подпапки?**

Замените в `main()`:
```python
sources = sorted(WORK_DIR.glob("*.pdf"))
```
на
```python
sources = sorted(WORK_DIR.rglob("*.pdf"))
```

**Как распараллелить?**

Оборачивайте вызов `convert()` в `multiprocessing.Pool`. Ghostscript
и pikepdf потокобезопасны в режиме отдельных процессов, но не в потоках.

**Где взять `srgb.icc`?**

См. раздел [ICC-профиль](#icc-профиль).

**Почему для `TextPart_...` `FontFile2=0`?**

Потому что применён `-dFILTERTEXT` — текст растеризован, встроенные шрифты
отсутствуют, чистить нечего. Это нормально.

**В `otchet.txt` написано `post fixed=0` для всех файлов. Это плохо?**

Нет. Это значит, что таблицы `post`/`maxp` уже были согласованы, править
нечего. WARNING появлялся только у двух файлов, и для них `post fixed=1`.

---

## Ограничения

- **Windows-only** в текущей конфигурации (пути `C:\...`, `gswin64c.exe`,
  `verapdf.bat`). На Linux/macOS скрипт запустится после правки путей
  (`GS = "/usr/bin/gs"`, `VERAPDF = "/opt/verapdf/verapdf"`).
- **Не поддерживает multipage TIFF** на входе — только PDF. Для TIFF
  сначала прогнать через `img2pdf` или Ghostscript.
- **Не сохраняет цифровые подписи** исходных PDF — Ghostscript их снимает.
  Для подписанных PDF нужен другой инструмент (например, `qpdf` +
  постобработка).
- **`-dFILTERTEXT` необратим** — после него текст в файле исчезает.
  Применяйте только к тем файлам, которые без этого не проходят валидацию.
- **При смене версии Ghostscript** синтаксис `--permit-file-read` может
  поменяться. Проверяйте лог `otchet.txt` на строку `Failed to open the
  supplied ICCProfile`.

---

## Лицензия

Код проекта можно использовать по вашему усмотрению. Он зависит от:

- **Ghostscript** — AGPLv3 (https://www.ghostscript.com/licensing.html);
- **veraPDF** — GPLv3+ / MPLv2+ (https://verapdf.org/);
- **pikepdf** — MPLv2 (https://github.com/pikepdf/pikepdf).

Учитывайте лицензии этих компонентов при распространении результатов.

---

## Ссылки

- ISO 19005-2:2011 (PDF/A-2) — https://www.iso.org/standard/50655.html
- veraPDF validation profiles — https://github.com/veraPDF/veraPDF-validation-profiles/wiki
- Ghostscript PDF/A how-to — https://ghostscript.readthedocs.io/en/latest/VectorDevices.html#creating-pdf-a-files
- pikepdf docs — https://pikepdf.readthedocs.io/
- PDF/A in a Nutshell (PDF Association) — https://www.pdfa.org/resource/pdfa-in-a-nutshell-2/
