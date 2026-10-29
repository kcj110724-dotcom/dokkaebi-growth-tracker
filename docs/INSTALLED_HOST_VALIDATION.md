# 실제 설치 구조 검증 결과

검증일: 2026-10-29. 원본 설치·다운로드 폴더는 읽기 전용으로 조사했다.
새 테스트와 보고서는 기존 작업 브랜치에만 작성했다. main 병합, Release 게시,
설치 파일 변경, 실제 게임/런처 실행은 수행하지 않았다.

## 발견한 설치 후보

OneDrive 바탕 화면에서 다음 폴더를 발견했다.

| 폴더 | 런처 상태 | 기록기 상태 | 호스트 |
|---|---|---|---|
| Dokkaebi_Growth_Complete_Installer_v0.0.1/dokkaebi_growth_launcher | 0.0.1 | 0.0.1 | 있음 |
| 런처 만들기 재료/Dokkaebi_Growth_Launcher_Tracker_v0.0.0_Integrated_Update/dokkaebi_growth_launcher | 0.0.0 | 0.0.0 | 있음 |
| 런처 만들기 재료/Dokkaebi_Launcher_v0.0.0_Scroll_Fixed/dokkaebi_growth_launcher | 별도 runtime 파일 미확인 | 9.0.0, 이전 8.0.0 | 없음 |

세 곳에 실행 VBS/BAT가 있으며 첫 두 호스트는 SHA-256이 동일하다.
어느 폴더의 바로가기를 평소 사용하는지는 이 조사만으로 확정하지 않았다.

완성 설치 폴더 구조: 루트의 launcher.pyw, launch_host.pyw, launcher/,
launcher_versions/0.0.1, versions/{0.0.0,0.0.1,v8.0.0}, user_data/, backups/,
launcher_state.json, launcher_runtime.json, launcher_settings.json.
VBS/BAT는 Python 3.12로 launch_host.pyw를 호출한다.

## 테스트와 판정

전체 로컬 Windows 테스트 **42개 통과**. 통과에는 정상 동작뿐 아니라 아래 결함을
예상대로 재현한 테스트도 포함한다. 제품의 모든 호환성 검증 완료를 뜻하지 않는다.

| 요구사항 | 결과 |
|---|---|
| 런처 시작 실패 자동 복구 | 원본 구조에 Windows import 충돌이 있어 차단됨 |
| 복구 알고리즘 | 테스트에서만 패키지 경계를 명시하면 실패한 자식 프로세스 종료 후 다음 실행에서 이전 런처 선택 성공 |
| 정상 시작 확인 | healthy 신호 후 다음 실행에서 현재 버전 유지 성공 |
| 설치 실패 | SHA 불일치 거부, 상태 저장 실패 시 이전 활성 상태 유지 확인 |
| 사용자 데이터/설정 | 격리된 CSV·JSON·사용자 배경·런처 설정 바이트 보존 확인 |
| 독립 업데이트 | 구성요소별 Release 선택/설치/명시적 복구 성공. 호스트의 런처 복구가 기록기 상태 파일을 바꾸지 않음 |
| 8.x/9.x → 0.x 자동 업데이트 | 미지원: 숫자 비교에서 0.x가 더 낮으므로 업데이트로 선택되지 않음 |
| v8.0.0 폴더 호환성 | 경로 불일치: Store는 versions/8.0.0을 사용하며 versions/v8.0.0을 자동으로 찾지 않음 |

호스트 결함: `save()`의 `from launcher.update_engine import atomic_json`에서,
Windows는 동일 루트의 launcher.pyw를 모듈로 먼저 선택한다. launcher/에
__init__.py가 없어 `'launcher' is not a package` 오류가 발생한다.
원본 구조를 임시 폴더에 재현한 별도 Python 프로세스에서 확인했다.
pending 시도 횟수 저장 전 실패하므로 원본 그대로 자동 복구 성공이라고 판정할 수 없다.

알고리즘 테스트는 sys.modules에 명시적인 package 경계를 제공하는 **테스트 전용 우회**를
사용했다. 원본 호스트 파일은 수정하지 않았다. 자식 프로세스는 임시 pass/실패 프로그램이며,
실제 런처 전체 UI 시작을 대신하는 제어된 테스트다. 실제 설치에 우회/수정을 적용하지 않았다.

복구 시점: 시작 완료 신호 이전 실패를 다음 실행에서 복구한다. 동일 실행에서 즉시
재시작하는 방식이 아니다. 런처 코드는 650ms 뒤 healthy를 호출하므로 그 이후 실패까지
자동 복구한다고 보장하지 않는다. 기록기 실행 실패는 현재 UI에서 경고만 표시하며,
런처와 같은 pending/healthy 자동 복구 구조는 없다. 명시적 버전 복구는 별도로 동작한다.

실제 완성 설치 폴더의 기존 **246개 파일**을 검증 전후 SHA-256으로 비교했고,
변경·누락은 **0개**였다. 실제 기록 내용은 출력하거나 저장소에 복사하지 않았다.

## 추가한 파일

- tests/fixtures/installed_bootstrap/launch_host.pyw: 설치 호스트 원본 복사
- tests/fixtures/installed_bootstrap/2_OPEN_LAUNCHER_SILENT.vbs: 실행 경로 확인용 원본
- tests/fixtures/installed_bootstrap/2_OPEN_LAUNCHER.bat: 실행 경로 확인용 원본
- tests/test_installed_host.py: 호스트 검증 및 결함 재현 테스트 7개
- docs/INSTALLED_HOST_VALIDATION.md: 본 보고서

이번 테스트는 로컬에서 실행했다. 새 테스트의 GitHub CI는 아직 실행하지 않았다.
기존 게시 차단 상태는 유지한다. 다음 구현 단계는 패키지 import 충돌 해결,
레거시 버전/폴더 이전 정책과 기록기 실행 실패 시 복구 요구사항 결정이다.
