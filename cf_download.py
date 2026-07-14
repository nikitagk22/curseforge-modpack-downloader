#!/usr/bin/env python3
import os
import sys
import json
import zipfile
import argparse
import shutil
import re
from pathlib import Path
from urllib.parse import urlparse
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to import PySide6 for GUI, but make it optional
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QFileDialog, QProgressBar,
        QTextEdit, QSpinBox, QGroupBox, QMessageBox
    )
    from PySide6.QtCore import QThread, Signal, Slot, Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False

DEFAULT_API_KEY = "$2a$10$bL4bIL5pUWqfcO7KQtnMReakwtfHbNKh6v1uTpKlzhwoueEJQnPnm"
API_BASE_URL = "https://api.curseforge.com/v1"

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "_")
    return re.sub(r'_+', '_', name).strip('_')

def download_file(url, target_path, headers=None, session=None):
    req = session if session else requests
    response = req.get(url, headers=headers, stream=True)
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code} for URL: {url}")
    
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(target_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

def download_modpack_zip(url, dest_path, log_callback=None):
    if log_callback:
        log_callback(f"Downloading modpack ZIP from URL: {url}...")
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise Exception(f"Failed to download ZIP. HTTP status: {response.status_code}")
        
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024 * 1024  # 1MB
    
    with open(dest_path, 'wb') as f:
        downloaded = 0
        for data in response.iter_content(block_size):
            f.write(data)
            downloaded += len(data)
            if log_callback and total_size > 0:
                percent = int(100 * downloaded / total_size)
                # Avoid flooding logs, just basic print occasionally or format nicely
                if percent % 10 == 0 or downloaded == total_size:
                    log_callback(f"  Downloaded ZIP: {downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB ({percent}%)")

def fetch_files_metadata(file_ids, api_key, log_callback=None):
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    url = f"{API_BASE_URL}/mods/files"
    metadata = {}
    
    chunk_size = 100
    file_ids_list = list(file_ids)
    
    if log_callback:
        log_callback(f"Fetching metadata for {len(file_ids_list)} files from CurseForge API...")
    
    for i in range(0, len(file_ids_list), chunk_size):
        chunk = file_ids_list[i:i+chunk_size]
        payload = {"fileIds": chunk}
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json().get("data", [])
                for file_obj in data:
                    file_id = file_obj.get("id")
                    file_name = file_obj.get("fileName")
                    download_url = file_obj.get("downloadUrl")
                    metadata[file_id] = {
                        "fileName": file_name,
                        "downloadUrl": download_url
                    }
            else:
                msg = f"Warning: Failed to fetch metadata chunk. HTTP {response.status_code}"
                if log_callback:
                    log_callback(msg)
        except Exception as e:
            msg = f"Warning: Exception occurred while fetching metadata: {e}"
            if log_callback:
                log_callback(msg)
            
    return metadata

def run_installation(modpack_source, output_dir_str, threads, api_key, log_callback, progress_callback):
    """Core installation logic that can be run from CLI or GUI thread."""
    temp_zip = None
    
    # 1. Handle source ZIP (local or URL)
    if urlparse(modpack_source).scheme in ('http', 'https'):
        temp_zip = Path("temp_modpack.zip")
        download_modpack_zip(modpack_source, temp_zip, log_callback)
        zip_path = temp_zip
    else:
        zip_path = Path(modpack_source)
        if not zip_path.is_file():
            raise FileNotFoundError(f"File '{zip_path}' does not exist.")
            
    # 2. Open and inspect ZIP
    log_callback(f"Reading modpack archive: {zip_path.name}")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if "manifest.json" not in zip_ref.namelist():
                raise ValueError("The zip file does not contain manifest.json. Is this a CurseForge modpack ZIP?")
                
            with zip_ref.open("manifest.json") as f:
                manifest = json.load(f)
    except zipfile.BadZipFile:
        raise ValueError("The specified file is not a valid zip archive.")

    # 3. Read metadata from manifest
    modpack_name = manifest.get("name", "Unknown Modpack")
    modpack_version = manifest.get("version", "1.0")
    mc_version = manifest.get("minecraft", {}).get("version", "Unknown")
    mod_loaders = manifest.get("minecraft", {}).get("modLoaders", [])
    primary_loader = next((loader.get("id") for loader in mod_loaders if loader.get("primary")), "None")
    
    log_callback(f"\nModpack Information:")
    log_callback(f"  Name:             {modpack_name}")
    log_callback(f"  Version:          {modpack_version}")
    log_callback(f"  Minecraft:        {mc_version}")
    log_callback(f"  Mod Loader:       {primary_loader}")
    log_callback(f"  Number of Mods:   {len(manifest.get('files', []))}\n")
    
    # 4. Resolve Output Directory
    if output_dir_str:
        output_dir = Path(output_dir_str).resolve()
    else:
        sanitized_name = sanitize_filename(modpack_name)
        output_dir = Path(zip_path.parent) / sanitized_name
        
    log_callback(f"Installing modpack to: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 5. Extract Overrides
    log_callback("Extracting overrides (configs, scripts, etc.)...")
    overrides_count = 0
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.startswith("overrides/"):
                relative_path = file_info.filename[len("overrides/"):]
                if not relative_path:
                    continue
                    
                target_file_path = output_dir / relative_path
                
                if file_info.is_dir():
                    target_file_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_file_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(file_info) as source, open(target_file_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    overrides_count += 1
                    
    log_callback(f"Extracted {overrides_count} override files.\n")
    
    # 6. Fetch Metadata for Mod Files
    files_to_download = manifest.get("files", [])
    if not files_to_download:
        log_callback("No mod files specified in manifest.json. Installation complete.")
        if temp_zip and temp_zip.exists():
            temp_zip.unlink()
        return output_dir, mc_version, primary_loader, 0, 0
        
    file_ids = [file_info["fileID"] for file_info in files_to_download]
    metadata = fetch_files_metadata(file_ids, api_key, log_callback)
    
    # 7. Prepare Download Queue
    download_queue = []
    mods_dir = output_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    
    missing_metadata = 0
    for file_info in files_to_download:
        file_id = file_info["fileID"]
        project_id = file_info["projectID"]
        
        file_meta = metadata.get(file_id)
        if not file_meta:
            log_callback(f"Warning: Could not get metadata for File ID {file_id}. Skipping.")
            missing_metadata += 1
            continue
            
        file_name = file_meta["fileName"]
        download_url = file_meta["downloadUrl"]
        
        if not download_url:
            high_id = file_id // 1000
            low_id = file_id % 1000
            download_url = f"https://edge.forgecdn.net/files/{high_id}/{low_id}/{file_name}"
            
        download_queue.append({
            "url": download_url,
            "path": mods_dir / file_name,
            "name": file_name
        })
        
    if missing_metadata > 0:
        log_callback(f"Warning: {missing_metadata} mods will be skipped due to missing API metadata.\n")
        
    # 8. Download Mods using ThreadPoolExecutor
    log_callback(f"Downloading mods using {threads} parallel threads...")
    
    session = requests.Session()
    session.headers.update({"x-api-key": api_key})
    
    success_count = 0
    failed_downloads = []
    
    progress_callback(0, len(download_queue))
    
    with ThreadPoolExecutor(max_workers=threads) as executor:
        future_to_mod = {
            executor.submit(
                download_file, 
                mod["url"], 
                mod["path"], 
                session=session
            ): mod for mod in download_queue
        }
        
        for future in as_completed(future_to_mod):
            mod = future_to_mod[future]
            try:
                future.result()
                success_count += 1
            except Exception as e:
                log_callback(f"Failed to download {mod['name']}: {e}")
                failed_downloads.append((mod['name'], mod['url']))
            progress_callback(success_count, len(download_queue))
                
    # Clean up temp ZIP if downloaded
    if temp_zip and temp_zip.exists():
        temp_zip.unlink()
        
    return output_dir, mc_version, primary_loader, success_count, len(download_queue)

# ==================== GUI IMPLEMENTATION ====================

class InstallerThread(QThread):
    progress_sig = Signal(int, int)
    log_sig = Signal(str)
    finished_sig = Signal(bool, str)

    def __init__(self, modpack, output_dir, threads, api_key):
        super().__init__()
        self.modpack = modpack
        self.output_dir = output_dir
        self.threads = threads
        self.api_key = api_key

    def run(self):
        try:
            def log_cb(msg):
                self.log_sig.emit(msg)
                
            def progress_cb(current, total):
                self.progress_sig.emit(current, total)
                
            out_dir, mc_ver, loader, success, total = run_installation(
                self.modpack, self.output_dir, self.threads, self.api_key, log_cb, progress_cb
            )
            
            summary = (
                f"\nInstallation Completed Summary:\n"
                f"  Target Instance:    {out_dir}\n"
                f"  Minecraft Version:  {mc_ver}\n"
                f"  Mod Loader:         {loader}\n"
                f"  Mods Downloaded:    {success} / {total}\n"
                f"Done! You can import this folder into your launcher."
            )
            self.log_sig.emit(summary)
            self.finished_sig.emit(True, "Installation complete!")
        except Exception as e:
            self.log_sig.emit(f"\nERROR during installation: {e}")
            self.finished_sig.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CurseForge Modpack Downloader")
        self.resize(650, 600)
        self.setAcceptDrops(True)
        
        # Stylesheet for premium aesthetics
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 10px;
                color: #cdd6f4;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #7f849c;
            }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 8px;
                margin-top: 15px;
                padding: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #f5c2e7;
            }
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 6px;
                text-align: center;
                background-color: #313244;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #a6e3a1;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #11111b;
                border: 1px solid #45475a;
                border-radius: 6px;
                font-family: Consolas, Monaco, "Courier New", monospace;
                font-size: 12px;
                color: #a6e3a1;
                padding: 5px;
            }
            QSpinBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px;
            }
        """)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title / Description
        title_label = QLabel("<h2>CurseForge Modpack Downloader</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        desc_label = QLabel("Drag & Drop a CurseForge modpack ZIP file here, or enter its details manually.")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("color: #a6adc8; margin-bottom: 10px;")
        
        main_layout.addWidget(title_label)
        main_layout.addWidget(desc_label)

        # File selection group
        file_group = QGroupBox("Modpack Source")
        file_layout = QVBoxLayout(file_group)
        
        input_label = QLabel("Select ZIP File or enter direct CurseForge ZIP download URL:")
        file_layout.addWidget(input_label)
        
        input_row = QHBoxLayout()
        self.modpack_input = QLineEdit()
        self.modpack_input.setPlaceholderText("Drag file here, browse, or paste URL...")
        self.modpack_input.textChanged.connect(self.auto_guess_output)
        
        browse_file_btn = QPushButton("Browse File...")
        browse_file_btn.clicked.connect(self.browse_file)
        
        input_row.addWidget(self.modpack_input)
        input_row.addWidget(browse_file_btn)
        file_layout.addLayout(input_row)
        main_layout.addWidget(file_group)

        # Output folder group
        output_group = QGroupBox("Destination")
        output_layout = QVBoxLayout(output_group)
        
        output_label = QLabel("Install Location:")
        output_layout.addWidget(output_label)
        
        output_row = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Defaults to parent directory/Modpack_Name")
        
        browse_folder_btn = QPushButton("Browse Folder...")
        browse_folder_btn.clicked.connect(self.browse_folder)
        
        output_row.addWidget(self.output_input)
        output_row.addWidget(browse_folder_btn)
        output_layout.addLayout(output_row)
        main_layout.addWidget(output_group)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QHBoxLayout(settings_group)
        
        threads_label = QLabel("Download Threads:")
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 20)
        self.threads_spin.setValue(5)
        
        settings_layout.addWidget(threads_label)
        settings_layout.addWidget(self.threads_spin)
        settings_layout.addStretch()
        
        main_layout.addWidget(settings_group)

        # Download / Action panel
        action_layout = QHBoxLayout()
        self.download_btn = QPushButton("Download & Install")
        self.download_btn.setFixedHeight(40)
        self.download_btn.setStyleSheet("font-size: 14px;")
        self.download_btn.clicked.connect(self.start_installation)
        
        action_layout.addWidget(self.download_btn)
        main_layout.addLayout(action_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m mods (%p%)")
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Log box
        log_label = QLabel("Installation Log:")
        main_layout.addWidget(log_label)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output)

        self.thread = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.endswith('.zip'):
                self.modpack_input.setText(file_path)
                break

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Modpack ZIP", "", "ZIP Archives (*.zip)"
        )
        if file_path:
            self.modpack_input.setText(file_path)

    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Destination Directory")
        if folder_path:
            self.output_input.setText(folder_path)

    def auto_guess_output(self, text):
        # If it's a local zip file, auto guess the output directory in its parent folder
        if text and text.endswith('.zip') and os.path.exists(text):
            zip_path = Path(text)
            # Remove extension and sanitize
            guessed_name = sanitize_filename(zip_path.stem)
            self.output_input.setText(str(zip_path.parent / guessed_name))

    def log(self, text):
        self.log_output.append(text)
        # Scroll to bottom
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def start_installation(self):
        modpack = self.modpack_input.text().strip()
        output_dir = self.output_input.text().strip()
        threads = self.threads_spin.value()
        
        if not modpack:
            QMessageBox.critical(self, "Error", "Please select a modpack ZIP file or enter a valid URL.")
            return

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        
        self.download_btn.setEnabled(False)
        self.modpack_input.setEnabled(False)
        self.output_input.setEnabled(False)
        self.threads_spin.setEnabled(False)

        self.log("Starting installer thread...")
        self.thread = InstallerThread(modpack, output_dir, threads, DEFAULT_API_KEY)
        self.thread.log_sig.connect(self.log)
        self.thread.progress_sig.connect(self.update_progress)
        self.thread.finished_sig.connect(self.installation_finished)
        self.thread.start()

    def installation_finished(self, success, message):
        self.download_btn.setEnabled(True)
        self.modpack_input.setEnabled(True)
        self.output_input.setEnabled(True)
        self.threads_spin.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "Success", "Minecraft Modpack installed successfully!")
        else:
            QMessageBox.critical(self, "Error", f"Installation failed:\n{message}")

# ==================== CLI / MAIN RUNNER ====================

def main():
    # If no arguments are provided, launch the GUI if PySide6 is installed
    if len(sys.argv) == 1:
        if PYSIDE_AVAILABLE:
            app = QApplication(sys.argv)
            window = MainWindow()
            window.show()
            sys.exit(app.exec())
        else:
            print("PySide6 is not installed. To run GUI, install it with:")
            print("  pip install PySide6")
            print("Alternatively, use the command line interface:")
            print("  python cf_download.py <modpack_zip_or_url> [-o output_dir] [-j threads]")
            sys.exit(1)

    # CLI flow
    parser = argparse.ArgumentParser(description="Download and install Minecraft modpacks from CurseForge ZIPs.")
    parser.add_argument("modpack", help="Path to local modpack ZIP file or direct download URL.")
    parser.add_argument("-o", "--output", help="Output directory path (defaults to a directory under parent folder).")
    parser.add_argument("-j", "--threads", type=int, default=5, help="Number of parallel download threads (default: 5).")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="CurseForge API Key.")
    
    args = parser.parse_args()
    
    try:
        # CLI print-based logging
        def cli_log(msg):
            print(msg)
            
        pbar = None
        def cli_progress(current, total):
            nonlocal pbar
            if pbar is None:
                pbar = tqdm(total=total, desc="Downloading Mods", unit="mod")
            pbar.n = current
            pbar.refresh()
            if current == total:
                pbar.close()

        out_dir, mc_ver, loader, success, total = run_installation(
            args.modpack, args.output, args.threads, args.api_key, cli_log, cli_progress
        )
        
        print("\n" + "="*40)
        print("Installation Completed Summary:")
        print(f"  Target Instance:    {out_dir}")
        print(f"  Minecraft Version:  {mc_ver}")
        print(f"  Mod Loader:         {loader}")
        print(f"  Mods Downloaded:    {success} / {total}")
        print("="*40 + "\nDone! You can import this folder into your launcher.")
        
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
