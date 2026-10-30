# 다운로드 중단 GUI 시험 결과

판정: 시험한 연결 끊김 시나리오 통과. 기존 실행이 결과 저장까지 완료되어 재개 시
다시 실행하지 않았다. 시험 코드 문법, 결과 JSON과 stdout의 일치, 빈 stderr,
기존 artifact의 고정 SHA를 확인하고 비식별 결과만 보존했다.

## 범위와 실제 관찰

- 기존 artifact 구성 재사용: source 9b742f4977101c8760c1a76cbfe57fc92d06a361,
  성공 run 41003472180, launcher artifact 12954108935.
- 실제 GitHub API에서 run/source/digest/만료 여부를 확인한 후 artifact storage 응답을 읽었다.
  전체 14,112,160바이트 중 262,144바이트를 받은 직후 시험 프로세스의 progress callback에서
  ConnectionResetError를 주입했다. 시스템 네트워크 설정이나 제품 Release 조회는 바꾸지 않았다.
- 이전에 검증된 전체 artifact와 payload SHA/manifest를 시험 시작 전 다시 검사했다.
  중단된 응답 자체가 전체 해시 검증을 통과했다고 주장하지 않는다.
- 원본 전체 백업을 입력으로 사용하고 임시 v0.0.1 복사본에서만 실행했다.
  실제 사용자 설치본은 입력/교체 대상이 아니며 실제 호스트 전환을 반복하지 않았다.
- 화면에서 업데이트 발견→다운로드 진행→오류(Injected transfer interruption)를 관찰했다.
  확인 버튼 후 기존 v0.0.1 홈과 배경이 다시 표시됐다.
- 저장된 UI 단계는 home→update→progress→error→home→update→progress→error→home이다.
  재진입과 두 번째 중단 뒤 홈 복귀도 기록됐다. 자동 재시도나 다운로드 재개 기능의 증빙은 아니다.
  중단 주입을 해제한 성공 재다운로드는 반복하지 않았으며 기존 정상 시험을 재사용한다.

## 결과

| 확인 항목 | 결과 |
|---|---|
| 오류 처리 | 오류 화면 표시, 확인 후 홈 복귀. 복구 불가능한 오류 없음 |
| 설치 상태 | current=0.0.1 유지, runtime 바이트 동일, 후보 버전 폴더 미생성 |
| 불완전 다운로드 | 다운로드 함수가 완성 ZIP을 저장하기 전에 예외 종료, download.zip 미생성 |
| 기록·설정·배경 | host/runtime를 제외한 기존 파일 SHA 동일. runtime도 별도로 동일 확인 |
| 입력 백업 | 전후 파일 해시 동일 |
| 실행 종료 | 결과 저장 및 정상 정리 후 시험 Python 프로세스 없음 |

기계 판독 결과: [artifact-ui-interrupted.json](evidence/artifact-ui-interrupted.json).
개인 경로·기록·설정 내용·스크린샷·복구 영수증은 업로드하지 않는다.

## 한계와 출시 승인

실제 artifact 응답을 읽는 중 예외를 주입한 시험이다. 무응답 시간 초과, 모든 프록시/OS
네트워크 장애를 각각 시험한 것은 아니며 공개 Release 다운로드 경로 검증과도 구분한다.
공개 Release의 발견·첨부파일 전달은 게시 후 승인된 점검으로 확인해야 한다.
healthy 이후 충돌 자동 롤백 미지원은 유지하며 출시 안내에 명시한다.
compatibility.json은 pending 유지. verified 전환·main 병합·Release 게시·실제 v0.0.3
설치는 각각 사용자 승인 전 실행하지 않는다. 최종 게시 파일은 병합 후 main CI로 다시 고정한다.
