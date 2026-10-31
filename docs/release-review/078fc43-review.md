# 런처 v0.0.3 출시 검토 — 2026-10-31

> 078fc43 시점의 보존 기록이다. 이후 확정한 호스트 동봉 방식과 승인 조건은
> [배포 절차](../LAUNCHER_RELEASE_PROCEDURE.md)를 따른다. 아래 해시는 당시 후보이며
> main CI의 최종 source SHA/run/호스트 ZIP 해시로 교체해야 한다.

판정: 검토 후보 확정, 공개 게시 보류. PR #1은 Draft/미병합이며 소스는
078fc43c958d797ebf6f8200a27d9ffc543b1d83. 작업 폴더는 clean이다.
이번에는 코드/디자인/승인 상태를 변경하지 않고 기존 64개 CI 테스트와 GUI 시험을 재사용했다.

## 승인 후보 파일

성공 Windows push CI run 41050222770:
https://github.com/kcj110724-dotcom/dokkaebi-growth-tracker/actions/runs/41050222770

런처 버전 0.0.3 / 예정 태그 launcher-v0.0.3 / latest=false.
기록기 0.0.1은 독립 유지하며 tracker-v0.0.1을 덮어쓰거나 재게시하지 않는다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| dokkaebi-launcher.zip | 14,112,952 bytes | 78e04820fe82b7ce7b682b0afd348e304c6dcd111c1317413e976d4f1d030d00 |
| dokkaebi-host-transition.zip | 6,355 bytes | badbe51ed3bfce2429369c195ea3d39ebe2487c2f5288d23659b99fd73ff8ba4 |

Actions launcher artifact ID 12973129791, archive SHA
3108596d97e3989251c7a52afaab563a516037f0dc195aa2679712c374e9926a.
bootstrap artifact ID 12973867901, archive SHA
82468fd5a05806e739fd9cfc7a3ca53fd8c765485ba6feb8bb7c93fa99ee0175.
외부 artifact archive와 내부 배포 ZIP 해시는 서로 다르다.
artifact 만료: 2026-11-29(UTC). 게시 직전에 만료/태그 충돌을 다시 확인한다.

최신 artifact를 실제 내려받아 외부/내부 체크섬을 확인했다. 런처 ZIP은 실제 GUI 시험에
사용한 9b742f4 빌드와 바이트 해시 동일. 전환 ZIP은 transition.json의 source_sha만
달라졌고 host/tool/README는 시험본과 바이트 동일. 새 기능 변경 없이 증빙 재사용 가능하다.
단, 최종 게시 후보는 병합 후 main CI의 SHA/run ID로 다시 고정해야 한다.

## 최종 코드 검토 결과 및 한계

- 런처/기록기 태그·비교·설치는 독립. SHA 검증 후 설치, 사용자 데이터 경로 분리.
- host 전환은 알려진 원본 SHA와 안정된 runtime=0.0.1만 허용. 이미 수정된 호스트,
  진행 중인 pending, 링크/junction, 기존 백업 덮어쓰기를 거부한다.
- 호스트 적용은 같은 파일시스템 임시 파일→os.replace. 백업/영수증을 먼저 기록한다.
  적용 중 예외와 교체 직후 중단 원복은 시험됨. 전원 차단/OneDrive 충돌/모든 디스크 장애를
  검증한 것은 아니다. concurrent 실행을 막는 OS 잠금도 없다.
- --apps-closed는 사용자 확인일 뿐 프로세스 감지가 아니다. 앱을 직접 종료해야 한다.
- 자동 백업은 host와 receipt뿐이다. user_data/settings/runtime 전체 백업 도구가 아니다.
  최초 적용 전 설치 전체를 별도 위치에 복사해 보관할 것을 권고한다.
- rollback은 host만 되돌린다. runtime/런처 버전/기록은 복원하지 않는다. 설치 후 host가
  달라졌으면 거부한다. 원본 host로 되돌리면 기존 import 결함도 복귀하므로 pending
  업데이트 중에 무작정 rollback해서는 안 된다. 새 런처 실패는 수정 host의 다음 실행
  복구로 먼저 처리하고, 필요시 승인된 백업 상태와 함께 복구를 검토한다.
