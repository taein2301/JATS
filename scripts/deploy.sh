#!/bin/bash
# JATS 배포 및 실행 스크립트

# 스크립트 실행 디렉토리로 이동
cd "$(dirname "$0")/.."

# 환경 변수 설정
PLATFORM=${1:-upbit}  # 기본값: upbit
ENV=${2:-prod}        # 기본값: prod
INTERVAL=${3:-60}     # 기본값: 60초

# 로그 디렉토리 생성
mkdir -p log

# 가상환경 활성화
if [ -d "jats_venv" ]; then
    source jats_venv/bin/activate
else
    echo "가상환경이 없습니다. 생성합니다..."
    python3 -m venv jats_venv
    source jats_venv/bin/activate
    pip install -r requirements.txt
fi

# 기존 프로세스 종료 (있다면)
pkill -f "python main.py" || echo "실행 중인 프로세스가 없습니다."

# 애플리케이션 실행
echo "JATS 시작: 플랫폼=$PLATFORM, 환경=$ENV, 간격=$INTERVAL초"
nohup python main.py --platform $PLATFORM --env $ENV --interval $INTERVAL > log/jats_$(date +%Y%m%d).log 2>&1 &

# 프로세스 ID 확인
PID=$!
echo "JATS가 PID $PID로 시작되었습니다."
echo "로그는 log/jats_$(date +%Y%m%d).log 파일에서 확인할 수 있습니다." 