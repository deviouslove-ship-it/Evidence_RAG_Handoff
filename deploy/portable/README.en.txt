Language / Ngon ngu: Tieng Viet in README.txt · English
English counterpart of deploy/portable/README.txt. The Vietnamese file is the original.

EVIDENCE RAG - PORTABLE RUN (no installation required)
======================================================

Machine requirements
  - Windows 10 / Windows Server 2016 or later, 64-bit. Python, PostgreSQL, and Node do not need to be installed.
  - Administrator rights are not required (they are needed only when opening the firewall; see section 4).
  - About 2 GB free for the package + data. Prefer a folder whose path has no diacritics
    and is not too long, for example D:\EvidenceRAG (a path with spaces still runs).

1. Run
  - Copy this whole folder to the machine that should run it (keep the structure), open the folder, and double-click
    start.cmd.
  - First run: it creates an empty database by itself (takes a few tens of seconds), then prints the password of the 4
    bootstrap accounts and saves it at secrets\first-login.txt. Each account is forced to change its password on
    the first login. After the change, delete the file first-login.txt.
  - At the end of start, the program prints addresses of the form http://<IP-máy-này>:8000/ (http://<this-machine-IP>:8000/). Give that
    address to users on the same network so they can open it in a browser. The address is discovered at run time and is not
    hardcoded.

2. Bootstrap accounts (the same initial password)
  admin       system administration, catalogs, accounts, AI configuration, audit log
  curator     load PDFs, create and submit drafts
  reviewer    appraise and approve administrative documents (văn bản); someone other than curator
  chuyenvien  question answering and search
  The system has no approved administrative document yet: question answering and search return results only after curator
  loads a PDF and reviewer approves it (and a catalog is attached for the user).

3. Stop / view status
  stop.cmd     stops the web server and the database (data stays in the data folder)
  status.cmd   shows whether it is running and the access addresses

4. Let other machines on the network reach it
  - If another machine cannot open the address: right-click open-firewall.cmd > Run as
    administrator (run it once). The rule allows only the same subnet and
    Private/Domain networks. Remove it with close-firewall.cmd (Administrator is also required).
  - Use it only on a trusted network: the connection is HTTP and is not encrypted.
  - To allow only this machine to reach it: set EVIDENCE_LISTEN_HOST=127.0.0.1 in config\evidence.env.

5. Configuration
  config\evidence.env: listen address, port, AI mode (LOCAL/API), limits. After editing,
  run stop.cmd and then start.cmd. AI model profiles are configured in the Admin Portal; set the API key according to
  the instructions in evidence.env (the key is not stored in the database).

5a. Change or upgrade the embedding model (search by meaning) - no command and no code edit required
  - Admin Portal > Mô hình AI (AI models) > 1. Hồ sơ Mô hình (1. Model profiles): select the role "Tạo vector (embedding)" (Create vectors (embedding)),
    enter the service address (an OpenAI-compatible API, for example a model server running on this machine),
    the model name, then approve and save.
  - Section "Embedding (tìm theo nghĩa)" (Embedding (search by meaning)): select the profile > Kiểm tra model (Check model) (connection, model, number of dimensions,
    data policy, number of nodes to create) > confirm. Vector creation runs in the background on the server,
    with progress, pause / resume / retry, and continues by itself after a restart (about 1
    minute after the server is up).
  - While creation is running, search still uses the old model and the old index. When it finishes, the system checks
    integrity and only then switches; if there is an error it keeps the old index. The old index and the old vectors are kept.
  - There is no need to import PDF/Word/TXT again: vectors are created from the approved Articles (Điều) / Clauses (Khoản) / Points (Điểm).

6. Backup and moving to another machine
  - Data is in data\ (the database + the PDF store) and secrets\ (the DB password).
  - Stop with stop.cmd, then copy the whole folder. To move to a new machine but KEEP the data:
    copy the folder intact. To start CLEAN: copy the folder but delete data\, secrets\, logs\,
    run\, cache\ before running.
  - secrets\ contains the database password: do not share this folder.

7. If something goes wrong
  - See logs\backend.err.log, logs\postgres.log, and logs\seed.err.log.
  - If it reports "port in use": change EVIDENCE_HTTP_PORT or EVIDENCE_PG_PORT in config\evidence.env.
  - If antivirus software blocks it: allow the runtime\ folder to run.
  - A package downloaded from the internet or from email is blocked by Windows (SmartScreen, "blocked"): open PowerShell in
    the package folder and run: Get-ChildItem -Recurse | Unblock-File . Copying via a USB drive or an internal network is
    not blocked.
  - A very old machine reports a missing DLL "api-ms-win-crt": install the Windows Universal C Runtime
    update (Windows 10 / Server 2016 and later already include it).

AI MODELS AND API KEYS (Admin Portal > Mô hình AI & Kiểm toán (AI models & audit))
- 1. Mô hình AI (AI models): separate forms for AI Local and AI API; "Kiểm tra kết nối" (Test connection) tests the
  connection and the model before saving. 2. Phân công AI (AI assignment): assign a model to each function.
- An API key typed in the AI API form is stored encrypted (Windows DPAPI, bound to the
  Windows account running the server) in secrets\ai-keys; it is never shown again. If the
  server account changes, enter the keys again. Back up secrets\ai-keys with the data only
  if the same account will restore it.
- The typed key travels to the server over HTTP; on a LAN without TLS prefer env:NAME
  (Nâng cao) (Advanced) or use the form on the server machine itself.

OCR FOR SCANNED PDF (optional, not included)
- Copy Tesseract 5 (tesseract.exe, its DLLs and tessdata with vie, eng, osd) to
  runtime\tesseract\ and restart; or set EVIDENCE_OCR_EXECUTABLE in config\evidence.env.
- It runs offline. OCR text becomes evidence only after a reviewer confirms each page
  against the scan in Admin Portal > Duyệt nguồn (Review source). The scan itself stays the original.
