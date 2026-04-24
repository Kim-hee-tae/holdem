# Texas Hold'em (Python)

텍사스 홀덤을 빠르게 실험할 수 있도록 다음 기능을 포함한 프로젝트입니다.

## 구현된 기능
- 프리플랍/플랍/턴/리버 **라운드별 베팅 시스템**
- **SB/BB 블라인드**, 칩 스택, 팟 처리
- 플레이어 액션: **폴드 / 체크 / 콜 / 레이즈**
- 사람 플레이어 **실시간 입력(콘솔)** 지원(`--interactive`)
- 올인 상황의 **사이드팟 분배** 처리
- 여러 판 진행 가능:
  - **캐시게임 모드**(파산 시 자동 리바이)
  - **토너먼트 모드**(탈락, 최종 1인 우승)
- 족보 판정 엔진(7장 중 최적 5장 선택)
- 간단한 **데스크톱 GUI(Tkinter)**: 핸드 단위 진행 로그 확인
- 간단한 **웹 GUI(Flask)**: 웹에서 핸드 진행 및 상태 확인

## CLI 실행
```bash
python holdem.py --mode cash --players 4 --hands 5
python holdem.py --mode tournament --players 6 --hands 100
python holdem.py --mode cash --players 4 --hands 3 --interactive
```

## GUI 실행
```bash
python holdem.py --gui
python holdem.py --web
```

## 테스트
```bash
python -m pytest -q
```

## 확장 아이디어
- 사람 플레이어의 실시간 입력(콘솔/웹)
- 사이드팟/정교한 올인 처리
- 웹 GUI를 FastAPI + SPA 구조로 고도화
