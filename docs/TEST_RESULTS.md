# 배포 시스템 검증 기록

검증일: 2026-10-29 (Asia/Seoul). 작업 브랜치: `codex/approved-windows-releases`.

## 로컬 Windows / Python 3.12.10

- `python -m unittest discover -s tests -v`: **28개 통과**.
- 기존 ZIP 내부 소스/리소스 17개와 `src/tracker/`가 바이트 단위로 동일함.
- 원본 ZIP과 새 ZIP 모두 manifest schema 1 및 내부 SHA-256 검증 통과.
- 동일 입력을 두 번 빌드한 ZIP이 바이트 단위로 동일함.
- private config/user_data가 소스 폴더에 있어도 패키지에서 제외되고 원본은 보존됨.
- UTF-8 BOM CSV 호환성 확인, 변조·경로 탈출·Windows 예약 이름·심볼릭 링크·
  대소문자 중복·ZIP 용량/개수 초과 거부 확인.
- 미승인 요청, 잘못된 빌드 출처, 누락된 승인 리뷰어, 미검증 런처 호환성 차단 확인.
- 게시 명령은 mock으로 검증: 정확한 SHA의 태그 생성, 기존 태그 충돌 중단,
  업로드 실패 시 공개 전환 차단. 원격 Release 생성 명령은 실행하지 않음.
- `python scripts/smoke_tracker.py dist/tracker/dokkaebi-app.zip`: **통과**.
  빌드된 ZIP에서 대시보드·능력치·전투력 기록·측정 도구·설정 화면을 숨긴 Tk 창에
  렌더링하고 측정 센터의 원본 모듈 체인을 import함.
  임시 CSV/JSON/config 바이트 보존 확인. 실제 사용자 데이터·게임 화면 접근 없음.
- Python 구문 검사와 `git diff --check`: 통과.

로컬 ZIP SHA-256:

```text
ec21160a83ff5e25aecfd384760531ee44b6adb56d226ce280233cfffc45368c
```

ZIP은 검토용 v0.0.1 재패키징이며 새 버전 승인이나 Release가 아니다.
기존 v0.0.1 패키지와 파일 내용은 같지만 ZIP 직렬화/manifest 순서가 달라 전체 ZIP 해시는 다르다.
게시할 때는 로컬 해시를 복사하지 않고 성공한 GitHub Windows 빌드의 `build-info.json`을 사용한다.

## GitHub Actions 및 실제 설치

원격 Windows CI 결과는 해당 작업 브랜치의 Actions 실행에서 확인한다.
로컬 테스트 통과는 GitHub 호스팅 runner의 성공을 대신하지 않는다.
main 병합, production-release 환경 설정, 태그 생성, 실제 Release 게시를 수행하지 않았다.

미검증 항목: 실제 런처 v0.0.2의 버전 감지, 런타임/의존성 설치,
다운로드 SHA 검증, 파일 교체 실패 복구, 프로세스 재실행, 기존 설치 데이터 보존,
게임 화면 캡처/OCR. 런처 소스와 비식별 설치 구조 예시가 필요하다.

## 변경 파일

- `.gitattributes`, `.gitignore`: 원본 바이트/빌드 산출물/사용자 데이터 관리
- `.github/workflows/build.yml`: Windows 자동 테스트·패키징·artifact
- `.github/workflows/release.yml`: 기존 게시 흐름을 owner 승인/검증 artifact 방식으로 전환
- `scripts/prepare_release.py`: 기존 검증 재사용 및 데이터/Windows ZIP 검사 강화
- `scripts/build_package.py`: 원본 형식의 결정적 소스 ZIP 생성
- `scripts/release_gate.py`: 승인·커밋·CI 출처·런처 증빙 검사
- `scripts/publish_release.py`: 고정 SHA 태그와 draft→업로드→공개 순서
- `scripts/smoke_tracker.py`: 패키지 UI·데이터 격리 smoke test
- `tests/test_distribution.py`: 28개 자동 테스트
- `release-config/tracker.json`, `release-config/compatibility.json`: 독립 버전과 게시 차단 상태
- `release-requests/template.json`: 미승인 상태의 요청 양식
- `src/tracker/` 17개 파일: 원본 소스/리소스 그대로 추가
- `README.md`, `docs/RELEASES.md`, `docs/TEST_RESULTS.md`: 절차·제약·검증 기록

기존 두 ZIP, `release-payloads`, 과거 승인 요청, 실제 사용자 기록은 변경하지 않았다.
