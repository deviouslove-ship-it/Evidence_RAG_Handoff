EVIDENCE RAG - PORTABLE LAN PACKAGE (WINDOWS, OFFLINE)
=======================================================

Language / Ngon ngu: this is the English counterpart of README.txt (the Vietnamese original).

Everything is in this folder: the web interface, the FastAPI server, PostgreSQL + pgvector (database,
indexes, vectors), the original document store, Tesseract OCR for Vietnamese, Ollama and the local AI
models. No Internet needed, and no need to install Python, Node.js, PostgreSQL, Ollama or Tesseract.
Client machines only need a browser.

MACHINE REQUIREMENTS
  - Windows 10 / Windows Server 2016 or later, 64-bit; PowerShell 5.1 (built into Windows).
  - Free space: about 6 GB for the package and data; RAM preferably 8 GB or more (the AI models run on CPU).
  - Extract the WHOLE package into a folder with a short path, for example D:\EvidenceRAG
    (avoid deep folders; keep the path under 120 characters). Do not run directly inside the ZIP file.
  - Administrator rights are not needed to run. They are only needed to open the firewall port (section 4).

1. START
  Double-click  Start-Server.bat  (no other command to type). It runs in turn:
    [1] checks runtime, models, database, network ports, configuration;
    [2] starts the package's own PostgreSQL + pgvector (data in data\postgres);
    [3] starts the package's Ollama (listens on 127.0.0.1 only, models in models\ollama);
    [4] starts the web/API server (FastAPI);
    [5] checks readiness (web, API, embedding model and text-generation model working offline);
    [6] prints the access address through the LAN IP, for example  http://192.168.1.15:8800/
  The FIRST run takes 1-3 more minutes: the package initialises its own database from the original
  data copy (folder seed\), then compares the content of every table with the original before use.
  Data, vectors and indexes are restored as they were: documents are NOT re-imported, NOT re-OCR'd,
  vectors are NOT recreated. Later runs start in a few tens of seconds.
  Running Start-Server.bat again while the server is running does not create a second process.
  If there is an error, the window names the missing or failing component; details are in  logs\launcher.log.

2. USERS ON THE LAN
  Send the address http://<server IP>:8800/ to users; they open it in a browser.
  Accounts, passwords, roles, per-category permissions (ACL) and the audit log are kept as they are in
  the existing system. The package contains NO plaintext passwords: use each account's current password.
  Old login sessions are not carried over; everyone logs in again.

3. STOP
  Double-click  Stop-Server.bat. It stops only the processes started from this folder (web, Ollama,
  PostgreSQL with pg_ctl stop -m fast); it does not affect other PostgreSQL/Ollama/Python on the machine.
  Stop with Stop-Server.bat before shutting down the machine or copying the folder.

4. OPEN THE PORT FOR OTHER MACHINES (WINDOWS FIREWALL)
  The package does not change Windows Firewall by itself. If other machines cannot open the address:
    - Double-click  tools\Allow-LAN-Firewall.bat  and accept the Administrator prompt (once).
      The rule it creates allows only the web port (default 8800), from the local subnet, on
      Private/Domain networks. Remove it with:  tools\Allow-LAN-Firewall.bat remove
    - Or, when Windows asks "allow python.exe to access the network", choose the Private network.
  PostgreSQL (55433) and Ollama (21434) listen on 127.0.0.1 only; they do not need and should not be
  opened to the network.
  The connection is unencrypted HTTP: use it only in a trusted internal network.

5. BACKUP AND RESTORE
  Backup-Data.bat [target folder]
    Backs up the database (including vectors, ACL, audit) with a consistent snapshot and the whole original
    document store, with the SHA-256 of every file. It can run while the server is running. By default it
    writes to backups\backup-<date-time>\. Copy the backup folder to another drive.
  Restore-Data.bat [backup folder]
    Checks backup integrity, shows the contents, asks you to type  KHOI PHUC  to confirm, backs up the
    current data to backups\pre-restore-*, builds a new database, compares every table, and only then
    switches. The old data is kept in data\postgres.before-restore-* (delete by hand when sure). The
    document store is only added to; no file is deleted.
  Never delete the data\ folder or copy over data\postgres while the server is running.

6. MOVE TO ANOTHER MACHINE
  The safest way (independent of the machine's version/CPU):
    a) On the old machine: Backup-Data.bat, then copy the backup folder.
    b) On the new machine: extract the release package, run Start-Server.bat, then Restore-Data.bat <backup folder>.
  The quick way: run Stop-Server.bat, copy the WHOLE folder to the new machine (changing drive, folder or
  machine name is fine: every path is relative and the IP address is detected on each run). If PostgreSQL
  reports incompatibility, use the safe way above; Start-Server.bat never deletes or overwrites data by itself.
  So far the package has been tested running from a different folder/drive on the development machine;
  moving to another physical Windows machine has NOT been verified.

7. CONFIGURATION  (config\evidence.env)
  Bind address, web port, PostgreSQL/Ollama ports, AI mode, limits. After editing, run Stop-Server.bat
  then Start-Server.bat. Change a port if another program occupies it (the error message names the program).
  Model profiles, AI assignment and embedding are edited in Admin Portal > AI Models. The local model
  address in the Registry is synchronised by the launcher with the bundled Ollama port (21434),
  independent of any Ollama already installed on the machine.
  Bundled Local models: see MANIFEST.json (qwen3:1.7b for AI interpretation, search expansion, ranking,
  labelling, relations; qwen3-embedding:0.6b for semantic search).

8. PACKAGE CHECK
  tools\Verify-Package.bat   compares the SHA-256 of every runtime, model, application and original
                             document file with checksums.sha256 of the release (takes a few minutes).
  tools\Status.bat           shows processes, ports, document/vector counts.
  MANIFEST.json              lists the runtime, versions, models, sizes, components.

9. COMMON PROBLEMS
  - "Port ... is used by another program": change the port in config\evidence.env.
  - "Missing component": the package was copied incompletely or antivirus removed files. Extract the
    package again; run tools\Verify-Package.bat to see which file is damaged.
  - A package downloaded over the Internet/email is marked "blocked" by Windows: Start-Server.bat removes
    the mark by itself.
  - Slow AI models: the models run on CPU; the first call after start needs to load the model into RAM.
  - Logs: logs\launcher.log (start/stop), logs\backend.err.log, logs\postgres.log, logs\ollama.err.log.

10. SECURITY
  - Only the web server listens on the LAN; PostgreSQL and Ollama listen on 127.0.0.1 only.
  - The database password is generated randomly by this machine at initialisation and stored in secrets\
    (do not share this folder). API keys (if API mode is used) are DPAPI-encrypted per the Windows account
    running the server.
  - The package contains no API keys, tokens or login sessions.
