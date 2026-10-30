# 런처 0.0.3 출시·최초 전환 절차

최신 실제 적용 결과: [호스트 전환 후 출시 검토](release-review/host-transition-acceptance.md).
한 실제 설치본에서 승인된 호스트 교체와 기존 v0.0.1 정상 시작을 확인했고,
사용자는 기록기 화면의 기록·설정 정상 표시를 보고했다. 아래 최초 전환 절차는
아직 전환하지 않은 사용자를 위한 안내다. 현재 compatibility는 pending이며 게시 미승인이다.

## 전달 방식 확정

사용자 승인 후 `launcher-v0.0.3` Release 하나에 다음 네 파일을 함께 게시한다.
`dokkaebi-launcher.zip`, `.zip.sha256`, `dokkaebi-host-transition.zip`, `.zip.sha256`.
latest=false. 기록기 Release/버전은 변경하지 않는다. 자동 조회기는 정해진 런처 ZIP만
선택하므로 추가 host ZIP을 자동 실행하지 않는다. Draft 동안은 일반 업데이트 목록에서 제외된다.

같은 성공 CI run/source SHA의 launcher 및 bootstrap artifact를 다운로드한다.
요청 JSON의 `sha256`과 `host_transition_sha256` 두 값을 각각 고정해 확인한다.
호스트 메타데이터/manifest/파일 목록도 확인하고 네 파일 업로드 완료 후 공개한다.
실패 시 draft 상태를 유지한다. 이미 생성된 태그/draft는 자동 삭제하지 않는다.
Actions artifact의 만료/인증 문제를 일반 사용자에게 전가하지 않고 공개 Release 첨부로 전달한다.

## 일반 사용자의 최초 한 번 작업 (별도 승인 후에만)

1. 실제 사용 바로가기의 설치 폴더를 확인하고 런처·기록기를 모두 종료한다.
   설치 폴더 전체를 별도 위치에 한 번 복사해 보관한다. 도구 자체의 백업은 host/receipt뿐이다.
2. 공식 Release의 `dokkaebi-host-transition.zip`을 설치 폴더 밖에 풀기 전에
   ZIP SHA-256을 Release 승인 안내/.sha256과 비교한다. Python 3.12가 필요하다.
3. 압축을 푼 폴더에서 아래 명령을 실행한다. 실제 경로는 따옴표 안에 입력한다.

```powershell
python host_transition.py inspect --root "<설치 폴더>"
python host_transition.py apply --root "<설치 폴더>" --backup "<설치 밖의 새 백업 폴더>" --apps-closed
```

부모 백업 폴더는 존재해야 하며 마지막 새 폴더는 없어야 한다. 앱 종료 여부는 도구가
검출하지 않으므로 사용자가 확인한다. 알 수 없는 host/hash, pending, 다른 버전은 중단한다.
기존 BAT/VBS로 v0.0.1 실행을 확인한 뒤 기존 런처에서 업데이트·재시작한다.
런처 ZIP을 수동으로 설치 폴더 위에 풀지 않는다.

전환 직후 문제가 있으면 앱을 닫고 다음을 실행한다:

```powershell
python host_transition.py rollback --root "<같은 설치 폴더>" --backup "<앞에서 만든 백업 폴더>" --apps-closed
```

이 명령은 host만 복원한다. 새 런처 설치 후 pending 상태라면 수정 host의 다음 실행
복구를 먼저 사용한다. 원래 host로 돌아가면 기존 import 결함도 돌아오므로 runtime을
무작정 되돌리거나 백업을 덮어쓰지 않는다. 기록·설정·배경은 도구가 건드리지 않는다.

## healthy 이후 충돌 정책

현재 정책 유지 권고: healthy 이전 시작 실패는 다음 실행에서 자동 복구하며,
healthy 이후 강제 종료/충돌은 자동 롤백하지 않고 명시적 수동 복구 대상이다.
이 한계 자체는 시작 실패 복구 제품으로 출시하는 것을 반드시 막는 결함으로 보지 않는다.
단, 사용자가 이 범위를 수용하고 Release 안내에 명시해야 한다. 모든 충돌 자동 복구를
요구한다면 별도 구현·검증 전 출시 차단 사유다. 사용자 동의를 검증 성공으로 기록하지 않는다.

## compatibility 승인 조건

이미 통과: 실제 artifact 다운로드/외부·내부 SHA/manifest, 임시 0.0.1 전환,
GUI 설치·완료·재시작 healthy, 손상 거부, 시작 실패 다음 실행 복구, 파일 바이트 보존,
8.x/9.x 전환 정책. 기존 증빙을 재사용하고 반복하지 않는다.

별도 실제 적용 단계: 사용 바로가기/설치 경로·Python 확인, 원본 전체 백업,
사용자 승인 후 최초 host 적용, 기존 기록기에서 기록/설정 읽기 확인. 실제 설치 변경은
일반 출시 승인과 별개로 명시적으로 승인받는다. 완료 전 pending 유지.

공개 Release 조회 경로는 artifact 시험과 구분한다. 공개 전에는 조회 필터/asset 계약을
검토하고, 공개 후 승인된 점검에서 실제 발견/다운로드를 확인한다. 공개 전 검증했다고
표시하지 않는다. 아직 수행하지 않은 네트워크 중단 GUI 시험도 미검증으로 남긴다.
증빙의 범위·미검증 항목·수용한 한계를 사용자와 검토한 뒤에만 verified 변경을 제안한다.

## 승인 후 순서

1. 사용자: 0.0.3, healthy 한계, 동일 Release의 수동 host 패키지 전달 및 PR 병합 승인.
2. 실제 설치 검증은 별도 승인 범위에서 수행. unresolved 항목이 남으면 pending 및 게시 차단 유지.
3. 승인된 PR을 main에 병합하고 main Windows CI 성공을 기다린다.
4. 그 run/source SHA와 launcher/host 두 ZIP SHA를 새 요청에 고정한다.
   launcher ZIP이 검증본과 같으면 기존 기능 증빙 재사용. 다르면 원인과 필요한 검증만 수행.
5. 사용자가 정확한 파일과 증빙을 승인한 뒤 approved=true 요청을 main에 반영한다.
6. main에서 수동 Release workflow를 실행하고 production-release 소유자가 승인한다.
7. 네 첨부파일과 태그/SHA, 일반 Release 조회를 확인한다.

docs/release-review의 3개 파일은 이전 로컬 출시 준비 기록을 보존한 것이다.
요청 초안은 approved=false이고 이전 branch CI 정보이므로 그대로 실행하지 않는다.
이번 작업에서는 실제 설치/main/Release/compatibility 상태를 변경하지 않는다.
