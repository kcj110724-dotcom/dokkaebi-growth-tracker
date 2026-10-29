# 승인 기반 Windows 배포

> 런처 통합 후 최신 상태는 [LAUNCHER_INTEGRATION.md](LAUNCHER_INTEGRATION.md)를 참조한다.
> 아래 초기 구축 기록 중 런처 소스/빌드가 없다는 설명은 해당 문서로 대체된다.
> 승인 환경과 게시 차단 정책은 계속 적용한다.

## 구현 범위와 현재 차단 조건

기존 `.github/workflows/release.yml`, `scripts/prepare_release.py`,
`tracker-vX.Y.Z` / `launcher-vX.Y.Z` 태그와 ZIP·SHA-256 첨부 방식을 재사용한다.
과거 `release-payloads`와 승인 요청은 변경하지 않았다. 새 게시 워크플로는
과거 staged ZIP을 게시하지 않고 성공한 Windows 소스 빌드의 artifact만 받는다.

성장 기록기 소스 17개는 기존 v0.0.1 ZIP에서 바이트 그대로 옮겼다.
UI, OCR, CSV/JSON 저장 코드, 이미지, requirements는 변경하지 않았다.
`manifest.json` + `app/` 구조, schema 1, `tracker.py` 진입점을 유지한다.
이 패키지는 기존 Python 런처용 Windows 배포 ZIP이다. 독립 EXE, Python 설치기,
Tesseract 설치기는 만들지 않는다. 기존 런처의 실행 환경 계약을 확인해야 한다.

**런처 v0.0.2 소스가 없으므로 런처 빌드·설치·자동 감지·복구는 아직 미구현/미검증이다.**
`--component launcher`는 명시적으로 실패한다. 임의의 런처로 대체하지 않는다.
`release-config/compatibility.json`은 `pending`이며 모든 실제 Release 게시를 막는다.
소스를 받은 후 별도 `release-config/launcher.json`, 전용 파일 목록·manifest 검증·
Windows 빌드 작업을 실제 런처 계약에 맞게 추가한다. tracker 버전과 연동해 올리지 않는다.

## 로컬 테스트 및 빌드

Python 3.12에서 저장소 루트 기준:

```powershell
python -m unittest discover -s tests -v
python scripts/build_package.py --source-sha <검토한-40자리-커밋-SHA>
python -m pip install -r src/tracker/requirements.txt
python scripts/smoke_tracker.py dist/tracker/dokkaebi-app.zip
```

`dist/tracker/`에 ZIP, `.sha256`, `build-info.json`이 생긴다.
실제 커밋에 없는 작업 파일을 빌드한 경우 해당 결과를 게시용 증빙으로 사용하지 않는다.
테스트용 단축 SHA나 브랜치 이름은 허용하지 않는다.
ZIP 파일명·파일 내용·시간·권한·순서를 고정해 같은 Python/zlib 환경에서 재현 가능하다.
운영체제/압축 라이브러리 차이가 있을 수 있으므로 게시 시 로컬에서 재빌드하지 않는다.

패키징은 명시적인 17개 파일 목록만 사용한다. config, CSV, 로그, user_data,
사용자 배경은 포함하지 않는다. 제품에 새 파일을 추가하면 파일 목록과 검증을 검토한다.
기존 requirements의 `>=` 범위는 호환성 유지를 위해 그대로이며 CI가 설치 버전을 기록한다.
완전한 의존성 재현을 위해서는 실제 런처 환경을 확인한 후 검증된 버전 고정이 추가로 필요하다.

## GitHub 빌드와 승인 순서

1. `codex/**` 작업 브랜치에 변경을 push한다. `build.yml`은 Windows에서 테스트,
   의존성 설치, 소스 ZIP 생성, 대시보드 5개 화면 렌더링, 측정 모듈 import를 수행한다.
   실제 화면 캡처/OCR, 게임 실행, 실제 사용자 폴더 접근은 하지 않는다.
2. Actions Summary와 `windows-tracker-<SHA>` artifact를 검토한다.
   `build-info.json`에는 버전·커밋 SHA·ZIP SHA-256이 있다. artifact 보관 기간은 30일이다.
3. 사용자가 변경을 승인한 뒤에만 main에 병합한다. 병합은 자동으로 수행하지 않는다.
   squash/rebase는 SHA를 바꾸므로 **main에서 성공한 새 빌드**를 게시 후보로 사용한다.
4. 실제 런처 통합 테스트를 완료하고, 비식별 테스트 결과 파일을 저장소에 추가한다.
   `release-config/compatibility.json`의 `status`를 `verified`, `evidence`를 해당 파일 경로로
   변경한다. 실제 결과 없이 이 값을 변경하지 않는다.
5. `release-requests/template.json`을 새 요청 파일로 복사한다. 버전·태그·성공한 빌드
   실행 ID·정확한 source_sha·ZIP sha256·변경 내역·latest 정책을 작성한다.
   사용자가 해당 패키지를 승인한 뒤에만 `approved: true`로 변경한다.
   이 메타데이터 변경도 검토 후 main에 반영한다. 소스 SHA는 패키지를 만든 커밋이다.
