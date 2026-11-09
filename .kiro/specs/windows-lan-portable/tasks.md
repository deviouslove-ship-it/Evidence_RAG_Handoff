# Tasks: Windows LAN Portable

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. Launcher scripts and batch entry points (`deploy/lan-portable/*`)
- [x] 2. Seed-based first run, table comparison (`tools/portable.ps1`)
- [x] 3. Backup and guarded restore (`Backup-Data.bat`, `Restore-Data.bat`)
- [x] 4. Firewall helper with remove option (`tools/Allow-LAN-Firewall.bat`)
- [x] 5. Package verification and status tools (`Verify-Package.bat`, `Status.bat`)
- [x] 6. Builder (`scripts/build-lan-portable.ps1`)
- [x] 7. Operator guide in Vietnamese (`README.txt`) and English (`README.en.txt`)
- [x] 8. Simpler single-folder package (`deploy/portable/`, `scripts/package-portable.ps1`)
- [ ] 9. Test on a second physical Windows machine (not done)
- [ ] 10. Windows service wrapper and TLS (not present)
