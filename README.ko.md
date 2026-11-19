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

[`uv`](https://docs.astral.sh/uv/)와 git이 필요하다. `token-ledger` CLI는 플러그인이 필요할 때 자기 폴더에서 설치한다.

**레포 설정 (한 사람이 한 번)**

```
/token-ledger:init
```

`token-ledger-out/`을 만들고, `.gitattributes`에 데이터를 생성 파일로 표시하고, 로컬 리포트를 무시하도록 하고, `CLAUDE.md`에 `## token-ledger` 섹션을 넣고, pre-commit hook을 설치한다. 새로 생긴 파일을 커밋한다.

**팀원**은 플러그인을 설치하고 Claude Code로 레포를 열면 된다. SessionStart hook이 CLI 설치를 안내하고 pre-commit hook을 설치한다.

**커밋할 때마다** `token-ledger-out/data/<팀원>/` 아래에 새 파일이 하나 생긴다. 이 레포에서 끝난 프롬프트마다 한 줄씩, 모델별 토큰, API 정가 기준 비용, 브랜치, 워크트리, 태그, 바뀐 파일 경로가 들어간다. 프롬프트 원문은 커밋되지 않는다. (예외 하나: 파일을 고치지 않은 내 프롬프트만으로 된 작업 단위는 그 프롬프트 앞부분을 보고 이름을 붙이므로, 이름에 질문 내용이 드러날 수 있다.) 커밋하는 순간 아직 진행 중인 프롬프트는 다음 커밋에 들어간다.

**명령**

| Claude Code에서 | CLI | 하는 일 |
|---|---|---|
| `/token-ledger:report` | `token-ledger report` | 새 프롬프트를 작업 단위로 묶고 `token-ledger-out/report.html`을 만든다 |
| `/token-ledger:tag <이름>` | `token-ledger tag <이름>` | 이후 프롬프트에 태그를 붙인다 (`off`로 끈다) |
| `/token-ledger:vocab` | `token-ledger vocab list\|merge\|rename\|ok` | 작업 단위 이름을 정리한다 |
| | `token-ledger summary --by branch` | 터미널에서 합계를 빠르게 본다 |
| | `token-ledger hook status\|install\|uninstall` | pre-commit hook을 관리한다 |

**작업 단위**는 자동으로 찾는다. 같은 파일을 고친 프롬프트, 한 세션에서 이어진 프롬프트, 같은 기능 브랜치의 프롬프트를 묶고, 새로 생긴 묶음마다 Claude Haiku(`claude -p --model haiku`)가 파일 경로, 브랜치, 세션 제목을 보고 짧은 이름을 붙인다. 이름은 `token-ledger-out/vocabulary.jsonl`에 저장되고 다시 쓰이므로, 한 묶음은 한 번만 이름을 붙인다. `token-ledger-out/config.json`에서 `"classify": false`로 두거나 `--no-classify`를 주면 모델 없이 파일 이름으로 이름을 붙인다.

**태그**는 사람이 직접 붙이는 라벨(릴리스, 실험 등)이고 작업 단위에는 영향을 주지 않는다.

**개인정보.** 커밋되는 기록에는 숫자, 브랜치, 태그, 세션 제목, 레포 기준 경로, 그리고 팀원의 `git config user.name`이 들어간다. 켜기 전에 팀에 알린다. 설정의 `"per_member": false`는 팀원별 보기를 숨기는 용도로 예약해 두었다.

## 상태

초기 뼈대 (v0.1.0). 첫 안정 버전 전까지는 호환되지 않는 변경이 있을 수 있다.
