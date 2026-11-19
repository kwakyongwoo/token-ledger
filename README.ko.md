# token-ledger

[English](README.md) | 한국어

Claude Code 토큰 사용량을 질문, 기능, 브랜치, 워크트리 단위로 기록하고 모델별, 기능별, 세션별로 묶어 보여주는 장부.

## 예시

![예시 리포트](examples/screenshot-light.jpg)

가상의 데이터(가상의 팀원 세 명, 프롬프트 140개)로 만든 리포트. [`examples/report.html`](examples/report.html)을 브라우저로 열면 필터와 묶기 버튼을 써볼 수 있고, [`examples/token-ledger-out/`](examples/token-ledger-out/)에서 실제로 커밋되는 것(프롬프트 원문 없는 기록, 작업 단위, 단어장)을 볼 수 있다. 다시 만들려면 `python3 examples/make_example.py`.

## 설치

```
/plugin marketplace add kwakyongwoo/token-ledger
/plugin install token-ledger@token-ledger
```

## 사용법

TODO: 이 플러그인이 추가하는 스킬, 명령, 훅과 실행 방법, 어떤 결과가 나오는지, 처음 쓰기 전에 필요한 설정을 적는다.

## 상태

초기 뼈대 (v0.1.0). 첫 안정 버전 전까지는 호환되지 않는 변경이 있을 수 있다.
