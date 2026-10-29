# dokkaebi-growth-tracker
도깨비의 세계 성장 기록기 자동 업데이트

기존 성장 기록기 소스는 `src/tracker/`에서 관리합니다. 원본 v0.0.1 ZIP의
UI·OCR·설정·기록 저장 코드를 그대로 보존했습니다.

- Windows 빌드/테스트: `.github/workflows/build.yml`
- 승인 후 게시: 기존 `.github/workflows/release.yml`
- 버전: `release-config/tracker.json` (런처와 독립)
- [빌드·테스트·승인·배포 절차](docs/RELEASES.md)

최신 런처 v0.0.2 소스가 없어 런처 빌드와 실제 업데이트/롤백 검증은 대기 중입니다.
호환성 검증과 소유자의 GitHub Environment 승인 전에는 새 Release를 게시하지 않습니다.
