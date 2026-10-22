# KR-Inside 공통 Blogger 테마 자산

`assets/releases/v1/`의 CSS·JS는 `www`, `news`, `trip`, `item.kr-inside.com`에서 공통으로 사용합니다. GitHub에 게시한 파일은 jsDelivr의 GitHub CDN으로 제공합니다.

| 파일 | 역할 |
| --- | --- |
| `common.css` | 공통 컴포넌트, FAQ, 다크 모드, 동작 줄이기 설정 |
| `typify-base.css` | 원본 테마의 기본 스타일과 폰트 |
| `typify-responsive.css` | 원본 테마의 후반부 반응형 스타일 |
| `typify-plugins.js` | 원본 테마 플러그인 |
| `typify-runtime.js` | 메뉴 구성, 썸네일 로딩 등 원본 테마 실행 코드 |

원본의 메뉴·위젯 설정, 광고·댓글 템플릿과 Blogger 변수는 XML에 남습니다. CSS 안의 Blogger 값은 XML에서 CSS 사용자 지정 속성으로 전달합니다. Blogger 변수가 들어간 미디어 쿼리는 XML에 유지하며, 앞뒤 CSS 파일의 순서도 유지합니다. 두 JS 파일은 원본 그대로이며 기존 jQuery 뒤에서 동기 실행합니다.

## XML 생성

Python 3 표준 라이브러리만 필요합니다. 원본 Blogger XML은 공개 저장소에 넣지 않고 로컬 파일로 전달합니다.

```bash
python3 tools/build_blogger_release.py /path/to/original-theme.xml /path/to/output \
  --base-url https://cdn.jsdelivr.net/gh/HG-oh/kr-inside-styles@COMMIT/assets/releases/v1
```

`COMMIT`은 자산이 게시된 실제 Git 커밋 전체 해시로 바꿉니다. 생성기는 이 테마의 원본 내보내기 형식을 대상으로 하며, 예상 구조가 다르면 중단합니다. 자산 5개와 `theme-item.lightweight.xml`, 파일 크기·해시를 담은 `release-manifest.json`, 보존 항목을 담은 `release-audit.json`을 생성합니다. 명령 자체는 GitHub 게시나 Blogger 적용을 수행하지 않습니다.

먼저 자산을 게시한 다음, 실제 커밋 주소로 XML을 생성합니다. 배포 전에 XML이 가리키는 모든 공개 URL의 HTTP 상태·콘텐츠 유형·SHA-256을 확인하고, 해당 응답으로 메뉴·썸네일·반응형 표시를 검증해야 합니다. 존재하지 않는 URL로 생성한 XML을 적용하면 메뉴와 썸네일이 작동하지 않습니다.

커밋 주소를 고정하므로 검증 후 파일 내용이 예고 없이 바뀌지 않습니다. 공통 자산을 수정해 새 버전을 배포할 때는 새 커밋으로 XML의 주소를 갱신하고 네 블로그에 적용합니다. 각 블로그의 위젯 설정을 유지하려면 해당 블로그에서 내보낸 XML을 입력으로 사용해야 합니다.