- healthy 이전 실패는 다음 실행에서 이전 런처 선택. 같은 실행의 감시 재시작이 아니다.
  **healthy 이후 강제 종료/충돌은 현재 버전을 유지하고 자동 롤백하지 않는다.**
  이 범위는 명시적 수동 복구 대상이며 자동 복구가 완전하다고 안내하면 안 된다.
- 공개 Release discovery는 일반 제품의 기존 API를 유지했다. GUI artifact 시험은
  공급 경로를 시험 프로세스에서 바꾼 것으로 공개 Release 경로의 실전 시험과 동일하지 않다.
- 배포 gate는 approved/verified/증빙 파일 존재, 성공한 동일 저장소 CI와 SHA, main 조상,
  소유자 환경 승인을 확인한다. 증빙 내용의 완전성은 사람이 검토해야 한다.
- CI는 push/manual 빌드가 main 조상인지 검사하며 '그 빌드가 main에서 실행됐는지'까지
  강제하지 않는다. 이번 출시 절차에서는 반드시 병합 후 main CI를 사용한다.
- Release는 태그 고정→draft→두 자산 업로드→공개 순서. 중간 실패 시 태그/draft가
  남을 수 있으며 자동 삭제/덮어쓰기는 없다. 실패 로그를 검토한 후 처리해야 한다.
- Python 패키지 ZIP이며 독립 EXE/전체 Python 설치기가 아니다. 사용 환경 의존성과
  보안 프로그램/잠긴 파일 영향은 배포 안내에 포함해야 한다.

## 아직 결정/확인해야 하는 사항

1. 실제 사용하는 바로가기의 설치 루트와 Python 3.12 환경을 확정한다. 원본에는 미적용.
2. 최초 전환 패키지의 일반 사용자 전달 경로를 승인한다. 현재 publisher는
   dokkaebi-launcher.zip과 .sha256만 게시한다. bootstrap은 Actions 검토 artifact이며
   만료된다. 일반 사용자용 지속 배포 경로/별도 첨부 승인이 필요하다. 이번에는 추가하지 않았다.
3. 실제 기록기 화면에서 개인 기록 읽기 확인, 필요시 artifact 다운로드 중단 GUI 시험,
   공개 Release 후 smoke 확인 계획을 정한다. 출시 전 불가능한 공개 경로 확인은
   사후 확인 항목으로 명확히 구분하고 사용자에게 잔여 위험을 승인받는다.
4. healthy 이후 자동 복구 미지원 범위를 수용할지 확인한다. 미검증 항목을 단순 동의만으로
   검증 완료라 표기하지 않는다. compatibility.json은 현재 pending을 유지한다.

## 승인 뒤 실행 순서 (아직 실행하지 않음)

1. 사용자: 버전 0.0.3, 잔여 한계, 전환 패키지 전달 방식 및 PR 병합 범위를 승인.
2. 필요한 미검증 증빙을 보완하고 검토. 완료된 범위에 대해서만 compatibility 상태 변경을
   제안한다. unresolved 항목이 남아 있으면 pending을 유지하고 게시를 진행하지 않는다.
3. 승인된 변경을 main에 병합. main Windows CI 성공 후 artifact/run/source SHA와
   내부 ZIP SHA를 새 승인 목록으로 만든다. ZIP 해시가 같으면 기존 기능 시험 재사용,
   다르면 차이 원인을 확인하고 필요한 범위만 재검증한다.
4. 새 요청 JSON에 main CI의 정확한 정보/launcher-v0.0.3/latest=false를 입력한다.
   사용자가 해당 패키지를 승인한 뒤 approved=true 요청을 main에 반영한다.
5. main에서 Dokkaebi approved release를 요청 경로로 수동 실행한다.
6. 사용자: production-release의 Review deployments에서 최종 게시 승인.
7. 게시 파일/태그/SHA와 일반 Release 조회를 확인한다. 최초 전환은 승인된 사용자만
   백업→inspect→apply→기존 런처 실행 확인 순서로 적용한다.

동봉한 launcher-v0.0.3.review.json은 approved=false인 검토 초안이다.
현재 작업 브랜치 CI 정보이므로 정식 실행 요청으로 사용하지 않는다.
main 병합, Release 게시, 실제 설치, compatibility 상태 변경은 이번에 수행하지 않았다.
