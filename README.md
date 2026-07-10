⚠️ **PROJECT STATUS & EXPECTATIONS:** This is a solo development project with occasional contribution from a other collaborators. Testing and debugging are ongoing, and active development time is extremely limited. Please only deploy or use this application if you are capable of auditing and bugfixing the Python source code yourself. We cannot offer technical support, troubleshooting, or real-time assistance.

⚠️ IMPORTANT: UPDATE REQUIRED FOR EXISTING USERS OF (v2.5 Release) The repository history has been completely reset and force-updated to deliver a major Version update and High-Security Overhaul. If you cloned a previous v2.5 version of this tool, your local Git history will conflict with the new clean timeline. To discard the old prototype history and cleanly update to the secure latest version, run the following commands in your local project terminal:

**git fetch --all**

**git reset --hard origin/main**

==============================================================================================

Changelog and Bug Fixes: pduiv3.6.py

This version marks a significant stabilisation of the backup utility, addressing fundamental architectural limitations found in v3.5. It should HOPEFULLY be a lot more stable and work as intended. I have been working on this version for quite some time, but ran into a lot of difficulties getting it stable so kept it back. I need to give the Restore Archive a bit of love, but it’s working fine for me now with a few quirks.

## New Features
[NOTE: This feature is not working currently. I am working to fix this. Not sure it’s possible. If anyone works it out let me know] * Automated Retention Management: Added logic to define and enforce retention counts for remote backups. Old .gpg files are now automatically purged from Proton Drive based on the configured limit.*****

* System Dependency Check: Startup validation now verifies that gpg, tar, zstd, and proton-drive are present and accessible in your system PATH.

* Centralised Config Paths: Migrated configuration and log storage to ~/.config/proton-backup/ to ensure path consistency.

* Passphrase Security Audit: Introduced a mandatory check for passphrase strength, alerting users to security risks before initiating archives.

## Bug Fixes
* Reliable Cancellation: Resolved the "zombie process" issue from v3.5 by implementing an active_procs registry. The "Cancel" button now correctly triggers termination for all associated subprocesses.

* Config Corruption Prevention: Implemented atomic writes using os.replace to prevent configuration data loss during unexpected crashes or power failures.

* UI/Network Responsiveness: Tightened the integration between the "Test Route Link" feature and the UI to provide immediate feedback on API connectivity issues.

Tutorial: Setting Up Your Backup Workflow

Follow these steps to configure pduiv3.6.py for optimal performance.

1. Initial Setup
* Ensure the required binaries (gpg, tar, zstd, proton-drive) are installed on your system.

* Run the script once to generate the directory structure at ~/.config/proton-backup/.

* The script will verify your environment; if any dependency is missing, it will alert you to update your PATH.

2. Configuring Retention and Security

* Open the config.json located in the new configuration folder.

* Define your retention policy by setting the integer value for the number of remote backups to keep per label.

* When prompted for a passphrase, ensure it meets the recommended complexity requirements; the script will provide a warning if the entropy is too low.

3. Executing and Managing Backups
* Start: Initiate a backup through the main UI. The system will perform an atomic write for your configuration state.

* Monitoring: Check ~/.config/proton-backup/pdui.log if you encounter unexpected behavior. The log rotates automatically, maintaining the last 3 files at 2MB each.

* Canceling: If you need to stop a process, simply click "Cancel". The new active_procs registry ensures that all background tasks are terminated immediately.


Note: I only provide my app here, any other download is unathorised and you should be careful.

Many thanks to Gin Mei, "Silver Beauty," for the inspiration, technical guidance, core architecture & logic design collaboration, structural guidance and generally co-developing the app... ...and keeping me up at nights. And also A. D. Cade for recently bringing sanity to my process. Without their help this would not be possible.

