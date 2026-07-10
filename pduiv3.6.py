#!/usr/bin/env python3
# Proton Professional Backup v3.5 (High-Security Hardened Edition)
# Copyright (C) 2026 Mark Sean Ryan (ayenack29)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
import sys
import time
import glob
import shutil
import socket
import subprocess
import threading
import datetime
import json
import secrets
import string
import hashlib
import base64
import tempfile
import logging
import logging.handlers
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from cryptography.fernet import Fernet, InvalidToken

def get_app_dir():
    """Directory for config + logs, independent of the current working
    directory (fixes config location changing based on launch cwd)."""
    app_dir = os.path.join(os.path.expanduser("~"), ".config", "proton-backup")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

CONFIG_FILE = os.path.join(get_app_dir(), "config.json")
LOG_FILE = os.path.join(get_app_dir(), "pdui.log")
REQUIRED_TOOLS = ["gpg", "tar", "zstd", "proton-drive"]

class ProtonBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Proton Professional Backup v3.6")
        self.root.geometry("1920x1080")
        self.cancel_event = threading.Event()
        self.session_authenticated = False
        self.core_ui_built = False
        self.config = {
            "labels_history": [],
            "last_label": "",
            "password_hash": "",
            "password_salt": "",
            "vault_salt": "",
            "vault": {},
            "retention_count": 0
        }
        # Derived from the master password at login/registration time.
        # Lives in memory only - never written to disk.
        self.vault_key = None
        self.backup_target = ""
        self.is_file_mode = False
        self.dest_dir = ""
        self.animation_frames = [
            "(swiping your data... )",
            "(packing the bag... )",
            "(launching to Switzerland... )",
            "(encryption magic complete! )"
        ]
        self.current_frame_idx = 0
        self.spinner_chars = ["|", "/", "-", "\\"]
        self.spinner_idx = 0
        self.backup_active = False
        self.restore_active = False
        # Currently-running subprocesses, so Cancel can actually terminate
        # them instead of just flipping a flag nothing checks.
        self.active_procs = []
        
        self.file_logger = logging.getLogger("proton_backup")
        self.file_logger.setLevel(logging.INFO)
        if not self.file_logger.handlers:
            handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            self.file_logger.addHandler(handler)
        
        # Pre-emptive boot-level cache sweep
        self.cleanup_paths("/tmp/proton-drive*")
        
        self.load_config()
        self.evaluate_security_gate()
        self.root.after(500, self.check_dependencies)

    def check_dependencies(self):
        missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
        if missing:
            messagebox.showwarning(
                "Missing Dependencies",
                "The following required tools were not found on your PATH:\n\n"
                + "\n".join(f" • {m}" for m in missing) +
                "\n\nFeatures relying on them will fail until installed:\n"
                " • gpg → encryption/decryption\n"
                " • tar → archive creation/extraction\n"
                " • zstd → compression (requires the 'zstd' CLI package, not just libzstd)\n"
                " • proton-drive → cloud upload/download"
            )

    def cancel_current_operation(self):
        if not (self.backup_active or self.restore_active):
            return
        self.cancel_event.set()
        for p in list(self.active_procs):
            try:
                p.terminate()
            except Exception:
                pass

    def register_proc(self, proc):
        self.active_procs.append(proc)
        return proc

    def unregister_proc(self, proc):
        if proc in self.active_procs:
            self.active_procs.remove(proc)

    def cleanup_paths(self, *patterns):
        """Delete files/dirs matching glob patterns without invoking a shell."""
        for pattern in patterns:
            for path in glob.glob(pattern):
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                except OSError:
                    pass

    def get_dir_size(self, path):
        """Sum file sizes under `path`. Used as a real, local progress signal."""
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total

    def start_size_progress(self, bar, get_size_fn, total_bytes):
        """Drive a determinate progress bar from a real on-disk size signal.

        Deliberately never parses text output from an external CLI (that's
        what made progress reporting flaky before) - it only ever polls a
        file/folder size on disk that this app itself is writing. Progress
        is capped at 95% until the caller calls finish_progress(), so it
        never claims "100%" before the operation has actually finished.
        """
        stop_event = threading.Event()

        def _poll():
            while not stop_event.is_set():
                try:
                    current = get_size_fn()
                    pct = min(95.0, (current / total_bytes) * 100) if total_bytes > 0 else 0.0
                except OSError:
                    pct = 0.0
                self.root.after(0, lambda p=pct: bar.config(mode="determinate", value=p))
                if stop_event.wait(0.2):
                    break

        threading.Thread(target=_poll, daemon=True).start()
        return stop_event

    def finish_progress(self, bar, stop_event, success=True):
        stop_event.set()
        final = 100 if success else 0
        self.root.after(0, lambda: bar.config(mode="determinate", value=final))

    def start_indeterminate_progress(self, bar):
        """For phases with no reliable local signal (e.g. network transfer
        via the Proton Drive CLI) - an honest 'working, can't measure' bar
        instead of a fake percentage."""
        def _go():
            bar.config(mode="indeterminate")
            bar.start(12)
        self.root.after(0, _go)

    def stop_indeterminate_progress(self, bar, success=True):
        def _go():
            bar.stop()
            bar.config(mode="determinate", value=100 if success else 0)
        self.root.after(0, _go)

    def hash_password_securely(self, password, salt=None):
        if salt is None:
            salt = secrets.token_hex(16)
        pwd_bytes = password.encode('utf-8')
        salt_bytes = bytes.fromhex(salt)
        derived_key = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
        return derived_key.hex(), salt

    def derive_vault_key(self, password, vault_salt_hex):
        """Derive a Fernet-compatible key from the master password.

        Uses a separate salt (and derivation context) from the login
        hash so this key material never overlaps with password_hash.
        """
        pwd_bytes = password.encode('utf-8')
        salt_bytes = bytes.fromhex(vault_salt_hex)
        raw_key = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 200000, dklen=32)
        return base64.urlsafe_b64encode(raw_key)

    def encrypt_for_vault(self, plaintext):
        if not self.vault_key:
            raise RuntimeError("Vault key not available - not authenticated.")
        return Fernet(self.vault_key).encrypt(plaintext.encode('utf-8')).decode('utf-8')

    def decrypt_from_vault(self, token):
        if not self.vault_key:
            raise RuntimeError("Vault key not available - not authenticated.")
        return Fernet(self.vault_key).decrypt(token.encode('utf-8')).decode('utf-8')

    def evaluate_security_gate(self):
        if not self.config.get("password_hash"):
            self.show_register_screen()
        else:
            self.show_login_screen()

    def show_register_screen(self):
        self.gate_window = ttk.Frame(self.root, padding="30")
        self.gate_window.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        ttk.Label(self.gate_window, text="Proton Drive Profession Backup V3.6 - Initialize Master Vault Password", font=("Helvetica", 14, "bold")).pack(pady=10, padx=20)
        ttk.Label(self.gate_window, text="Set a permanent master password. This will be cryptographically hashed\nand salted to shield your repository interface from local tampering.").pack(pady=5, padx=20)
        
        self.reg_pass = ttk.Entry(self.gate_window, show="*", justify="center", font=("Helvetica", 14))
        self.reg_pass.pack(pady=5, ipady=4)
        ttk.Label(self.gate_window, text="Confirm Master Password:").pack(pady=2)
        self.reg_pass_conf = ttk.Entry(self.gate_window, show="*", justify="center", font=("Helvetica", 14))
        self.reg_pass_conf.pack(pady=5, ipady=4)
        self.reg_pass.focus()
        
        ttk.Button(self.gate_window, text="Create Cryptographic Hash & Lock", command=self.handle_registration).pack(pady=10)

    def handle_registration(self):
        p1 = self.reg_pass.get()
        p2 = self.reg_pass_conf.get()
        if not p1 or p1 != p2:
            messagebox.showerror("Error", "Passwords must match and cannot be empty!")
            return
        h_val, s_val = self.hash_password_securely(p1)
        self.config["password_hash"] = h_val
        self.config["password_salt"] = s_val
        self.config["vault_salt"] = secrets.token_hex(16)
        self.vault_key = self.derive_vault_key(p1, self.config["vault_salt"])
        self.save_config()
        self.reg_pass.delete(0, tk.END)
        self.reg_pass_conf.delete(0, tk.END)
        self.gate_window.destroy()
        self.session_authenticated = True
        self.setup_main_application_core()

    def show_login_screen(self):
        self.gate_window = ttk.Frame(self.root, padding="30")
        self.gate_window.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        ttk.Label(self.gate_window, text="Proton Professional Backup v3.6 - Unlock", font=("Helvetica", 14, "bold")).pack(pady=10, padx=20)
        self.login_pass = ttk.Entry(self.gate_window, show="*", justify="center", font=("Helvetica", 14))
        self.login_pass.pack(pady=10, ipady=4)
        self.login_pass.focus()
        ttk.Button(self.gate_window, text="Verify Vault Credentials", command=self.handle_login).pack(pady=5)

    def handle_login(self):
        entered = self.login_pass.get()
        salt = self.config.get("password_salt", "")
        stored_hash = self.config.get("password_hash", "")
        test_hash, _ = self.hash_password_securely(entered, salt)
        self.login_pass.delete(0, tk.END)
        
        if secrets.compare_digest(test_hash, stored_hash):
            # Backward-compat: older config files won't have a vault_salt yet.
            if not self.config.get("vault_salt"):
                self.config["vault_salt"] = secrets.token_hex(16)
                self.config["vault"] = {}  # old plaintext entries can't be migrated safely
                self.save_config()
            self.vault_key = self.derive_vault_key(entered, self.config["vault_salt"])
            self.gate_window.destroy()
            self.session_authenticated = True
            self.setup_main_application_core()
        else:
            messagebox.showerror("Access Denied", "Incorrect Master Password!")

    def lock_application_interface(self):
        if hasattr(self, 'notebook'):
            self.notebook.pack_forget()
        self.session_authenticated = False
        self.backup_active = False
        self.restore_active = False
        self.vault_key = None
        
        # Cleanup UI state
        if hasattr(self, 'pass1'): self.pass1.delete(0, tk.END)
        if hasattr(self, 'pass2'): self.pass2.delete(0, tk.END)
        if hasattr(self, 'restore_pass'): self.restore_pass.delete(0, tk.END)
        
        self.backup_target = ""
        self.dest_dir = ""
        self.show_login_screen()

    def setup_main_application_core(self):
        if self.core_ui_built:
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            self.session_authenticated = True
            return
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.backup_frame = ttk.Frame(self.notebook, padding="10")
        self.restore_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.backup_frame, text="Backup Archive")
        self.notebook.add(self.restore_frame, text="Restore Archive")
        
        self.setup_backup_tab()
        self.setup_restore_tab()
        self.core_ui_built = True
        
        self.animate_header()
        self.animate_loading_spinners()
        self.check_network_reachability()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
            except Exception:
                pass
            
    def save_config(self):
        try:
            config_dir = os.path.dirname(CONFIG_FILE) or "."
            fd, tmp_path = tempfile.mkstemp(dir=config_dir, prefix=".config_", suffix=".tmp")
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(self.config, f)
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, CONFIG_FILE)  # atomic on POSIX
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            print(f"Failed to isolate configuration layer: {e}")

    def animate_header(self):
        if hasattr(self, 'anim_label_backup') and hasattr(self, 'anim_label_restore') and self.session_authenticated:
            current_text = self.animation_frames[self.current_frame_idx]
            self.anim_label_backup.config(text=current_text)
            self.anim_label_restore.config(text=current_text)
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.animation_frames)
        self.root.after(1500, self.animate_header)

    def animate_loading_spinners(self):
        if self.session_authenticated:
            char = self.spinner_chars[self.spinner_idx]
            self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
            
            if self.backup_active:
                prefix = getattr(self, 'backup_status_prefix', "PROCESSING")
                self.backup_status_label.config(text=f"[ {char} {prefix} ]", foreground="orange")
            
            if self.restore_active:
                prefix = getattr(self, 'restore_status_prefix', "PROCESSING")
                self.restore_status_label.config(text=f"[ {char} {prefix} ]", foreground="orange")
        self.root.after(100, self.animate_loading_spinners)

    def wipe_vault_history(self):
        if messagebox.askyesno("Security Clearance", "Permanently clear historical data labels?"):
            self.config["labels_history"] = []
            self.config["last_label"] = "My-Backup"
            self.config["vault"] = {}
            self.save_config()
            self.backup_name_entry.config(values=[])
            self.backup_name_entry.set("My-Backup")
            self.log("System Action: Operational label history cleared.", self.log_box_backup)

    def check_network_reachability(self):
        def _ping():
            self.network_status_label.config(text=" Auditing Network Nodes...", foreground="orange")
            try:
                socket.create_connection(("api.protonmail.ch", 443), timeout=4)
                self.network_status_label.config(text=" Secure", foreground="green")
            except Exception:
                self.network_status_label.config(text=" Firewalled", foreground="red")
        threading.Thread(target=_ping, daemon=True).start()

    def get_friendly_file_size(self, filepath):
        try:
            bytes_size = os.path.getsize(filepath)
            return self.format_bytes(bytes_size), bytes_size
        except Exception:
            return "Unknown size", 0

    def format_bytes(self, size_in_bytes):
        bytes_size = float(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0: return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"

    def send_desktop_notification(self, title, message):
        threading.Thread(target=lambda: self._trigger_notification(title, message), daemon=True).start()

    def _trigger_notification(self, title, message):
        try:
            if sys.platform.startswith("linux"):
                subprocess.run(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform == "darwin":
                cmd = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def generate_random_passphrase(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        generated = "".join(secrets.choice(alphabet) for _ in range(24))
        self.pass1.delete(0, tk.END)
        self.pass1.insert(0, generated)
        self.pass2.delete(0, tk.END)
        self.pass2.insert(0, generated)

    def toggle_passphrase_visibility(self, e1, e2, btn):
        if e1.cget("show") == "*":
            e1.config(show="")
            if e2: e2.config(show="")
            btn.config(text=" Hide Passphrase")
        else:
            e1.config(show="*")
            if e2: e2.config(show="*")
            btn.config(text=" Show Passphrase")

    def log(self, text, box):
        box.config(state=tk.NORMAL)
        box.insert(tk.END, f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}\n")
        box.see(tk.END)
        box.config(state=tk.DISABLED)
        try:
            self.file_logger.info(text)
        except Exception:
            pass

    def browse_backup_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.backup_target = selected
            self.is_file_mode = False
            self.dir_label.config(text=f" Folder Selected: {selected}")

    def browse_backup_files(self):
        selected = filedialog.askopenfilename(title="Select Target File", filetypes=[("All Files", "*.*")])
        if selected:
            self.backup_target = selected
            self.is_file_mode = True
            self.dir_label.config(text=f" Individual File Selected: {selected}")

    def select_dest(self):
        selected = filedialog.askdirectory()
        if selected:
            self.dest_dir = selected
            self.dest_label.config(text=self.dest_dir)

    def setup_backup_tab(self):
        utility_frame = ttk.Frame(self.backup_frame)
        utility_frame.pack(fill=tk.X, pady=(0, 10))
        self.network_status_label = ttk.Label(utility_frame, text="Checking Network...", font=("Helvetica", 10, "bold"))
        self.network_status_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(utility_frame, text=" Test Route Link", command=self.check_network_reachability).pack(side=tk.LEFT, padx=5)
        ttk.Button(utility_frame, text=" Lock App Screen", command=self.lock_application_interface).pack(side=tk.LEFT, padx=5)
        ttk.Button(utility_frame, text=" Wipe Local History", command=self.wipe_vault_history).pack(side=tk.RIGHT, padx=5)
        
        self.anim_label_backup = ttk.Label(self.backup_frame, text="", font=("Helvetica", 12, "italic"), foreground="#2196F3")
        self.anim_label_backup.pack(pady=5)
        
        ttk.Label(self.backup_frame, text="Selected Source Path:").pack(anchor=tk.W)
        self.dir_label = ttk.Label(self.backup_frame, text="No folder or file selected", font=("Helvetica", 10, "bold"))
        self.dir_label.pack(anchor=tk.W, pady=2)
        
        btn_path_frame = ttk.Frame(self.backup_frame)
        btn_path_frame.pack(anchor=tk.W, pady=5)
        ttk.Button(btn_path_frame, text=" Browse Folder", command=self.browse_backup_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_path_frame, text=" Browse Files", command=self.browse_backup_files).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(self.backup_frame, text="Backup Label Profile History:").pack(anchor=tk.W, pady=(5,0))
        self.backup_name_entry = ttk.Combobox(self.backup_frame, values=self.config.get("labels_history", []))
        self.backup_name_entry.set(self.config.get("last_label", "My-Backup"))
        self.backup_name_entry.pack(fill=tk.X)
        
        self.mem_mode = tk.BooleanVar()
        ttk.Checkbutton(self.backup_frame, text="Use RAM Disk (/dev/shm)", variable=self.mem_mode).pack(anchor=tk.W, pady=5)
        
        retention_frame = ttk.Frame(self.backup_frame)
        retention_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(retention_frame, text="Keep last N remote backups for this label (0 = unlimited):").pack(side=tk.LEFT)
        self.retention_var = tk.StringVar(value=str(self.config.get("retention_count", 0)))
        retention_spin = ttk.Spinbox(retention_frame, from_=0, to=999, width=5, textvariable=self.retention_var, command=self._save_retention_setting)
        retention_spin.pack(side=tk.LEFT, padx=5)
        retention_spin.bind("<FocusOut>", lambda e: self._save_retention_setting())
        
        pass_lbl_frame = ttk.Frame(self.backup_frame)
        pass_lbl_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(pass_lbl_frame, text="Encryption Passphrase:").pack(side=tk.LEFT)
        ttk.Button(pass_lbl_frame, text=" Generate Passphrase", command=self.generate_random_passphrase).pack(side=tk.RIGHT, padx=2)
        self.btn_reveal_backup = ttk.Button(pass_lbl_frame, text=" Reveal Passphrase", command=lambda: self.toggle_passphrase_visibility(self.pass1, self.pass2, self.btn_reveal_backup))
        self.btn_reveal_backup.pack(side=tk.RIGHT, padx=2)
        
        self.pass1 = ttk.Entry(self.backup_frame, show="*")
        self.pass1.pack(fill=tk.X)
        ttk.Label(self.backup_frame, text="Confirm Passphrase:").pack(anchor=tk.W)
        self.pass2 = ttk.Entry(self.backup_frame, show="*")
        self.pass2.pack(fill=tk.X)
        
        btn_frame = ttk.Frame(self.backup_frame)
        btn_frame.pack(pady=10)
        self.btn_begin_backup = ttk.Button(btn_frame, text="Begin Backup", command=self.run_backup_with_check)
        self.btn_begin_backup.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel_current_operation).pack(side=tk.LEFT, padx=5)
        
        self.backup_status_label = ttk.Label(self.backup_frame, text="[ STANDBY ]", font=("Courier", 11, "bold"), foreground="green")
        self.backup_status_label.pack(anchor=tk.W, pady=(0, 2))
        
        self.backup_progress = ttk.Progressbar(self.backup_frame, mode="determinate", maximum=100)
        self.backup_progress.pack(fill=tk.X, pady=(0, 5))
        
        self.log_box_backup = tk.Text(self.backup_frame, height=12, bg="black", font=("Courier", 10), fg="lime")
        self.log_box_backup.pack(fill=tk.BOTH, expand=True)

    def setup_restore_tab(self):
        utility_frame_r = ttk.Frame(self.restore_frame)
        utility_frame_r.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(utility_frame_r, text=" Lock App Screen", command=self.lock_application_interface).pack(side=tk.LEFT, padx=5)
        
        self.anim_label_restore = ttk.Label(self.restore_frame, text="", font=("Helvetica", 12, "italic"), foreground="#2196F3")
        self.anim_label_restore.pack(pady=5)
        
        ttk.Label(self.restore_frame, text="Cloud Archives Available:").pack(anchor=tk.W)
        ttk.Button(self.restore_frame, text=" Refresh Cloud List", command=self.refresh_cloud_list).pack(anchor=tk.W, pady=2)
        
        self.file_listbox = tk.Listbox(self.restore_frame, height=6)
        self.file_listbox.pack(fill=tk.BOTH, pady=5)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_restore_file_selected)
        
        ttk.Button(self.restore_frame, text=" Select Destination Folder", command=self.select_dest).pack(anchor=tk.W)
        self.dest_label = ttk.Label(self.restore_frame, text="No destination selected")
        self.dest_label.pack(anchor=tk.W, pady=2)
        
        restore_pass_frame = ttk.Frame(self.restore_frame)
        restore_pass_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(restore_pass_frame, text="Decryption Passphrase:").pack(side=tk.LEFT)
        self.btn_reveal_restore = ttk.Button(restore_pass_frame, text=" Reveal Passphrase", command=lambda: self.toggle_passphrase_visibility(self.restore_pass, None, self.btn_reveal_restore))
        self.btn_reveal_restore.pack(side=tk.RIGHT)
        
        self.restore_pass = ttk.Entry(self.restore_frame, show="*")
        self.restore_pass.pack(fill=tk.X, pady=5)
        
        btn_frame = ttk.Frame(self.restore_frame)
        btn_frame.pack(pady=10)
        self.btn_start_restore = ttk.Button(btn_frame, text="Start Restore", command=self.run_restore)
        self.btn_start_restore.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel_current_operation).pack(side=tk.LEFT, padx=5)
        
        self.restore_status_label = ttk.Label(self.restore_frame, text="[ STANDBY ]", font=("Courier", 11, "bold"), foreground="green")
        self.restore_status_label.pack(anchor=tk.W, pady=(0, 2))
        
        self.restore_progress = ttk.Progressbar(self.restore_frame, mode="determinate", maximum=100)
        self.restore_progress.pack(fill=tk.X, pady=(0, 5))
        
        self.log_box_restore = tk.Text(self.restore_frame, height=12, bg="black", font=("Courier", 10), fg="yellow")
        self.log_box_restore.pack(fill=tk.BOTH, expand=True)

    def refresh_cloud_list(self):
        def _fetch():
            self.restore_active = True
            self.restore_status_prefix = "SCANNING CLOUD FILESYSTEMS"
            try:
                res = subprocess.run(["proton-drive", "filesystem", "list", "/my-files"], capture_output=True, text=True, check=True)
                self.file_listbox.delete(0, tk.END)
                for line in res.stdout.splitlines():
                    if ".gpg" in line: self.file_listbox.insert(tk.END, line.split()[-1])
                self.root.after(0, lambda: self.restore_status_label.config(text="[  SCAN SYNCED ]", foreground="green"))
            except Exception as e:
                self.log(f"Cloud query failure: {e}", self.log_box_restore)
            finally:
                self.restore_active = False
        threading.Thread(target=_fetch).start()

    def on_restore_file_selected(self, event):
        if not self.file_listbox.curselection(): return
        selected = self.file_listbox.get(self.file_listbox.curselection()).strip()
        inferred_label = "My-Backup"
        if '_20' in selected:
            inferred_label = selected.split('_20')[0]
        elif '_' in selected:
            inferred_label = selected.split('_')[0]
            
        if inferred_label in self.config.get("vault", {}):
            try:
                decrypted = self.decrypt_from_vault(self.config["vault"][inferred_label])
            except (InvalidToken, RuntimeError) as e:
                self.log(f"Vault: couldn't decrypt stored passphrase for '{inferred_label}': {e}", self.log_box_restore)
                return
            self.restore_pass.delete(0, tk.END)
            self.restore_pass.insert(0, decrypted)
            self.log(f"Vault: Autoloaded passphrase match for '{inferred_label}'!", self.log_box_restore)

    def is_weak_passphrase(self, pw):
        if len(pw) < 12:
            return True
        categories = sum([
            any(c.islower() for c in pw),
            any(c.isupper() for c in pw),
            any(c.isdigit() for c in pw),
            any(not c.isalnum() for c in pw),
        ])
        return categories < 2

    def _save_retention_setting(self):
        try:
            value = int(self.retention_var.get())
        except (ValueError, AttributeError):
            value = 0
        value = max(0, value)
        self.config["retention_count"] = value
        self.save_config()

    def prune_remote_backups(self, label, keep_count):
        """Best-effort deletion of older remote backups beyond keep_count for
        this label. Never treated as fatal - if the CLI's delete subcommand
        doesn't behave as expected, this just logs a warning and stops."""
        def _prune():
            try:
                res = subprocess.run(["proton-drive", "filesystem", "list", "/my-files"], capture_output=True, text=True, check=True)
                candidates = []
                for line in res.stdout.splitlines():
                    if ".gpg" not in line:
                        continue
                    name = line.split()[-1]
                    if name.startswith(f"{label}_"):
                        candidates.append(name)
                # Filenames embed a sortable timestamp (YYYYMMDD_HHMMSS_ffffff),
                # so lexicographic sort = chronological order.
                candidates.sort()
                to_delete = candidates[:-keep_count] if keep_count > 0 else []
                for old_file in to_delete:
                    del_proc = subprocess.run(
                        ["proton-drive", "filesystem", "delete", f"/my-files/{old_file}"],
                        capture_output=True, text=True
                    )
                    if del_proc.returncode == 0:
                        self.log(f"Pruned old backup: {old_file}", self.log_box_backup)
                    else:
                        self.log(f"Could not prune '{old_file}' automatically - remove it manually via the Proton Drive web app if desired.", self.log_box_backup)
                        break  # if delete isn't supported as expected, stop rather than spam failures
            except Exception as e:
                self.log(f"Retention pruning skipped (non-fatal): {e}", self.log_box_backup)
        threading.Thread(target=_prune, daemon=True).start()

    def run_backup_with_check(self):
        if self.backup_active or self.restore_active:
            return messagebox.showinfo("Busy", "Another backup/restore operation is already running.")
        if not self.backup_target: return messagebox.showerror("Error", "Select source path first!")
        if self.pass1.get() != self.pass2.get(): return messagebox.showerror("Error", "Passwords do not match!")
        if not self.pass1.get(): return messagebox.showerror("Error", "Password cannot be empty!")
        
        if self.is_weak_passphrase(self.pass1.get()):
            if not messagebox.askyesno(
                "Weak Passphrase",
                "This passphrase looks short or low-variety (aim for 12+ characters "
                "mixing upper/lower/digits/symbols, or use Generate Passphrase).\n\n"
                "Continue with it anyway?"
            ):
                return
        
        current_label = self.backup_name_entry.get().strip() or "Backup"
        if "vault" not in self.config: self.config["vault"] = {}
        if current_label not in self.config["labels_history"]:
            self.config["labels_history"].append(current_label)
            self.config["last_label"] = current_label
            self.config["vault"][current_label] = self.encrypt_for_vault(self.pass1.get())
            self.save_config()
            self.backup_name_entry.config(values=self.config["labels_history"])
            
        self.cancel_event.clear()
        self.btn_begin_backup.config(state=tk.DISABLED)
        
        def _thread():
            try:
                self.execute_backup()
            finally:
                self.root.after(0, lambda: self.btn_begin_backup.config(state=tk.NORMAL))
        threading.Thread(target=_thread, daemon=True).start()

    def run_restore(self):
        if self.backup_active or self.restore_active:
            return messagebox.showinfo("Busy", "Another backup/restore operation is already running.")
        if not getattr(self, 'dest_dir', None): return messagebox.showerror("Error", "Select destination folder!")
        if not self.restore_pass.get(): return messagebox.showerror("Error", "Enter decryption password!")
        self.cancel_event.clear()
        self.btn_start_restore.config(state=tk.DISABLED)
        
        def _thread():
            try:
                self.execute_restore()
            finally:
                self.root.after(0, lambda: self.btn_start_restore.config(state=tk.NORMAL))
        threading.Thread(target=_thread, daemon=True).start()

    def read_stream_lines_to_log(self, proc, text_box, collect_into=None):
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                self.root.after(0, self.log, line.strip(), text_box)
                if collect_into is not None:
                    collect_into.append(line.strip())

    def execute_backup(self):
        self.backup_active = True
        self.backup_status_prefix = " CRYPTOGRAPHIC PACKAGING"
        label = self.config["last_label"]
        passphrase = self.pass1.get()
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{label}_{timestamp}.tar.zst.gpg"
        target = os.path.join("/dev/shm", filename) if self.mem_mode.get() and os.path.exists("/dev/shm") else os.path.join(os.getcwd(), filename)
        self.root.after(0, lambda: self.backup_progress.config(mode="determinate", value=0))
        
        def _cancelled(cleanup_files=()):
            self.backup_active = False
            for p in cleanup_files:
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except OSError: pass
            self.root.after(0, lambda: self.backup_status_label.config(text="[ CANCELLED ]", foreground="orange"))
            self.log("Backup cancelled by user.", self.log_box_backup)
        
        try:
            source_size = os.path.getsize(self.backup_target) if self.is_file_mode else self.get_dir_size(self.backup_target)
        except OSError:
            source_size = 0
        
        temp_tar = None
        try:
            if self.is_file_mode:
                encrypt_input_size = source_size
            else:
                temp_tar = target.replace(".gpg", "")
                tar_cmd = ["tar", "--zstd", "--no-wildcards", "-cf", temp_tar, "-C", self.backup_target, "."]
                tar_proc = self.register_proc(subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                tar_progress = self.start_size_progress(
                    self.backup_progress,
                    lambda: os.path.getsize(temp_tar) if os.path.exists(temp_tar) else 0,
                    source_size
                )
                _, tar_err = tar_proc.communicate()
                self.unregister_proc(tar_proc)
                self.finish_progress(self.backup_progress, tar_progress, success=(tar_proc.returncode == 0))
                if self.cancel_event.is_set():
                    return _cancelled([temp_tar])
                if tar_proc.returncode != 0:
                    self.backup_active = False
                    self.root.after(0, lambda: self.backup_status_label.config(text="[ COMPRESSION FAILED ]", foreground="red"))
                    self.log(f"Compression failed: {tar_err.decode(errors='replace') if tar_err else ''}", self.log_box_backup)
                    return
                encrypt_input_size = os.path.getsize(temp_tar) if os.path.exists(temp_tar) else source_size
            
            self.root.after(0, lambda: self.backup_progress.config(value=0))
            if self.is_file_mode:
                cmd = ["gpg", "--batch", "--yes", "--passphrase-fd", "0", "-c", "-o", target, self.backup_target]
            else:
                cmd = ["gpg", "--batch", "--yes", "--passphrase-fd", "0", "-c", "-o", target, temp_tar]
            
            g_proc = self.register_proc(subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            encrypt_progress = self.start_size_progress(
                self.backup_progress,
                lambda: os.path.getsize(target) if os.path.exists(target) else 0,
                encrypt_input_size
            )
            _, g_stderr = g_proc.communicate(input=(passphrase + "\n").encode('utf-8'))
            self.unregister_proc(g_proc)
            returncode = g_proc.returncode
            self.finish_progress(self.backup_progress, encrypt_progress, success=(returncode == 0))
            
            if not self.is_file_mode and temp_tar and os.path.exists(temp_tar):
                os.remove(temp_tar)
            
            if self.cancel_event.is_set():
                return _cancelled([target])
            
            if returncode != 0:
                self.backup_active = False
                self.root.after(0, lambda: self.backup_status_label.config(text="[ ENCRYPTION FAILED ]", foreground="red"))
                err_txt = g_stderr.decode(errors='replace') if g_stderr else ""
                self.log(f"Encryption failed: {err_txt}", self.log_box_backup)
                return
        except Exception as e:
            self.backup_active = False
            self.root.after(0, lambda: self.backup_status_label.config(text="[ ENGINE FAULT ]", foreground="red"))
            return self.log(f"Error: {e}", self.log_box_backup)
        finally:
            # Note: Python strings are immutable, so there is no reliable way
            # to scrub `passphrase` from memory here. Clearing the widgets is
            # the only thing we can meaningfully do at the application level.
            self.pass1.delete(0, tk.END)
            self.pass2.delete(0, tk.END)
        
        friendly_size, byte_units = self.get_friendly_file_size(target)
        self.backup_status_prefix = " UPLOADING TO PROTON DRIVE"
        self.start_indeterminate_progress(self.backup_progress)
        try:
            proc = self.register_proc(subprocess.Popen(["proton-drive", "filesystem", "upload", target, "/my-files/"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1))
            upload_output = []
            self.read_stream_lines_to_log(proc, self.log_box_backup, collect_into=upload_output)
            proc.wait()
            self.unregister_proc(proc)
            self.backup_active = False
            
            if self.cancel_event.is_set():
                self.stop_indeterminate_progress(self.backup_progress, success=False)
                self.log("Upload cancelled by user.", self.log_box_backup)
                self.root.after(0, lambda: self.backup_status_label.config(text="[ CANCELLED ]", foreground="orange"))
                return
            
            if proc.returncode == 0:
                self.stop_indeterminate_progress(self.backup_progress, success=True)
                self.log("Backup Successfully Synchronised!", self.log_box_backup)
                self.root.after(0, lambda: self.backup_status_label.config(text="[ COMPLETE ]", foreground="green"))
                self.send_desktop_notification("Backup Successful", f"Uploaded {friendly_size}.")
                retention = self.config.get("retention_count", 0)
                if retention and retention > 0:
                    self.prune_remote_backups(label, retention)
            else:
                self.stop_indeterminate_progress(self.backup_progress, success=False)
                self.log("Proton Upload failed.", self.log_box_backup)
                out = " ".join(upload_output).lower()
                if "not found" in out or "no such" in out:
                    self.log("Hint: the destination folder may not exist yet - create it once via the Proton Drive web app, then try again.", self.log_box_backup)
        finally:
            if os.path.exists(target): os.remove(target)
            self.cleanup_paths("/tmp/proton-drive*")

    def execute_restore(self):
        self.restore_active = True
        self.restore_status_prefix = " DOWNLOADING CLOUD MANIFEST"
        self.root.after(0, lambda: self.restore_progress.config(mode="determinate", value=0))
        try:
            selected = self.file_listbox.get(self.file_listbox.curselection())
        except Exception:
            self.restore_active = False
            return self.log("Select a file from the list first!", self.log_box_restore)
        
        self.start_indeterminate_progress(self.restore_progress)
        try:
            # FIXED: Download command with conflict strategy and fixed filename logic
            proc = self.register_proc(subprocess.Popen(["proton-drive", "filesystem", "download", "-f", "replace", f"/my-files/{selected}", "."], 
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1))
            self.read_stream_lines_to_log(proc, self.log_box_restore)
            proc.wait()
            self.unregister_proc(proc)

            if self.cancel_event.is_set():
                self.stop_indeterminate_progress(self.restore_progress, success=False)
                self.restore_active = False
                self.root.after(0, lambda: self.restore_status_label.config(text="[ CANCELLED ]", foreground="orange"))
                return self.log("Download cancelled by user.", self.log_box_restore)

            if proc.returncode == 0:
                self.stop_indeterminate_progress(self.restore_progress, success=True)
                # Add timestamp to avoid local file conflicts
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                new_name = f"{selected.replace('.gpg', '')}_{timestamp}.gpg"

                # Double-check the file exists before renaming
                if os.path.exists(selected):
                    os.rename(selected, new_name)

                selected = new_name  # Update 'selected' so the decryption logic uses the new filename
                self.log(f"Downloaded and renamed to: {selected}", self.log_box_restore)
            else:
                self.stop_indeterminate_progress(self.restore_progress, success=False)
                self.restore_active = False
                self.root.after(0, lambda: self.restore_status_label.config(text="[ DOWNLOAD FAILED ]", foreground="red"))
                return self.log("Download failed.", self.log_box_restore)

        except Exception as e:
            self.stop_indeterminate_progress(self.restore_progress, success=False)
            self.restore_active = False
            self.root.after(0, lambda: self.restore_status_label.config(text="[ PIPELINE FAULT ]", foreground="red"))
            return self.log(f"Download error: {e}", self.log_box_restore)

        friendly_size, _ = self.get_friendly_file_size(selected)
        self.restore_status_prefix = " DECRYPTING AND EXTRACTING TARS"
        self.root.after(0, lambda: self.restore_progress.config(mode="determinate", value=0))
        passphrase = self.restore_pass.get()
        encrypted_size = os.path.getsize(selected) if os.path.exists(selected) else 0
        
        try:
            if "tar.zst" in selected or "tar.gz" in selected:
                # Support old gzip archives from before this update, as well
                # as the new zstd ones, so existing backups still restore.
                compress_flag = "--zstd" if "tar.zst" in selected else "-z"
                # Compressed archives typically expand ~2-4x on extraction;
                # this is only an estimate for the progress bar, so it's
                # capped at 95% until extraction actually finishes (see
                # start_size_progress/finish_progress).
                estimated_extracted_size = encrypted_size * 3
                extract_baseline = self.get_dir_size(self.dest_dir) if os.path.isdir(self.dest_dir) else 0
                
                g_cmd = ["gpg", "--batch", "--decrypt", "--passphrase-fd", "0", selected]
                g_proc = self.register_proc(subprocess.Popen(g_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                tar_cmd = ["tar", compress_flag, "--no-wildcards", "-xvf", "-", "-C", self.dest_dir]
                t_proc = self.register_proc(subprocess.Popen(tar_cmd, stdin=g_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                extract_progress = self.start_size_progress(
                    self.restore_progress,
                    lambda: max(0, self.get_dir_size(self.dest_dir) - extract_baseline),
                    estimated_extracted_size
                )
                g_proc.stdin.write((passphrase + "\n").encode('utf-8'))
                g_proc.stdin.close()
                t_proc.communicate()
                g_proc.wait()
                self.unregister_proc(g_proc)
                self.unregister_proc(t_proc)
                ret = g_proc.returncode
                self.finish_progress(self.restore_progress, extract_progress, success=(ret == 0))
            else:
                out_f = os.path.join(self.dest_dir, selected.replace('.gpg', ''))
                cmd = ["gpg", "--batch", "--decrypt", "--passphrase-fd", "0", "-o", out_f, selected]
                g_proc = self.register_proc(subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
                decrypt_progress = self.start_size_progress(
                    self.restore_progress,
                    lambda: os.path.getsize(out_f) if os.path.exists(out_f) else 0,
                    encrypted_size
                )
                _, g_stderr = g_proc.communicate(input=(passphrase + "\n").encode('utf-8'))
                self.unregister_proc(g_proc)
                ret = g_proc.returncode
                self.finish_progress(self.restore_progress, decrypt_progress, success=(ret == 0))
            
            self.restore_active = False
            
            if self.cancel_event.is_set():
                self.root.after(0, lambda: self.restore_status_label.config(text="[ CANCELLED ]", foreground="orange"))
                self.log("Restore cancelled by user.", self.log_box_restore)
                return
            
            if ret == 0:
                self.log("Restoration completely restored!", self.log_box_restore)
                self.root.after(0, lambda: self.restore_status_label.config(text="[ COMPLETE ]", foreground="green"))
                self.send_desktop_notification("Restore Successful", f"Extracted {friendly_size} archive.")
            else:
                self.root.after(0, lambda: self.restore_status_label.config(text="[ DECRYPTION FAILED ]", foreground="red"))
                self.log("Decryption/Extraction failed.", self.log_box_restore)
        except Exception as e:
            self.restore_active = False
            self.root.after(0, lambda: self.restore_status_label.config(text="[ EXTRACTION FAULT ]", foreground="red"))
            self.log(f"Runtime error: {e}", self.log_box_restore)
        finally:
            self.restore_pass.delete(0, tk.END)
            if os.path.exists(selected): os.remove(selected)
            self.cleanup_paths("/tmp/proton-drive*")

if __name__ == "__main__":
    root = tk.Tk()
    app = ProtonBackupGUI(root)
    root.mainloop()
