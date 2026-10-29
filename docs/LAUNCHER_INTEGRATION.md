# 런처 v0.0.2 통합 결과

사용자가 제공한 `launcher_v0.0.2_source`의 manifest로 93개 파일 SHA-256을 확인한 후
`src/launcher/`에 가져왔다. 원본 manifest는 가져온 파일의 기준 기록으로 보관하며,
빌드 시 변경된 소스의 체크섬으로 새 배포 manifest를 생성한다.
다운로드 폴더와 실제 설치/사용자 데이터는 변경하지 않았다. 기존 작업 브랜치의
배포 기능을 유지하고 확장했다. main 병합·태그·Release 게시는 수행하지 않았다.

## 변경

- `src/launcher/launcher.pyw`: 원본 UI 유지. 설정과 복구 안내의 기록기 버전을 실제
  기록기 상태로 표시한다. 패치 노트 버전을 런처 버전으로 치환하지 않는다.
  완료 팝업의 재시작 문구에서 폰트가 지원하지 않아 사각형으로 보이던 기호를 제거했다.
- `src/launcher/launcher/update_engine.py`: 이미 설치된 기록기 파일 전체의 해시를
  확인한 후 활성화한다. 상태 파일 저장이 성공한 후 메모리 상태를 전환한다.
  저장 실패 시 기존 활성 버전이 유지된다.
- `src/launcher/launcher/unified_updater.py`와 에셋 90개: 원본 그대로 통합.
- `release-config/launcher.json`: 런처 0.0.2 독립 설정. 기록기는 0.0.1 유지.
- `scripts/build_package.py`: 두 구성요소를 별도 ZIP·manifest·태그로 빌드.
- `scripts/prepare_release.py`: 실제 런처 검증기를 이용해 런처 패키지 검증.
- `.github/workflows/build.yml`: 런처 빌드·팝업 렌더링·별도 artifact 업로드 추가.
- `.gitattributes`: 런처 소스/에셋 원본 바이트 보존.
- `tests/test_distribution.py`: 런처 부재 테스트를 구성요소 혼용 차단 테스트로 대체.
- `tests/test_launcher.py`: 실제 빌드 패키지 기반 통합 테스트 7개 추가.
- `scripts/preview_launcher.py`: 실제 팝업 메서드로 검토 이미지 생성.
- `release-config/compatibility.json`: 남은 차단 원인을 실행 호스트와 버전 이전 문제로 갱신.
- `README.md`, `docs/RELEASES.md`, 이 문서: 현황/절차 설명.

## 검증 결과 (로컬 Windows, Python 3.12)

`python -m unittest discover -s tests -v`: **35개 통과**.

검증한 항목: 기존 기록기 소스 동일성, 두 구성요소 패키지 생성, 원본 런처의
manifest 검증, 구성요소별 Release 발견, 다운로드 해시 불일치 거부,
변경된 기존 기록기 폴더 거부, 상태 저장 실패 시 기존 활성 버전 유지,
런처/기록기 설치와 명시적 rollback, CSV·config·사용자 배경·런처 설정의 바이트 보존.
테스트는 임시 폴더와 모의 GitHub 응답을 사용했다. 실제 Release 다운로드/공개나
사용자 설치에서의 재시작 검증을 의미하지 않는다.

`python scripts/preview_launcher.py`: 통과. 실제 두 팝업 렌더링을 눈으로 확인했다.
발견은 분홍색 설치 버튼과 앉은 캐릭터, 완료는 쉬는 캐릭터와 보라색 재시작 버튼이다.
1440×810 논리 좌표에서 X 클릭 영역 `(1044,86)-(1096,138)`은
팝업 `(325,68)-(1115,744)` 안에 있고 두 화면에서 동일하다.
렌더링 검증은 실제 마우스 클릭/창 크기별 사용자 조작 테스트와 별개다.

검토 이미지: `dist/previews/discovery.png`, `dist/previews/success.png`.
이미지의 0.0.3은 테스트용 발견 버전이며 제품 버전을 올린 것이 아니다.
이번 통합 변경의 GitHub Actions는 아직 실행하지 않았다.

## 남은 자료와 차단 조건

1. **기존 설치의 `launch_host.pyw` 및 이를 실행하는 VBS/BAT 파일**이 필요하다.
   런처는 이 호스트로 재시작하고 pending/healthy 상태로 자동 복구를 위임한다.
   제공 자료에 호스트가 없어 시작 실패 후 자동 복구를 끝까지 검증할 수 없다.
   임의 호스트는 만들지 않았다. 로컬 패치 도구도 실행하지 않았다.
2. 현재 설치의 `launcher_state.json`, `launcher_runtime.json`에서 버전 정보만 확인해야 한다.
   기존 8.x/9.x 기록기는 새 0.x 태그를 낮은 버전으로 판단한다. 기록 보존을 전제로
   명시적 버전 이전 또는 기존 버전보다 높은 새 버전 정책이 필요하다.
3. `production-release`는 GitHub API로 소유자 `kcj110724-dotcom`이 유일한 필수 승인자이며
   self-review가 허용된 상태임을 확인했다. Deployment branch policy는 별도 제한이 없으며,
   게시 워크플로 자체는 main만 허용한다. CI에서 동일 설정을 읽기 전용으로 검사한다.
   실제 게시에는 여전히 최종 사용자 승인이 필요하다.

이에 따라 compatibility 상태는 pending을 유지한다. 승인 차단을 해제하지 않았다.
