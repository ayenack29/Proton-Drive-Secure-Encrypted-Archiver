#!/usr/bin/env python3
import os
import subprocess
import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CACHE_DIR = os.path.expanduser("~/.cache/proton_backup")

class ProtonBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure Proton Drive Backup Utility")
        self.root.geometry("1280x1280")
        self.root.resizable(True, True)
        
        self.is_fullscreen = False
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.selected_directory = ""
        self.active_process = None  
        self.cancel_event = threading.Event()  
        
        self.animation_frames = [
            "🦝 (swiping your data...)", 
            "💼 (packing the bag...)", 
            "🚀 (launching to Switzerland...)", 
            "✨ (encryption magic complete!)"
        ]
        self.current_frame_idx = 0
        
        self.create_main_widgets()
        self.animate_header()

    def create_main_widgets(self):
        main_frame = ttk.Frame(self.root, padding="25")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = ttk.Label(main_frame, text="Proton Drive Secure Encrypted Archiver", font=("Helvetica", 22, "bold"))
        self.title_label.pack(pady=(0, 2))
        
        self.anim_label = ttk.Label(main_frame, text="", font=("Helvetica", 12, "italic"), foreground="#2196F3")
        self.anim_label.pack(pady=(0, 10))
        
        hint_label = ttk.Label(main_frame, text="Press [F11] to toggle Full Screen | Press [Esc] to exit Full Screen", font=("Helvetica", 10, "italic"), foreground="gray")
        hint_label.pack(pady=(0, 15))

        # --- SECTION 1: TARGET DIRECTORY ---
        dir_lf = ttk.LabelFrame(main_frame, text=" 1. Select Source Folder ", padding="12")
        dir_lf.pack(fill=tk.X, pady=5)

        self.dir_label = ttk.Label(dir_lf, text="No folder selected.", font=("Helvetica", 11, "italic"))
        self.dir_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(dir_lf, text="Browse Folder", command=self.browse_folder)
        browse_btn.pack(side=tk.RIGHT, padx=10)

        # --- SECTION 2: NAMING SYSTEM ---
        name_lf = ttk.LabelFrame(main_frame, text=" 2. Archive Naming System ", padding="12")
        name_lf.pack(fill=tk.X, pady=5)

        ttk.Label(name_lf, text="Backup Label Prefix (e.g., Documents, Pictures, VIVO):").pack(anchor=tk.W, padx=10, pady=2)
        self.name_entry = ttk.Entry(name_lf, font=("Helvetica", 11))
        self.name_entry.pack(fill=tk.X, padx=10, pady=5)
        self.name_entry.insert(0, "My-Backup")

        # --- SECTION 3: PASSWORD SECURE VERIFICATION ---
        crypto_lf = ttk.LabelFrame(main_frame, text=" 3. Symmetric Encryption Passphrase ", padding="12")
        crypto_lf.pack(fill=tk.X, pady=5)

        ttk.Label(crypto_lf, text="Enter GPG Encryption Passphrase:").pack(anchor=tk.W, padx=10, pady=2)
        self.pwd_entry1 = ttk.Entry(crypto_lf, show="*", font=("Helvetica", 11))
        self.pwd_entry1.pack(fill=tk.X, padx=10, pady=4)

        ttk.Label(crypto_lf, text="Confirm GPG Encryption Passphrase:").pack(anchor=tk.W, padx=10, pady=2)
        self.pwd_entry2 = ttk.Entry(crypto_lf, show="*", font=("Helvetica", 11))
        self.pwd_entry2.pack(fill=tk.X, padx=10, pady=4)

        # --- SECTION 4: LIVE TERMINAL MONITOR ---
        terminal_lf = ttk.LabelFrame(main_frame, text=" 4. Live Terminal Activity Output Monitor ", padding="10")
        terminal_lf.pack(fill=tk.BOTH, expand=True, pady=5)

        self.terminal_box = tk.Text(terminal_lf, bg="#1e1e1e", fg="#00ff00", insertbackground="white", font=("Courier", 10), state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(terminal_lf, command=self.terminal_box.yview)
        self.terminal_box.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.terminal_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- BUTTON EXECUTION CONTROL GRID ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)

        self.run_btn = ttk.Button(btn_frame, text="Begin Packaging & Upload", command=self.start_thread)
        self.run_btn.pack(side=tk.LEFT, padx=10, ipady=5, ipadx=15)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancel Backup Process", command=self.trigger_cancellation, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.RIGHT, padx=10, ipady=5, ipadx=15)

    def animate_header(self):
        if hasattr(self, 'anim_label') and self.anim_label.winfo_exists():
            current_text = self.animation_frames[self.current_frame_idx]
            self.anim_label.config(text=current_text)
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.animation_frames)
            self.root.after(1200, self.animate_header)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        return "break"

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)
        return "break"

    def log_to_terminal(self, text):
        self.terminal_box.config(state=tk.NORMAL)
        self.terminal_box.insert(tk.END, text + "\n")
        self.terminal_box.see(tk.END)
        self.terminal_box.config(state=tk.DISABLED)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_directory = folder
            self.dir_label.config(text=folder, font=("Helvetica", 11, "normal"))

    def start_thread(self):
        if not self.selected_directory:
            messagebox.showerror("Validation Error", "Please select a local source folder to back up.")
            return

        pass1 = self.pwd_entry1.get()
        pass2 = self.pwd_entry2.get()

        if not pass1 or not pass2:
            messagebox.showerror("Validation Error", "Encryption passphrase fields cannot be blank.")
            return

        if pass1 != pass2:
            messagebox.showerror("Security Error", "Passphrases do not match! Please verify your password entry.")
            return

        self.run_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        
        self.cancel_event.clear()
        self.active_process = None

        worker = threading.Thread(target=self.execute_backup_pipeline, args=(pass1,))
        worker.daemon = True
        worker.start()

    def trigger_cancellation(self):
        if messagebox.askyesno("Cancel Confirmation", "Are you sure you want to stop the active packaging and cloud stream?"):
            self.log_to_terminal("\n[USER ACTION]: Termination signal caught. Spinning down subprocess handlers...")
            self.cancel_event.set()
            
            if self.active_process:
                try:
                    self.active_process.terminate()
                    self.active_process.kill()
                except Exception:
                    pass

    def execute_backup_pipeline(self, passphrase):
        prefix = self.name_entry.get().strip().replace(" ", "_")
        if not prefix:
            prefix = "Backup"
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        archive_name = f"{prefix}_{timestamp}.tar.gz"
        gpg_name = f"{archive_name}.gpg"
        
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp_archive_path = os.path.join(CACHE_DIR, archive_name)
        tmp_gpg_path = os.path.join(CACHE_DIR, gpg_name)

        try:
            if self.cancel_event.is_set(): raise InterruptedError
            
            # STEP A: Tar compression pack phase
            self.log_to_terminal(f"[SYSTEM]: Initializing monolithic Tar packing structure for {self.selected_directory}...")
            parent_dir = os.path.dirname(self.selected_directory)
            target_base = os.path.basename(self.selected_directory)
            
            self.active_process = subprocess.Popen([
                "tar", "-czf", tmp_archive_path, 
                "--ignore-failed-read", 
                "-C", parent_dir, target_base
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            while True:
                line = self.active_process.stdout.readline()
                if not line and self.active_process.poll() is not None:
                    break
                if line:
                    self.log_to_terminal(f"  [tar]: {line.strip()}")
            
            self.active_process.wait()
            
            if not os.path.exists(tmp_archive_path) or os.path.getsize(tmp_archive_path) == 0:
                raise RuntimeError("Tar compression failed to create any valid backup archive payload file.")
            
            if self.cancel_event.is_set(): raise InterruptedError
            self.log_to_terminal(f"[SYSTEM]: Tarball packaging successfully handled -> {archive_name}")

            # STEP B: Symmetric GPG secure locking pass
            self.log_to_terminal("[SYSTEM]: Processing strong AES-256 local client payload encryption via GPG...")
            self.active_process = subprocess.Popen([
                "gpg", "--batch", "--yes", "--symmetric", "--pinentry-mode", "loopback",
                "--passphrase", passphrase, "-o", tmp_gpg_path, tmp_archive_path
            ])
            self.active_process.wait()
            
            if self.active_process.returncode != 0:
                raise RuntimeError("GPG encryption failed.")
            
            if self.cancel_event.is_set(): raise InterruptedError
            self.log_to_terminal(f"[SYSTEM]: GPG layer fully locked -> {gpg_name}")

            if os.path.exists(tmp_archive_path):
                os.remove(tmp_archive_path)

            # STEP C: Direct Upload Stream to Base Root Area
            self.log_to_terminal("[SYSTEM]: Streaming payload archive directly to Proton Drive root...")
            self.active_process = subprocess.Popen([
                "proton-drive", "filesystem", "upload", 
                tmp_gpg_path, "/my-files", "--conflict-strategy", "replace"
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            while True:
                if self.cancel_event.is_set():
                    break
                line = self.active_process.stdout.readline()
                if not line and self.active_process.poll() is not None:
                    break
                if line:
                    self.log_to_terminal(line.strip())

            self.active_process.wait()
            if self.cancel_event.is_set(): raise InterruptedError

            if self.active_process.returncode == 0:
                self.log_to_terminal(f"[SUCCESS]: Transfer finalized successfully! Target saved as {gpg_name}")
                messagebox.showinfo("Success", f"Backup completed successfully:\n{gpg_name}")
            else:
                self.log_to_terminal("[ERROR]: Proton Drive CLI rejected the binary upload target stream.")
                messagebox.showerror("Cloud Sync Error", "Proton Drive rejected or dropped the upload target stream.")

        except (InterruptedError, tk.TclError):
            self.log_to_terminal("[HALTED]: Execution pipeline successfully stopped by user request.")
            messagebox.showwarning("Cancelled", "The current backup run has been stopped.")
        except Exception as e:
            self.log_to_terminal(f"[CRITICAL FAILURE]: Pipeline processing crash logic triggered:\n{str(e)}")
            messagebox.showerror("Pipeline Execution Error", f"An internal process failure occurred:\n{str(e)}")
        
        finally:
            for path in [tmp_archive_path, tmp_gpg_path]:
                if os.path.exists(path):
                    try: os.remove(path)
                    except Exception: pass
            
            self.run_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProtonBackupGUI(root)
    root.mainloop()
