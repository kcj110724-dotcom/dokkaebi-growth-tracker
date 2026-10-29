# 호스트·버전 전환·기존 폴더 호환성 수정

## 실제 코드 수정

- `src/bootstrap/launch_host.pyw`: Windows에서 `launcher.pyw`가 같은 이름의 namespace
  폴더를 가리는 import 충돌을 제거했다. 호스트 자체가 임시 JSON 작성 후 `os.replace`로
  상태를 저장하며 런처 모듈을 import하지 않는다. 저장 실패 시 기존 JSON을 보존한다.
- `src/launcher/launcher/unified_updater.py`: 구성요소를 확인한 뒤 적용하는 명시적
  버전 계열 정책을 구현했다. app은 tracker-v 태그, launcher는 launcher-v 태그만 허용한다.
  **각 구성요소의 8.x/9.x는 구형 계열, 0.x부터의 새 계열은 후속 계열**로 정의한다.
  같은 계열 안에서는 숫자로 비교한다. 향후 1.x 등도 후속 계열이며 8/9 major는 구형으로
  예약된다. 새 계열에서 구형으로의 자동 역전환은 거부하고 명시적 수동 복구는 허용한다.
  기록기 상태를 런처 상태와 비교하지 않는다. Release 선택과 설치 직전 검사에 같은 정책을 쓴다.
- `src/launcher/launcher/update_engine.py`: 실행·복구·설치 버전 목록에서 `v8.0.0`과
  `8.0.0` 경로를 호환한다. 정상 진입점이 있는 canonical 폴더가 우선이며 없으면 v 접두사
  폴더를 사용한다. 폴더를 이동·삭제·병합하지 않는다. 둘 다 있으면 목록에는 한 버전만 표시한다.
- `src/launcher/launcher.pyw`: 위 정책을 업데이트 발견/설치 및 버전 목록에 연결했다.
  UI 레이아웃과 이미지, 사용자 데이터 경로는 바꾸지 않았다.
- 호스트와 LauncherManager도 이전 런처의 v 접두사 경로를 복구 시 찾는다.

## 배포 범위

호스트는 기존 원칙대로 자동 업데이트 ZIP에 포함하지 않는다. CI는
`windows-bootstrap-<commit>` 검토용 artifact를 별도로 만들고 SHA-256을 첨부한다.
소스는 `src/bootstrap/`에 있으며 VBS/BAT 실행 방식은 그대로다.
이 artifact를 실제 설치에 적용하는 작업은 수행하지 않았다.

현재 설치된 구형 호스트/업데이터는 이 새 정책을 아직 모른다. 따라서 **최초 한 번은
승인된 호스트와 새 업데이터를 설치하는 전환 단계**가 필요하다. 구형 프로그램이
새 Release만으로 스스로 이 문제를 해결한다고 주장하지 않는다.
동일 버전 재배포는 금지되어 있으므로 수정본의 새 런처 버전은 게시 승인 시 정해야 한다.
이번 작업에서는 버전 번호, main, 공개 Release를 변경하지 않았다.

## 테스트 결과

로컬 Windows / Python 3.12: **51개 테스트 통과**.

- 원본 Windows import 충돌 재현 및 수정 호스트의 별도 프로세스 상태 저장 성공
- 모듈 우회 없이 시작 전 실패 → 다음 실행 시 자동 복구, healthy 확인 후 버전 유지
- 새 0.x 런처 실패 후 기존 `v9.0.0` 런처로 자동 복귀
- 두 구성요소의 8.x/9.x → 0.x 발견·설치·수동 복귀
- 같은/낮은 새 버전 거부, 구형 역전환 거부, 다른 구성요소/태그 혼용 거부
- 런처/기록기 추출 중 KeyboardInterrupt 및 상태 저장 실패: 이전 상태 유지, 임시 폴더 정리
- 기존 해시 오류 거부, 원본 기록기 소스 보존, CSV·JSON·배경·런처 설정 보존 회귀 테스트
- 팝업 렌더링 재검증 성공, X 위치 유지
- 실제 설치 폴더 246개 파일의 전후 해시 동일: 변경·누락 0개

테스트는 임시 설치와 제어된 정상/실패 자식 프로그램을 사용했다. 실제 게임 실행/OCR,
실제 사용자 PC의 강제 전원 차단은 테스트하지 않았다. 자동 복구는 기존 설계대로
healthy 확인 전 실패를 **다음 실행 시** 복구한다. healthy 이후 충돌이나 기록기 프로세스의
시작 후 오류에 대한 자동 복구 확대는 이번 세 수정의 범위에 포함하지 않는다.

## 수정/추가 파일

- src/bootstrap/launch_host.pyw 및 실행 VBS/BAT 2개 (신규 관리 소스)
- src/launcher/launcher.pyw
- src/launcher/launcher/update_engine.py
- src/launcher/launcher/unified_updater.py
- tests/test_installed_host.py, tests/test_transition.py
- tests/fixtures/installed_bootstrap/ 원본 3개 (회귀 비교용)
- .github/workflows/build.yml (검토용 bootstrap artifact)
- release-config/compatibility.json (게시 보류 사유 갱신)
- docs/COMPATIBILITY_FIXES.md, README.md

이전 설치 구조 조사 보고서와 원본 호스트 fixture는 과거 결함 증빙으로 유지한다.
