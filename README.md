⚠️ **PROJECT STATUS & EXPECTATIONS:** This is a solo development project with occasional contribution from a single collaborator. Testing and debugging are ongoing, and active development time is extremely limited. Please only deploy or use this application if you are capable of auditing and bugfixing the Python source code yourself. We cannot offer technical support, troubleshooting, or real-time assistance.

⚠️ IMPORTANT: UPDATE REQUIRED FOR EXISTING USERS OF (v2.5 Release) The repository history has been completely reset and force-updated to deliver a major Version 3.0 High-Security Overhaul. If you cloned a previous version of this tool, your local Git history will conflict with the new clean timeline. To discard the old prototype history and cleanly update to the secure v3.0 production branch, run the following commands in your local project terminal:

**git fetch --all**

**git reset --hard origin/main**




📋 **1. Official Changelog (v3.0)**

🔒 **Cryptography & Process Hardening**

***Implemented PBKDF2-HMAC-SHA256 Master Gate:*** 
Replaced the previous basic password check with an industry-standard key derivation function. Local dashboard access is now enforced via a cryptographically salted master password utilizing 100,000 iterations to completely halt brute-force parsing.

***Eliminated Plaintext Passphrase Caching:*** Completely removed the plain-text credential storage loop. Individual file-encryption keys are now held strictly within volatile system memory (RAM) and are automatically scrubbed immediately post-execution.

***Process Tree Hardening:*** Eliminated all unsafe shell script pipelines (shell=True). System actions are now executed as structured array commands, and passwords are fed directly into GPG via protected standard input (stdin) memory pipes (--passphrase-fd 0), preventing local process eavesdropping.

⏱️ **File Synchronization & Precision Logging**

***Precision Time-Stamping:*** Appended dynamic hour and minute markers (_%H%M) to file outputs. This prevents remote cloud collisions, ensuring back-to-back backup packages uploaded on the same day sit comfortably side-by-side without naming conflicts.

***Resolved Deselect Freeze:*** Patched a critical Tkinter layout bug where switching focus away from the cloud file listbox triggered an uncaught index failure.

***Display Layout Refactor:*** Standardised target desktop dimensions to 1920x1080 to guarantee clean visual mapping across standard or lower-resolution displays. (Note: I may introduce a Low-Res switch button for very old hardware to switch down to an even lower res display.)



🛡️ **2. The "Why":**  ***Reasons for the Structural Changes***

As an open-source tool built around absolute privacy, the core code needed to meet modern cryptographic standards before scaling to a wider user base.

🚀 **3. Updated User Walkthrough**

1: ***Initialize the Master Gate***

Open your terminal inside the application folder and run:

**python3 pdui.py**

2, On your first v3.0 launch, the app detects an empty configuration and opens the Master Vault Security Initialisation panel.

3, Type a strong master password twice and click Create Cryptographic Hash & Lock.(Note: This creates a mathematically salted signature in your config file. It keeps bad actors out of your UI, but it cannot be recovered if forgotten!)

**Step 2: Running a Secure Cloud Backup**

1, Input your newly created Master Password to unlock the main application dashboard.

2, Click Browse Folder or Browse Files to select the target data.

3, Choose or type a Backup Label Profile (e.g., Documents-Backup).

4, Type your private GPG Encryption Passphrase into the boxes.(Crucial: This is the local passphrase that locks your file before it leaves your machine. It is completely independent of your Proton Drive login).

5, Click Begin Backup. The app compresses the target, safely pipes it through local GPG encryption, and securely streams it up to your Proton Drive folder.

**Step 3: Activating the App Lock Screen**

1, If you need to step away from your desk while the application window is open, click the 🔒 Lock App Screen button at the top of either tab.

2, The dashboard instantly unloads from active layout memory, forcing anyone approaching your desk to provide the Master Password before allowing access to any controls or cloud maps.

**Step 4: Restoring an Archive**

1, Navigate to the Restore Archive tab.

2, Click Refresh Cloud List to fetch your available secure manifests directly from your cloud storage.

3, Select an archive from the list and click Select Destination Folder to choose where the files should extract.

4, Provide your private GPG Passphrase into the box and click Start Restore. The script downloads the package, decrypts it locally in temporary memory, and unpacks the target directories completely clean.

Please go to releases for the tutorial and info, pictures of the app etc.  

Note: I only provide my app here, any other download is unathorised and you should be careful.

Many thanks to Gin Mei, "Silver Beauty," for the inspiration, technical guidance, core architecture & logic design collaboration, structural guidance and generally co-developing the app... ...and keeping me up at nights.

