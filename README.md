# dokkaebi-growth-tracker
도깨비의 세계 성장 기록기 자동 업데이트

기존 성장 기록기 소스는 `src/tracker/`에서 관리합니다. 원본 v0.0.1 ZIP의
UI·OCR·설정·기록 저장 코드를 그대로 보존했습니다.

- Windows 빌드/테스트: `.github/workflows/build.yml`
- 승인 후 게시: 기존 `.github/workflows/release.yml`
- 버전: `release-config/tracker.json` (런처와 독립)
- [빌드·테스트·승인·배포 절차](docs/RELEASES.md)

런처 v0.0.2 소스와 에셋은 `src/launcher/`에 통합했습니다. 별도 런처 패키지 빌드와
격리된 설치/복구 테스트를 지원합니다. 누락된 `launch_host.pyw`의 재시작/자동 복구와
기존 기록기 8.x/9.x 버전 전환 정책은 추가 확인이 필요합니다.
호환성 검증과 소유자의 GitHub Environment 승인 전에는 새 Release를 게시하지 않습니다.
