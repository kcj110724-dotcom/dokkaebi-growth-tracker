# 중단된 artifact GUI 시험 완료 기록

실제 제품 파일/UI/Release 조회 코드는 변경하지 않았다. 이번 추가 파일은 시험 드라이버,
다운로드 도구, 고정 artifact 정보 및 증빙이다. compatibility.json은 pending 유지.

## 고정한 대상

- 소스 SHA: 9b742f4977101c8760c1a76cbfe57fc92d06a361
- 성공 push run: https://github.com/kcj110724-dotcom/dokkaebi-growth-tracker/actions/runs/41003472180
- bootstrap artifact ID: 12954785997
- bootstrap archive SHA-256: 9d64f34744bbde065ff721463bac3560d48818b75723d04f1946e5ebba79c191
- launcher artifact ID: 12954108935
- launcher archive SHA-256: 2e26602286e8bababc65ae712f53d83c98c4b28131dc18a1d336a3bd168f7997
- 내부 v0.0.3 ZIP SHA-256: 78e04820fe82b7ce7b682b0afd348e304c6dcd111c1317413e976d4f1d030d00

실제 GitHub artifact 다운로드와 archive SHA, 내부 build-info/source SHA/ZIP sidecar,
기존 업데이터의 payload SHA 및 manifest 검증을 사용했다. 로컬 재빌드로 대체하지 않았다.
인증은 기존 Git 자격 증명 helper를 통해 메모리에서 사용했고 저장/출력하지 않았다.
GitHub의 artifact storage redirect에는 인증 헤더를 전달하지 않는다.

## 결과와 중단 이력

| 시나리오 | 결과 |
|---|---|
| 이전 정상 GUI 시험 | 실제 다운로드·해시 검증·설치·재시작 healthy=true. 저장된 결과 재사용 |
| 이전 Escape 중단 시험 | 설치 완료(restart_required) 후 재시작 전 중단. 성공으로 세지 않음 |
| 승인받아 재개한 시작 실패 시험 | home→update→progress→restart_required 확인, 재시작 버튼 클릭. 임시 새 진입점 exit 7 주입 후 다음 호스트 호출에서 기존 0.0.1 실행 유지 확인 |
| 손상 다운로드 시험 | 실제 다운로드한 내부 payload 1바이트 변경. update→progress→error. SHA 거부 화면 확인, current=0.0.1 유지 |
| 기록·설정·배경 | 모든 완료 시험에서 기존 파일 해시 보존=true. host/runtime만 예상 변경에서 제외 |
| 실제 원본 | 모든 시험에서 전후 해시 일치=true |

발견/완료/오류 팝업은 설치되어 있던 v0.0.1의 실제 UI를 사용했다.
v0.0.1 완료 팝업은 단순한 재시작 안내이며 v0.0.3의 새 완료 에셋으로 바꾸지 않았다.
승인된 새 UI 디자인과 기존 제품 코드는 그대로 유지했다.

## 격리 방식과 판정 범위

scripts/artifact_ui_trial.py가 dist 아래 TemporaryDirectory에 원본을 복사하고
다운로드된 전환 패키지의 해시를 검사한 뒤 수정 호스트를 그 복사본에만 적용한다.
시험 프로세스의 discovery/download 함수만 고정 artifact 공급으로 바꾼다.
설치 버튼을 누르면 실제 GitHub artifact가 다운로드되고 기존 설치 메서드가 실행된다.
재시작은 기존 UI 메서드 → 관찰 wrapper → 실제 수정 호스트 → 실제 런처 프로세스다.
wrapper는 시험 자식의 수명/정리만 관리한다. 시작 실패 후 다음 실행은 시험 드라이버가
호스트를 다시 호출한다. 동일 실행에서 자동 감시 재시작을 구현한 것은 아니다.

정상 결과: dist/artifact-ui-success-retained.json.
시작 실패 결과: dist/artifact-ui-startup-result.json.
손상 결과: dist/artifact-ui-corrupt-result.json.
위 집계의 비식별 사본은 docs/evidence/에 보관한다. 개인 기록/스크린샷/설정 내용은 올리지 않는다.

시험 창은 180초 타임아웃을 두며 무한 재시도하지 않는다. GUI 도구가 창 종료 시점에
상태를 읽지 못한 경우 프로세스 결과/상태 기록으로 완료 여부를 별도 판정했다.
이전 정상 성공 시험은 불필요하게 반복하지 않았다.

## 아직 승인하지 않은 항목

- 공개 Release의 실제 검색/배포 경로는 이번 artifact 공급 시험과 다르다. 새 Release는 만들지 않았다.
- healthy 이후 충돌 자동 롤백은 기존 설계에서 지원하지 않는다.
- 실제 사용 설치 경로 확정·최초 호스트 적용·개인 기록의 기록기 화면 확인은 사용자 승인 전 보류.
- artifact 네트워크 중단 UI 시험은 이번 재개 범위에서 실행하지 않았다(손상/시작 실패는 완료).

최종 배포는 사용자가 버전/증빙/정확한 패키지를 승인하고, 호환성 보류 항목을 검토한 후
main 병합 → main 성공 CI artifact 고정 → 승인 요청 → 수동 Release workflow →
production-release 소유자 승인 순서로 진행한다. verified를 임의로 설정하지 않는다.
