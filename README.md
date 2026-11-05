# SPD 디자인 시스템 (비공식)

[Shattered Pixel Dungeon](https://github.com/00-Evan/shattered-pixel-dungeon) 소스 코드에서 추출한 디자인 토큰(색상, 글꼴 크기, 9-patch 프레임, 아이콘, 버프 아이콘, 간격, 모션)과 UI 컴포넌트 문서입니다. 값마다 원본 코드 줄 링크가 붙어 있습니다.

- 추출 기준: v4.0.2, 커밋 `57a4e06` (2026-10-06)
- 빌드 도구 없이 동작하는 정적 페이지입니다. `index.html`을 바로 열거나 GitHub Pages로 배포합니다.

## 토큰 다시 뽑기

```sh
git clone --depth 1 https://github.com/00-Evan/shattered-pixel-dungeon.git
python3 -I tools/extract.py shattered-pixel-dungeon
```

`tokens.json`과 `tokens.js`가 다시 만들어집니다. 정규식으로 뽑지 못하는 값(보조 색상, 컴포넌트 사양, 모션 상수)은 `app.js`에 출처 줄과 함께 직접 적혀 있습니다.

## 라이선스

`assets/`의 이미지와 `pixel_font.ttf`는 Shattered Pixel Dungeon(© Evan Debenham, 원작 Pixel Dungeon © Watabou)에서 가져왔고 GPLv3를 따릅니다. 이 저장소도 GPLv3입니다(`LICENSE`). 공식 문서가 아니며 개발자와 관련이 없습니다.

같은 부품으로 만든 빌드·장비 티어 사이트: https://mrtmi-0315.github.io/spd-builds/
