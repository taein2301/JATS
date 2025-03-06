# JATS (자동 트레이딩 시스템)

코인 및 증권 자동 매매 프로그램입니다. Upbit API와 한국투자증권 API를 활용하여 자동 매매 전략을 실행합니다.

## 주요 기능

- 실시간 시세 데이터 수집 (Upbit, 한국투자증권)
- 자동 매매 전략 실행
- 주문 관리 (시장가, 손절매, 이익 실현)
- 리스크 관리
- 로그 및 텔레그램 알림
- Streamlit 기반 모니터링 대시보드
- GitHub Actions를 통한 AWS EC2 자동 배포

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/yourusername/JATS.git
cd JATS
```

2. 가상환경 생성 및 활성화
```bash
python -m venv jats_venv
source jats_venv/bin/activate  # Linux/Mac
# 또는
jats_venv\Scripts\activate  # Windows
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

4. 설정 파일 생성
```bash
cp config/sample_config.yaml config/dev_config.yaml
# 설정 파일 편집
```

## 실행 방법

### 개발 환경
```bash
python main.py upbit dev  # Upbit 개발 환경
python main.py kis dev    # 한국투자증권 개발 환경
```

### 운영 환경
```bash
python main.py upbit prod  # Upbit 운영 환경
python main.py kis prod    # 한국투자증권 운영 환경
```

## 배포 방법

### GitHub Actions를 통한 AWS EC2 배포

이 프로젝트는 GitHub Actions를 사용하여 AWS EC2 인스턴스에 자동으로 배포됩니다.

1. GitHub 저장소에 다음 Secrets 설정:
   - `EC2_HOST`: EC2 인스턴스의 퍼블릭 IP 또는 도메인
   - `EC2_USERNAME`: SSH 접속 사용자명 (예: ubuntu, ec2-user)
   - `EC2_SSH_KEY`: EC2 인스턴스 접속용 SSH 개인 키
   - `EC2_PORT`: SSH 포트 (기본값: 22)
   - `EC2_DEPLOY_PATH`: EC2 인스턴스 내 프로젝트 경로
   - `EC2_VENV_PATH`: EC2 인스턴스 내 가상환경 경로
   - `TRADING_PLATFORM`: 사용할 트레이딩 플랫폼 (upbit 또는 kis)

2. 배포 트리거:
   - `main` 브랜치에 푸시하면 자동으로 배포가 시작됩니다.
   - GitHub 저장소의 Actions 탭에서 수동으로 워크플로우를 실행할 수도 있습니다.

3. 배포 과정:
   - 코드 체크아웃
   - Python 설정 및 의존성 설치
   - 테스트 실행
   - SSH를 통해 EC2 인스턴스에 접속
   - 코드 업데이트 및 의존성 설치
   - 기존 프로세스 종료 및 새 프로세스 시작

## 프로젝트 구조

```
├── .gitignore
├── README.md
├── .github
│   └── workflows
│       └── deploy-to-ec2.yml
├── config
│   ├── dev_config.yaml
│   ├── prod_config.yaml
│   └── sample_config.yaml
├── log
├── main.py
├── requirements.txt
├── upbit
│   ├── analyzer.py
│   ├── api.py
│   ├── trader.py
├── kis  
│   ├── analyzer.py
│   ├── api.py
│   ├── trader.py
└── util
    ├── config.py
    ├── logger.py
    ├── telegram_bot.py
```

## 기여 방법

1. 이슈 생성 또는 기존 이슈 확인
2. 브랜치 생성 (`git checkout -b feature/your-feature-name`)
3. 변경사항 커밋 (`git commit -m 'Add some feature'`)
4. 브랜치 푸시 (`git push origin feature/your-feature-name`)
5. Pull Request 생성

## 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다. 