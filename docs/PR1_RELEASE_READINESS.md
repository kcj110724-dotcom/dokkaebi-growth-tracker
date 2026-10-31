# PR #1 설치 전환 검증 및 게시 보류

검증일: 2026-10-29. PR #1은 Draft, base main, head
`codex/approved-windows-releases`임을 확인했다. 제품 소스 기준 커밋은
`37b215af6bc0771cf3b0098ea36b07ee293fa31b`이다.
이 보고서는 **verified 전환 증빙의 일부이며 완료 승인이 아니다**.
`release-config/compatibility.json`의 pending과 빈 evidence 배열을 그대로 유지했다.

## 실제 설치본 복사 검증

`Dokkaebi_Growth_Complete_Installer_v0.0.1/dokkaebi_growth_launcher` 후보 설치의
runtime current=0.0.1을 확인하고 임시 복사본에서 실행했다. 평소 사용 중인
바로가기가 이 폴더를 가리키는지는 아직 확인하지 않았다.
실제 개인 기록/설정은 공개하지 않았고 임시 복사본은 검증 후 정리했다.

재현 도구: `scripts/check_installed_transition.py --installation <설치 경로> --source-sha <제품 소스 SHA>`.
Windows/Python 3.12에서 실행하며 원본 설치는 읽기만 한다. 별도 프로세스에서
실행해야 한다. 기존 코드와 후보 패키지 검증에 쓰는 도구로서 전체 GUI 테스트를 대신하지 않는다.

| 검증 | 결과 |
|---|---|
| 실제 0.0.1 업데이터로 현재 0.0.2 전체 패키지 설치 | 성공: 외부 SHA 검증, 내부 manifest 검증, pending 전환, previous=0.0.1 |
| 잘못된 다운로드 해시 | 거부, 기존 runtime 유지 |
| 추출 중 KeyboardInterrupt | 기존 runtime 유지, 대상 폴더 미생성, 임시 stage 정리 |
| 원본 호스트 재시작 | **실패**: Windows launcher 모듈 충돌, pending attempts=0 유지 |
| 수정 호스트의 경로 선택/상태 저장 | 복사본에서 0.0.2 선택 후 healthy 미확인 시 다음 호출에 0.0.1 복구. 자식 실행은 가로채서 선택만 확인 |
| 복사본 기존 기록/설정/기록기 파일 | runtime 외 기존 245개 파일의 SHA 동일 |
| 실제 원본 설치 | 246개 파일 SHA 전체 동일 |
| 별도 회귀 테스트 | 51개 모두 통과. 제어된 자식 프로세스 실패/정상 시작, 다음 시작 복구 포함 |

실제 old updater SHA-256:
`0a53af5e0b1c9024d837f1cc2a136ba24e729c4c25a21049bbe857b488b8a8b9`

원본 host SHA-256:
`84b0026111980ac2ed9c2c4e4286eb8c2536d2d116f05a569c219247358c85db`

검증한 로컬 launcher ZIP SHA-256:
`f6daec4ecd7eba39e88c37c01c5d1ca69b285fcb064bd8f5307177e7f0952d66`

이 ZIP은 로컬 재현용이며 CI artifact와 동일하다고 주장하거나 게시 후보로 승인하지 않는다.
네트워크 다운로드는 메모리 응답으로 대체했다. 전체 UI의 업데이트 발견→완료→재시작,
실제 기록 표시와 정상 healthy 신호, 실환경 자동 복구는 아직 완료되지 않았다.

## 배포를 막는 원인

일반 launcher ZIP에는 안정 호스트가 없다. 따라서 원본 0.0.1 설치에 0.0.2 ZIP만
배포하면 문제 있는 호스트가 그대로 남는다. 업데이트 설치 성공은 곧 정상 실행을 뜻하지 않는다.
수정 호스트/실행 파일의 최초 적용 및 실패 시 원복 절차를 별도로 마련하고 검증해야 한다.
현재는 bootstrap 검토용 artifact만 있으며 실제 설치 적용 도구/완료 증빙은 없다.

