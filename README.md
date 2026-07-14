# CurseForge Modpack Downloader 🚀

[Русский перевод ниже / Russian translation below](#русский)

A fast, lightweight, and modern utility to download and install Minecraft modpacks from CurseForge ZIP archives. It parses the modpack's `manifest.json`, extracts overrides (configs, scripts, etc.), and downloads all mod files concurrently using the CurseForge API with fallback CDN resolution.

Features a **Command Line Interface (CLI)** and a sleek **Graphical User Interface (GUI)**.

---

## Features

- **Modern Dark GUI**: Beautifully styled interface built with PySide6.
- **Drag & Drop**: Drag a CurseForge modpack ZIP file directly into the application window.
- **Multi-threaded Downloads**: Downloads mods in parallel (configurable thread count, default 5) for maximum speed.
- **API and CDN Fallback**: Downloads directly using official API mappings or constructs CDN fallback links if direct download is disabled by mod authors.
- **Automatic Output Paths**: Resolves the output instance path next to your modpack archive.
- **Real-time Console Output**: Live scrolling logs of the extraction and download process inside the app.

---

## Installation & Setup

### Prerequisites
- Python 3.10 or higher.

### Step-by-Step Setup
1. Clone or download this folder.
2. Initialize virtual environment:
   ```bash
   python3 -m venv .venv
   ```
3. Activate virtual environment and install dependencies:
   ```bash
   # On macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt

   # On Windows:
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## How to Run

### Graphical User Interface (GUI)
Simply run the script without any arguments:
```bash
python cf_download.py
```
*Tip: Drag and drop a `.zip` file from your desktop/folders directly onto the window!*

### Command Line Interface (CLI)
Run the script with the path to a local ZIP file or a direct CurseForge download URL:
```bash
python cf_download.py <path_to_zip_or_url> [-o output_directory] [-j parallel_threads]
```

**Examples:**
```bash
# Run on local ZIP using default settings (5 threads, outputs to parent directory)
python cf_download.py "../Cave Horror Project 1-v3.4.1.zip"

# Run with custom output folder and 8 threads
python cf_download.py "../Cave Horror Project 1-v3.4.1.zip" -o "../MyInstance" -j 8
```

---

<a name="русский"></a>
# CurseForge Modpack Downloader (На русском) 🇷🇺

Быстрая, легкая и современная утилита для скачивания и установки сборок Minecraft из ZIP-архивов CurseForge. Скрипт анализирует файл `manifest.json`, распаковывает переопределения (`overrides`, такие как конфиги, скрипты и т.д.) и параллельно скачивает все файлы модов с помощью API CurseForge и резервного поиска на CDN.

Снабжен как **интерфейсом командной строки (CLI)**, так и красивым **графическим интерфейсом (GUI)**.

---

## Особенности

- **Современный GUI**: Стильная темная тема на базе библиотеки PySide6.
- **Drag & Drop (Перетаскивание)**: Перетащите ZIP-архив сборки напрямую в окно программы.
- **Многопоточное скачивание**: Скачивание файлов модов в несколько потоков (настраиваемое количество, по умолчанию 5) для максимальной скорости.
- **Умное скачивание**: Автоматическое переключение на CDN-ссылки в обход ограничений сторонних загрузок.
- **Автоматический путь**: Умный подбор конечной папки для установки рядом с вашим архивом.
- **Логи в реальном времени**: Встроенный консольный лог для отслеживания хода скачивания.

---

## Установка и запуск

### Требования
- Python 3.10 или выше.

### Инструкция по установке:
1. Скачайте или скопируйте эту папку.
2. Создайте виртуальное окружение:
   ```bash
   python3 -m venv .venv
   ```
3. Активируйте виртуальное окружение и установите зависимости:
   ```bash
   # На macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt

   # На Windows (CMD):
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## Использование

### Графический интерфейс (GUI)
Просто запустите скрипт без аргументов:
```bash
python cf_download.py
```
*Совет: Перетащите файл `.zip` прямо из проводника/файлового менеджера в окно программы.*

### Командная строка (CLI)
Запустите скрипт, передав путь к локальному ZIP-файлу или прямой ссылке на CurseForge:
```bash
python cf_download.py <путь_к_zip_или_url> [-o конечная_папка] [-j потоков]
```

**Примеры:**
```bash
# Запуск с локальным ZIP (5 потоков, папка с результатом создается в родительской директории)
python cf_download.py "../Cave Horror Project 1-v3.4.1.zip"

# Запуск с указанием конкретной папки и 8 потоками скачивания
python cf_download.py "../Cave Horror Project 1-v3.4.1.zip" -o "../MyInstance" -j 8
```
