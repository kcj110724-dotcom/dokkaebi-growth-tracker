# 최초 전환 패키지 검증 결과 — 2026-10-30

검증 코드: fd727966b930d934201d17c62e7153d0eeb17187.
별도 검토 ZIP: dist/host-transition-review/dokkaebi-host-transition.zip.
SHA-256: cd2d75cc0df85833532e284137fd41ca399aaca32d50ca21de626d085ed1326a.
이 로컬 ZIP은 해당 커밋 기준 결과이며 이후 CI artifact는 해당 run의 SHA를 따로 확인한다.

새 호스트 SHA-256: 5b340c1fd9b6a8220e3832de627f9359b8e2c4d3a68c88f9e08584dfc216ad55.
호스트 외 설치 파일은 전환 도구가 수정하지 않는다. ZIP 전체 체크섬은 도구·설명서·manifest도 포함한다.

## 이번에 수행한 검증

- 전환 전용 테스트 6개 통과: 적용/반복 적용/원복, 손상 payload 및 미확인 호스트 거부,
  교체 실패 원본 유지, 교체 직후 중단 시 원복, 손상 백업·사후 수정 호스트 거부,
  pending 업데이트·설치 내부 백업 경로 거부.
- 실제 v0.0.1 설치의 임시 복사본에서 생성 ZIP을 풀고 apply를 사용했다.
- 해당 복사본의 기존 업데이터로 v0.0.3 패키지를 설치하고 수정 호스트를 통해
  실제 pythonw 런처 프로세스와 healthy 신호를 확인했다.
- 임시 후보 진입점에 시작 실패/healthy 전 강제 종료를 주입하고 다음 실행에서
  실제 v0.0.1 런처 프로세스가 유지되는 것을 확인했다.
- 테스트 자식들을 종료한 뒤 rollback으로 원래 호스트 바이트가 돌아오는지 확인했다.
- host/runtime 외 복사본 기존 244개 파일 SHA 동일. 실제 원본 246개 파일 SHA 동일.
- healthy 이후 강제 종료는 현재 버전을 유지한다. 이 범위의 자동 롤백은 지원하지 않는다.

이번에는 기존 전체 회귀 테스트를 로컬에서 반복하지 않고 전환 전용 테스트와
패키지 통합 실행에 집중했다. 전체 Windows 검사는 PR CI에서 수행한다.

## 실행하지 않은 항목

실제 설치 변경, main 병합, Draft/공개 Release 생성, 실온라인 artifact 다운로드→
팝업 클릭→설치→완료→재시작 전체 흐름은 수행하지 않았다.
온라인 시험은 [HOST_TRANSITION.md](HOST_TRANSITION.md)의 격리된 Actions artifact
계획을 따른다. 전용 시험 드라이버 구현/검토와 정확한 artifact 선정이 다음 작업이다.
그 전까지 compatibility.json은 pending이다.

사용자가 최종 승인 후 직접 할 일은 설치 루트 확인, 앱 종료, 승인 ZIP 해시 확인,
inspect/apply 실행, 기존 런처 재실행 확인이다. 문제가 있으면 앱 종료 후 지정한
백업과 rollback을 사용한다. 원본 호스트로 복귀하면 기존 결함도 복귀하므로 새 런처의
pending 복구와 호스트 원복을 혼동하지 않는다. 상세 명령은 패키지 README에 있다.
