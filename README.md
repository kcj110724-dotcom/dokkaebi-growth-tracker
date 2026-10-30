# dokkaebi-growth-tracker

런처 정식 출시와 최초 호스트 전환: [사용자 절차·승인 조건](docs/LAUNCHER_RELEASE_PROCEDURE.md).
도깨비의 세계 성장 기록기 자동 업데이트

기존 성장 기록기 소스는 `src/tracker/`에서 관리합니다. 원본 v0.0.1 ZIP의
UI·OCR·설정·기록 저장 코드를 그대로 보존했습니다.

- Windows 빌드/테스트: `.github/workflows/build.yml`
- 승인 후 게시: 기존 `.github/workflows/release.yml`
- 버전: `release-config/tracker.json` (런처와 독립)
- [빌드·테스트·승인·배포 절차](docs/RELEASES.md)

런처 v0.0.2 소스와 에셋은 `src/launcher/`에 통합했습니다. 별도 런처 패키지 빌드와
격리된 설치/복구 테스트를 지원합니다. 호스트 모듈 충돌, 8.x/9.x → 0.x 전환,
v 접두사 설치 폴더 호환성을 수정했습니다. 실제 설치에는 아직 적용하지 않았습니다.
[수정 정책과 검증 결과](docs/COMPATIBILITY_FIXES.md)를 확인하세요.
호환성 검증과 소유자의 GitHub Environment 승인 전에는 새 Release를 게시하지 않습니다.