6. `Dokkaebi approved release`를 main에서 수동 실행하고 요청 파일 경로를 입력한다.
   push, PR, 태그 생성만으로 게시되지 않는다.
7. `production-release` Environment에서 저장소 소유자가 **Review deployments → Approve**를
   수행하면 GitHub Actions가 검증된 artifact를 그대로 게시한다. 승인 전 재빌드·게시하지 않는다.

다른 run, 실패한 빌드, PR 병합 가상 커밋, fork 빌드, main 이력 밖 커밋, SHA 불일치,
만료된 artifact, 누락된 승인 환경은 게시할 수 없다. 빌드가 만료되면 새 빌드를 검토·승인한다.
릴리스 버전은 `release-config/tracker.json`과 제품 버전 표기를 함께 검토해 변경한다.
현재 0.0.1은 원본 보존용이다. 이미 게시된 `tracker-v0.0.1`은 다시 게시할 수 없다.

## 필수 GitHub 설정

저장소 Settings → Environments에서 `production-release`를 만든다.

- Required reviewers: **kcj110724-dotcom 한 명만** 지정한다. GitHub는 여러 리뷰어 중
  한 명의 승인으로 진행하므로 다른 사람/팀을 함께 넣지 않는다.
- 소유자가 수동 실행하고 직접 승인하려면 Prevent self-review는 끈다.
- Deployment branches는 main으로 제한하고 관리자 우회 허용은 끄는 것을 권장한다.
- main 브랜치에는 PR 검토와 `tracker` Windows 빌드 성공을 필수로 설정한다.
- Actions 실행과 `GITHUB_TOKEN`의 게시 작업 `contents: write`가 허용되어야 한다.

환경을 설정하지 않거나 리뷰어가 다르면 preflight가 실패한다. 워크플로에서 환경 이름만
선언하는 것으로 승인 보호가 설정되는 것은 아니므로 API로 실제 required reviewers를 확인한다.
환경 설정에는 저장소 Administration write 권한이 필요하며 연결된 GitHub 도구에는 해당
설정 기능이 없다. 비밀 토큰을 소스에 넣거나 PAT를 추가할 필요는 없다.

## 게시 실패 시 처리

승인 후 태그를 검토한 소스 SHA에 원자적으로 생성한다. 기존 태그가 있으면 중단한다.
Release는 먼저 draft로 만들고 ZIP·SHA-256 업로드가 모두 성공한 뒤 공개한다.
업로드 실패 시 공개 전환하지 않는다. 태그 또는 draft가 남을 수 있으므로 실패 로그를
확인하고 소유자가 복구 방법을 결정한다. 자동 삭제·덮어쓰기·태그 이동은 하지 않는다.

이 복구는 **게시 실패 처리**이다. **사용자 PC 설치 실패 시 롤백**은 실제 런처 소스가
필요하다. 확인 전에는 완료했다고 판단하지 않는다.

## 기존 런처 통합에 필요한 파일과 검증

필요한 자료:

- 최신 런처 v0.0.2 전체 소스와 requirements/빌드 설정/진입점
- GitHub API 조회·태그/버전 비교·asset 선택·SHA 검증 코드
- 설치 경로, 버전 교체, 프로세스 종료/재실행, 실패 시 복구 코드
- 현재 설치 폴더 구조 예시(개인 기록 대신 파일명·경로만)
- 기존 업데이트 manifest/설정 예시(토큰·개인정보 제거)

실제 런처로 다음을 검증하고 증빙을 남긴다:

- `v9.0.0` → `tracker-vX.Y.Z` 버전 체계와 component별 비교가 정확한지
- latest 한 개를 쓰는지, Release 목록을 태그별로 필터링하는지
- tracker/launcher가 상대 구성요소의 Release를 잘못 선택하지 않는지
- ZIP 외부 SHA와 내부 manifest 검증 후 설치하는지, 불일치 시 기존 설치가 유지되는지
- 내려받기 중단/손상/잠긴 파일/설치 중 예외/재실행 실패 시 이전 버전으로 복구하는지
- 성공/실패 모두 CSV·JSON·설정·사용자 배경이 바이트 단위로 유지되는지
- 대시보드 → 측정 센터에 데이터 경로가 전달되고 기존 기록이 계속 표시되는지

`latest`는 요청마다 명시한다. 기존 런처가 `/releases/latest`를 사용한다면 실제 호환성을
검증한 tracker Release만 latest로 지정해야 한다. launcher Release가 이를 가로채면 안 된다.
manifest schema, 자산 이름과 SHA 파일은 유지했지만, 이것만으로 자동 감지 성공을 보장하지 않는다.
사용자 데이터 저장 방식은 변경하지 않았다. 런처가 `DOKKAEBI_DATA_DIR`와
`DOKKAEBI_ASSETS_DIR`를 고정 경로로 설정하는지 확인하기 전에는 설치 폴더를 교체하지 않는다.

## 참고

- [GitHub Environment 승인 및 API 권한](https://docs.github.com/en/rest/deployments/environments)
- [빌드 artifact 다운로드](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