복구는 healthy 이전 실패를 **다음 실행 시** 처리한다. 호스트가 종료된 자식을 감시해
동일 실행에서 자동 재시작하는 방식이 아니다. healthy 이후 충돌과 기록기 프로세스의
시작 후 오류에 대해서는 같은 자동 복구를 보장하지 않는다.

## verified 전환에 필요한 증빙

1. 실제 사용 설치 경로/바로가기, Windows/Python/의존성 버전 및 원본 호스트·업데이터 해시를 확정한다.
2. 승인된 bootstrap 최초 전환·원복 절차를 복사본에서 검증한 뒤 실제 적용을 별도로 승인받는다.
3. 고정한 CI run/source SHA/패키지 SHA로 0.0.1→후보 버전의 발견, SHA 검증,
   완료 팝업, 재시작, 실제 UI 정상 표시와 healthy 처리를 검증한다. 공개 Release를
   시험 목적으로 게시할 필요는 없으며 테스트 공급원 사용 범위를 증빙에 명시한다.
4. 실패 전/후/다음 시작 상태를 남겨 손상 패키지·설치 중단·시작 실패·수동 복귀를
   확인한다. 기존 기록과 설정은 해시뿐 아니라 UI에서 읽히는지도 확인한다.
   런처 업데이트가 기록기 버전/데이터를 바꾸지 않고 반대 방향도 독립적인지 확인한다.
5. 비식별 보고서와 실행 로그, artifact 식별자, UI 증빙, 남은 한계를 검토하고 사용자
   승인을 받은 후에만 status=verified와 evidence 경로를 변경한다.

현재 gate는 verified 문자열, 비어 있지 않은 evidence 경로 및 파일 존재를 검사한다.
문서 내용의 진실성이나 해당 패키지와 증빙의 일치까지 자동 판정하지 않으므로 사람의
검토가 필수다. 과거 테스트 성공 문서만 연결해 차단을 해제해서는 안 된다.

## 버전 및 승인 기반 실행 순서

조회 시 공개 Release는 tracker-v0.0.1과 v9.0.0이며 launcher-v0.0.2는 없었다.
현재 후보 설정은 launcher 0.0.2 / tracker 0.0.1이다. launcher 0.0.2가 실제로
사용자에게 이미 배포되지 않았다는 확인이 있으면 최초 launcher-v0.0.2 후보로 사용할 수 있다.
이미 제공된 0.0.2 설치가 있다면 수정본은 0.0.3 등 새 버전이 필요하다. 번호는 아직 변경하지 않았다.
tracker-v0.0.1은 기존 공개 버전이므로 덮어쓰지 않으며, 기록기 변경이 없다면 재배포하지 않는다.

1. 위 전환 검증 완료, 후보 버전 결정, compatibility 증빙 검토.
2. 사용자 최종 승인 후 PR 병합. main에서 성공한 push/manual Windows CI의 커밋과
   artifact를 고정한다. PR merge 가상 커밋의 CI만으로는 게시할 수 없다.
3. component/version/tag/source_sha/build_run_id/ZIP SHA/latest를 담은 새 요청을 작성한다.
   launcher는 latest=false를 제안하며 기존 tracker latest를 유지한다.
4. 사용자가 정확한 패키지를 승인한 뒤 approved=true 요청을 검토해 main에 반영한다.
5. main에서 `Dokkaebi approved release`를 수동 실행하고 요청 경로를 입력한다.
   preflight 후 production-release에서 소유자가 해당 배포를 승인한다.
6. 성공한 CI artifact를 재빌드 없이 게시한다. 태그는 고정 SHA, Release는 draft 생성 후
   ZIP/SHA 업로드가 모두 성공해야 공개한다. 기존 태그/버전은 덮어쓰지 않는다.

이번 검증에서는 실제 설치 수정, main 병합, Release 요청 승인 또는 게시를 하지 않았다.
