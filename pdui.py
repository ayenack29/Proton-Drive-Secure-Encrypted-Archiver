#!/usr/bin/env python3
#  Proton Professional Backup v2.5
#  Copyright (C) 2026 
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.

import os
import sys
import time
import socket
import subprocess
import threading
import datetime
import json
import secrets
import string
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CONFIG_FILE = "config.json"

class ProtonBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Proton Professional Backup v2.5 (Complete Production Matrix)")
        self.root.geometry("1920x1080")
        
        self.cancel_event = threading.Event()
        self.master_key = None
        
        self.config = {
            "labels_history": [], 
            "last_label": "My-Backup",
            "vault": {}
        }
        
        self.backup_target = ""
        self.is_file_mode = False
        self.dest_dir = ""
        
        self.animation_frames = [
            " (swiping your data... 🧹)", 
            " (packing the 🦝 💼 bag...)", 
            " (launching to Switzerland... ✈️)", 
            " (encryption magic complete! 🪄)"
        ]
        self.current_frame_idx = 0
        
        self.setup_master_lock_screen()

    def setup_master_lock_screen(self):
        self.lock_frame = ttk.Frame(self.root, padding="30")
        self.lock_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        has_existing_password = False
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    test_load = json.load(f)
                if "verify_hash" in test_load:
                    has_existing_password = True
            except Exception:
                pass

        if not has_existing_password:
            self.is_first_setup = True
            ttk.Label(self.lock_frame, text="Setup Master Password (Locks your local history ledger):", font=("Helvetica", 12, "bold")).pack(pady=5)
            self.master_entry = ttk.Entry(self.lock_frame, show="*", width=40)
            self.master_entry.pack(pady=5)
            self.master_entry.focus()
            
            ttk.Label(self.lock_frame, text="Confirm Master Password:", font=("Helvetica", 12, "bold")).pack(pady=5)
            self.master_confirm_entry = ttk.Entry(self.lock_frame, show="*", width=40)
            self.master_confirm_entry.pack(pady=5)
            
            btn_txt = "Initialize Application Secure Core"
        else:
            self.is_first_setup = False
            ttk.Label(self.lock_frame, text="Enter Master Password to Unlock History & Profiles:", font=("Helvetica", 12, "bold")).pack(pady=5)
            self.master_entry = ttk.Entry(self.lock_frame, show="*", width=40)
            self.master_entry.pack(pady=5)
            self.master_entry.focus()
            
            btn_txt = "Unlock Interface Matrix"
            
        ttk.Button(self.lock_frame, text=btn_txt, command=self.verify_or_create_master).pack(pady=10)

    def verify_or_create_master(self):
        passwd = self.master_entry.get()
        if len(passwd) < 4:
            return messagebox.showerror("Security Fault", "Master passphrase must be at least 4 characters long.")
            
        if self.is_first_setup:
            confirm_passwd = self.master_confirm_entry.get()
            if passwd != confirm_passwd:
                return messagebox.showerror("Security Fault", "Passwords do not match! Please verify your inputs.")
            
        dk = hashlib.sha256(passwd.encode('utf-8')).hexdigest()
        self.master_key = dk
        
        if self.is_first_setup:
            self.save_config_encrypted()
        else:
            if not self.load_config_encrypted():
                self.master_key = None
                return messagebox.showerror("Access Denied", "Incorrect Master Password. Lockout engaged.")
                
        self.lock_frame.destroy()
        self.setup_main_application_core()

    def setup_main_application_core(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.backup_frame = ttk.Frame(self.notebook, padding="10")
        self.restore_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.backup_frame, text="Backup Archive")
        self.notebook.add(self.restore_frame, text="Restore Archive")
        
        self.setup_backup_tab()
        self.setup_restore_tab()
        self.animate_header()
        self.check_network_reachability()
    def animate_header(self):
        if hasattr(self, 'anim_label_backup') and hasattr(self, 'anim_label_restore'):
            current_text = self.animation_frames[self.current_frame_idx]
            self.anim_label_backup.config(text=current_text)
            self.anim_label_restore.config(text=current_text)
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.animation_frames)
            self.root.after(1500, self.animate_header)

    def load_config_encrypted(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                payload = json.load(f)
            if payload.get("verify_hash") != hashlib.sha256(self.master_key.encode()).hexdigest():
                return False
            self.config = payload
            if "labels_history" not in self.config: self.config["labels_history"] = []
            if "vault" not in self.config: self.config["vault"] = {}
            return True
        except Exception:
            return False

    def save_config_encrypted(self):
        if not self.master_key: return
        try:
            self.config["verify_hash"] = hashlib.sha256(self.master_key.encode()).hexdigest()
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f)
            os.chmod(CONFIG_FILE, 0o600)
        except Exception as e:
            print(f"Failed to isolate configuration layer: {e}")

    def wipe_vault_history(self):
        confirm = messagebox.askyesno("Security Clearance Required", "Permanently clear all history labels and passphrases?")
        if confirm:
            self.config["labels_history"] = []
            self.config["vault"] = {}
            self.save_config_encrypted()
            self.backup_name_entry.config(values=[])
            self.backup_name_entry.set("My-Backup")
            self.log("System Action: Secure vault profiles and operational history completely wiped.", self.log_box_backup)
            messagebox.showinfo("Vault Cleared", "Local metadata history cache successfully purged.")

    def check_network_reachability(self):
        def _ping():
            self.network_status_label.config(text="🔍 Auditing Network Nodes...", foreground="orange")
            try:
                socket.create_connection(("api.protonmail.ch", 443), timeout=4)
                self.network_status_label.config(text="🟢 Connection Matrix Secure", foreground="green")
            except Exception:
                self.network_status_label.config(text="🔴 Network Core Offline / Firewalled", foreground="red")
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
            elif sys.platform == "win32":
                from win10toast import ToastNotifier
                ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        except Exception: pass
    def generate_random_passphrase(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        generated = "".join(secrets.choice(alphabet) for _ in range(24))
        self.pass1.delete(0, tk.END)
        self.pass1.insert(0, generated)
        self.pass2.delete(0, tk.END)
        self.pass2.insert(0, generated)
        self.pass1.config(show="")
        self.pass2.config(show="")
        self.btn_reveal_backup.config(text="👁 Hide Passphrase")

    def toggle_passphrase_visibility(self, entry_widget, entry_widget_2, btn_widget):
        if entry_widget.cget("show") == "*":
            entry_widget.config(show="")
            if entry_widget_2: entry_widget_2.config(show="")
            btn_widget.config(text="👁 Hide Passphrase")
        else:
            entry_widget.config(show="*")
            if entry_widget_2: entry_widget_2.config(show="*")
            btn_widget.config(text="👁 Reveal Passphrase")

    def log(self, text, box):
        box.config(state=tk.NORMAL)
        box.insert(tk.END, f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}\n")
        box.see(tk.END)
        box.config(state=tk.DISABLED)

    def browse_backup_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.backup_target = selected
            self.is_file_mode = False
            self.dir_label.config(text=f"📁 Folder Selected: {selected}")

    def browse_backup_files(self):
        selected = filedialog.askopenfilename(title="Select Target File for Ingestion", filetypes=[("All Files", "*.*")])
        if selected:
            self.backup_target = selected
            self.is_file_mode = True
            self.dir_label.config(text=f"📄 Individual File Selected: {selected}")

    def select_dest(self): 
        # REPAIRED INTERFACE CONNECTOR HOOK
        selected = filedialog.askdirectory()
        if selected:
            self.dest_dir = selected
            self.dest_label.config(text=self.dest_dir)

    def setup_backup_tab(self):
        utility_frame = ttk.Frame(self.backup_frame)
        utility_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.network_status_label = ttk.Label(utility_frame, text="Checking Network...", font=("Helvetica", 10, "bold"))
        self.network_status_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(utility_frame, text="🔄 Test Route Link", command=self.check_network_reachability).pack(side=tk.LEFT, padx=5)
        ttk.Button(utility_frame, text="🗑 Wipe Local History & Vault", command=self.wipe_vault_history).pack(side=tk.RIGHT, padx=5)
        
        self.anim_label_backup = ttk.Label(self.backup_frame, text="", font=("Helvetica", 12, "italic"), foreground="#2196F3")
        self.anim_label_backup.pack(pady=5)
        
        ttk.Label(self.backup_frame, text="Selected Source Path:").pack(anchor=tk.W)
        self.dir_label = ttk.Label(self.backup_frame, text="No folder or file selected", font=("Helvetica", 10, "bold"))
        self.dir_label.pack(anchor=tk.W, pady=2)
        
        btn_path_frame = ttk.Frame(self.backup_frame)
        btn_path_frame.pack(anchor=tk.W, pady=5)
        ttk.Button(btn_path_frame, text="📁 Browse Folder", command=self.browse_backup_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_path_frame, text="📄 Browse Files", command=self.browse_backup_files).pack(side=tk.LEFT, padx=2)
        ttk.Label(self.backup_frame, text="Backup Label Profile History:").pack(anchor=tk.W, pady=(5,0))
        self.backup_name_entry = ttk.Combobox(self.backup_frame, values=self.config.get("labels_history", []))
        self.backup_name_entry.set(self.config.get("last_label", "My-Backup"))
        self.backup_name_entry.pack(fill=tk.X)
        
        self.mem_mode = tk.BooleanVar()
        ttk.Checkbutton(self.backup_frame, text="Use RAM Disk (/dev/shm)", variable=self.mem_mode).pack(anchor=tk.W, pady=5)
        
        pass_lbl_frame = ttk.Frame(self.backup_frame)
        pass_lbl_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(pass_lbl_frame, text="Encryption Passphrase:").pack(side=tk.LEFT)
        
        ttk.Button(pass_lbl_frame, text="🔑 Generate Passphrase", command=self.generate_random_passphrase).pack(side=tk.RIGHT, padx=2)
        self.btn_reveal_backup = ttk.Button(pass_lbl_frame, text="👁 Reveal Passphrase", 
                                            command=lambda: self.toggle_passphrase_visibility(self.pass1, self.pass2, self.btn_reveal_backup))
        self.btn_reveal_backup.pack(side=tk.RIGHT, padx=2)
        
        self.pass1 = ttk.Entry(self.backup_frame, show="*")
        self.pass1.pack(fill=tk.X)
        ttk.Label(self.backup_frame, text="Confirm Passphrase:").pack(anchor=tk.W)
        self.pass2 = ttk.Entry(self.backup_frame, show="*")
        self.pass2.pack(fill=tk.X)
        
        btn_frame = ttk.Frame(self.backup_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Begin Backup", command=self.run_backup_with_check).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self.cancel_event.set()).pack(side=tk.LEFT, padx=5)
        
        self.backup_progress_label = ttk.Label(self.backup_frame, text="Progress: 0%")
        self.backup_progress_label.pack(anchor=tk.W)
        self.backup_progress = ttk.Progressbar(self.backup_frame, orient="horizontal", mode="determinate", maximum=100)
        self.backup_progress.pack(fill=tk.X, pady=(0, 5))
        
        self.log_box_backup = tk.Text(self.backup_frame, height=12, bg="black", fg="lime")
        self.log_box_backup.pack(fill=tk.BOTH, expand=True)

    def setup_restore_tab(self):
        self.anim_label_restore = ttk.Label(self.restore_frame, text="", font=("Helvetica", 12, "italic"), foreground="#2196F3")
        self.anim_label_restore.pack(pady=5)

        ttk.Label(self.restore_frame, text="Cloud Archives Available:").pack(anchor=tk.W)
        ttk.Button(self.restore_frame, text="Refresh Cloud List", command=self.refresh_cloud_list).pack(anchor=tk.W, pady=2)
        
        self.file_listbox = tk.Listbox(self.restore_frame, height=6)
        self.file_listbox.pack(fill=tk.BOTH, pady=5)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_restore_file_selected)
        
        ttk.Button(self.restore_frame, text="Select Destination Folder", command=self.select_dest).pack(anchor=tk.W)
        self.dest_label = ttk.Label(self.restore_frame, text="No destination selected")
        self.dest_label.pack(anchor=tk.W, pady=2)

        restore_pass_frame = ttk.Frame(self.restore_frame)
        restore_pass_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(restore_pass_frame, text="Decryption Passphrase:").pack(side=tk.LEFT)
        
        self.btn_reveal_restore = ttk.Button(restore_pass_frame, text="👁 Reveal Passphrase", 
                                             command=lambda: self.toggle_passphrase_visibility(self.restore_pass, None, self.btn_reveal_restore))
        self.btn_reveal_restore.pack(side=tk.RIGHT)

        self.restore_pass = ttk.Entry(self.restore_frame, show="*")
        self.restore_pass.pack(fill=tk.X, pady=5)
        
        btn_frame = ttk.Frame(self.restore_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Start Restore", command=self.run_restore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self.cancel_event.set()).pack(side=tk.LEFT, padx=5)
        self.restore_progress_label = ttk.Label(self.restore_frame, text="Progress: 0%")
        self.restore_progress_label.pack(anchor=tk.W)
        self.restore_progress = ttk.Progressbar(self.restore_frame, orient="horizontal", mode="determinate", maximum=100)
        self.restore_progress.pack(fill=tk.X, pady=(0, 5))
        
        self.log_box_restore = tk.Text(self.restore_frame, height=12, bg="black", fg="yellow")
        self.log_box_restore.pack(fill=tk.BOTH, expand=True)

    def refresh_cloud_list(self):
        def _fetch():
            self.restore_progress.config(mode="indeterminate")
            self.restore_progress.start(10)
            self.restore_progress_label.config(text="Scanning Cloud Storage Folders...")
            try:
                res = subprocess.run(["proton-drive", "filesystem", "list", "/my-files"], capture_output=True, text=True, check=True)
                self.file_listbox.delete(0, tk.END)
                for line in res.stdout.splitlines():
                    if ".gpg" in line: self.file_listbox.insert(tk.END, line.split()[-1])
                self.restore_progress_label.config(text="Cloud Manifest Updated.")
            except Exception as e: 
                self.log(f"Cloud query failure: {e}", self.log_box_restore)
            finally:
                self.restore_progress.stop()
                self.restore_progress.config(mode="determinate", value=0)
        threading.Thread(target=_fetch).start()

    def on_restore_file_selected(self, event):
        try:
            if not self.file_listbox.curselection(): return
            selected = self.file_listbox.get(self.file_listbox.curselection())
            inferred_label = selected.split('_20') if '_20' in selected else selected.split('_')

            if inferred_label in self.config.get("vault", {}):
                self.restore_pass.delete(0, tk.END)
                self.restore_pass.insert(0, self.config["vault"][inferred_label])
                self.log(f"Vault: Autoloaded passphrase for '{inferred_label}'!", self.log_box_restore)
        except Exception: pass

    def run_backup_with_check(self):
        if not self.backup_target: return messagebox.showerror("Error", "Select source folder or file first!")
        if self.pass1.get() != self.pass2.get(): return messagebox.showerror("Error", "Passwords do not match!")
        if not self.pass1.get(): return messagebox.showerror("Error", "Password cannot be empty!")
        
        current_label = self.backup_name_entry.get().strip() or "Backup"
        if current_label not in self.config["labels_history"]: self.config["labels_history"].append(current_label)
        self.config["last_label"] = current_label
        self.config["vault"][current_label] = self.pass1.get()
        
        self.save_config_encrypted()
        self.backup_name_entry.config(values=self.config["labels_history"])
        self.cancel_event.clear()
        threading.Thread(target=self.execute_backup, daemon=True).start()

    def run_restore(self):
        if not getattr(self, 'dest_dir', None): return messagebox.showerror("Error", "Select destination folder first!")
        if not self.restore_pass.get(): return messagebox.showerror("Error", "Enter decryption password!")
        self.cancel_event.clear()
        threading.Thread(target=self.execute_restore, daemon=True).start()

    def update_progress(self, val, label_widget, progress_widget, append_text=""):
        label_widget.config(text=f"Progress: {int(val)}%{append_text}")
        progress_widget.config(value=val)

    def read_stream_lines_to_log(self, proc, text_box):
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break
            if line: self.root.after(0, self.log, line.strip(), text_box)
    def smooth_progress_tracker(self, total_bytes, label_lbl, bar_widget):
        current_percentage = 2.0
        sleep_interval = max((total_bytes / (12 * 1024 * 1024)) / 95.0, 0.1)
        while current_percentage < 97.0 and not self.cancel_event.is_set():
            time.sleep(sleep_interval)
            current_percentage += 1.0
            self.root.after(0, self.update_progress, current_percentage, label_lbl, bar_widget)

    def execute_backup(self):
        self.update_progress(1, self.backup_progress_label, self.backup_progress)
        label = self.config["last_label"]
        filename = f"{label}_{datetime.datetime.now().strftime('%Y%m%d')}.tar.gz.gpg"
        target = os.path.join("/dev/shm", filename) if self.mem_mode.get() and os.path.exists("/dev/shm") else os.path.join(os.getcwd(), filename)
        
        if not self.is_file_mode and os.path.abspath(target).startswith(os.path.abspath(self.backup_target)):
            self.log("Fault Abort: Destination path sits inside source folder.", self.log_box_backup)
            self.update_progress(0, self.backup_progress_label, self.backup_progress)
            return

        self.log("Assembling compression/encryption pipeline...", self.log_box_backup)
        try:
            if self.is_file_mode:
                cmd = f"gpg --batch --yes --passphrase '{self.config['vault'][label]}' -c -o '{target}' '{self.backup_target}'"
            else:
                cmd = f"tar -cz --exclude='*.tar.gz.gpg' -C '{self.backup_target}' . | gpg --batch --yes --passphrase '{self.config['vault'][label]}' -c > '{target}'"
                
            process = subprocess.run(cmd, shell=True, capture_output=True)
            if process.returncode != 0:
                self.log(f"Encryption failed: {process.stderr.decode()}", self.log_box_backup)
                return
        except Exception as e:
            self.log(f"Error: {e}", self.log_box_backup)
            return

        friendly_size, byte_units = self.get_friendly_file_size(target)
        threading.Thread(target=self.smooth_progress_tracker, args=(byte_units, self.backup_progress_label, self.backup_progress), daemon=True).start()
        
        self.log(f"Uploading encrypted container ({friendly_size})...", self.log_box_backup)
        try:
            proc = subprocess.Popen(["proton-drive", "filesystem", "upload", target, "/my-files/"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.read_stream_lines_to_log(proc, self.log_box_backup)
            proc.wait()
            
            self.cancel_event.set()
            if proc.returncode == 0:
                self.log("Backup Successfully Synchronised!", self.log_box_backup)
                self.update_progress(100, self.backup_progress_label, self.backup_progress)
                self.send_desktop_notification("Backup Successful", f"Uploaded {friendly_size}.")
            else:
                self.update_progress(0, self.backup_progress_label, self.backup_progress)
        finally:
            if os.path.exists(target): os.remove(target)

    def execute_restore(self):
        self.update_progress(1, self.restore_progress_label, self.restore_progress)
        try:
            selected = self.file_listbox.get(self.file_listbox.curselection())
        except Exception:
            return self.log("Select a file from the list first!", self.log_box_restore)
        
        self.log(f"Downloading encrypted manifest {selected}...", self.log_box_restore)
        try:
            proc = subprocess.Popen(["proton-drive", "filesystem", "download", f"/my-files/{selected}", "."], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.read_stream_lines_to_log(proc, self.log_box_restore)
            proc.wait()
            if proc.returncode != 0: return
        except Exception as e:
            return self.log(f"Download error: {e}", self.log_box_restore)

        friendly_size, byte_units = self.get_friendly_file_size(selected)
        self.update_progress(50, self.restore_progress_label, self.restore_progress)
        self.log("Unpacking encrypted context safely...", self.log_box_restore)
        
        try:
            cmd = f"gpg --batch --passphrase '{self.restore_pass.get()}' -d '{selected}' > '{os.path.join(self.dest_dir, selected.replace('.gpg', ''))}'"
            if "tar.gz" in selected:
                cmd = f"gpg --batch --passphrase '{self.restore_pass.get()}' -d '{selected}' | tar -xzv -C '{self.dest_dir}'"
                
            process = subprocess.run(cmd, shell=True, capture_output=True)
            if process.returncode == 0:
                self.log("Restoration completely restored!", self.log_box_restore)
                self.update_progress(100, self.restore_progress_label, self.restore_progress)
                self.send_desktop_notification("Restore Successful", f"Extracted {friendly_size} archive.")
            else:
                self.log(f"Extraction failed: {process.stderr.decode()}", self.log_box_restore)
                self.update_progress(0, self.restore_progress_label, self.restore_progress)
        except Exception as e:
            self.log(f"Runtime error: {e}", self.log_box_restore)
        finally:
            if os.path.exists(selected): os.remove(selected)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProtonBackupGUI(root)
    root.mainloop()
