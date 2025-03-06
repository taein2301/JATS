"""
JATS (자동 트레이딩 시스템) 메인 모듈

이 모듈은 프로그램의 진입점으로, 설정을 로드하고 자동 매매를 시작합니다.
"""
import os
import sys
import time
import argparse
import logging
import signal
from datetime import datetime
from typing import Dict, Any, List, Tuple, Callable, Optional

from util.config import load_config, ConfigManager
from util.logger import setup_logger
from util.telegram_bot import TelegramNotifier


class TradingManager:
    """트레이딩 관리 클래스"""
    
    def __init__(self, platform: str, env: str, interval: int):
        """
        TradingManager 초기화
        
        Args:
            platform: 거래 플랫폼 (upbit 또는 kis)
            env: 실행 환경 (dev 또는 prod)
            interval: 매매 전략 실행 간격 (초)
        """
        self.platform = platform
        self.env = env
        self.interval = interval
        
        # 설정 로드
        self.config = load_config(platform, env)
        
        # 로거 초기화
        self.logger = setup_logger('main', platform, self.config)
        self.logger.info(f"JATS 시작 (플랫폼: {platform}, 환경: {env})")
        
        # 텔레그램 알림 초기화
        self.notifier = TelegramNotifier(platform, self.config, self.logger)
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 플랫폼별 모듈 임포트
        self.API, self.Analyzer, self.Trader = self._import_platform_modules()
        
    def _signal_handler(self, sig, frame):
        """
        시그널 핸들러 (Ctrl+C 등)
        
        Args:
            sig: 시그널 번호
            frame: 현재 스택 프레임
        """
        self.logger.info("프로그램 종료 신호를 받았습니다. 종료합니다...")
        
        # 텔레그램 종료 알림
        self.notifier.send_message("프로그램이 종료되었습니다.", is_shutdown=True)
            
        sys.exit(0)
        
    def _import_platform_modules(self):
        """
        플랫폼별 모듈을 동적으로 임포트합니다.
        
        Returns:
            tuple: (API, Analyzer, Trader) 클래스
        """
        if self.platform == 'upbit':
            from upbit.api import UpbitAPI
            from upbit.analyzer import UpbitAnalyzer
            from upbit.trader import UpbitTrader
            return (UpbitAPI, UpbitAnalyzer, UpbitTrader)
        elif self.platform == 'kis':
            from kis.api import KisAPI
            from kis.analyzer import KisAnalyzer
            from kis.trader import KisTrader
            return (KisAPI, KisAnalyzer, KisTrader)
        else:
            raise ValueError(f"지원하지 않는 플랫폼: {self.platform}")
            
    def _format_summary_message(self, summary: Dict[str, Any]) -> str:
        """
        트레이딩 요약 정보를 메시지 형식으로 변환
        
        Args:
            summary: 트레이딩 요약 정보
            
        Returns:
            str: 포맷팅된 메시지
        """
        message = f"📊 트레이딩 요약 정보\n\n"
        
        # 플랫폼별 필드 이름 차이 처리
        if self.platform == 'upbit':
            cash_field = 'total_balance'
        else:  # kis
            cash_field = 'cash_balance'
            
        message += f"총 자산: {summary['total_assets']:,.0f}원\n"
        message += f"현금: {summary[cash_field]:,.0f}원\n"
        message += f"자산 가치: {summary['total_value']:,.0f}원\n"
        message += f"수익률: {summary['total_profit_percent']:.2f}%\n"
        message += f"보유 종목: {summary['positions_count']}개\n"
        message += f"오늘 거래: {summary['today_trades_count']}건\n"
        
        return message
            
    def run_trading(self):
        """
        트레이딩 실행
        """
        # API 클라이언트 생성
        api = self.API(self.config, self.logger)
        
        # 분석기 생성
        analyzer = self.Analyzer(api, self.config, self.logger)
        
        # 트레이더 생성
        trader = self.Trader(api, analyzer, self.config, self.logger, self.notifier)
        
        # 시작 알림
        platform_name = "Upbit" if self.platform == "upbit" else "한국투자증권"
        self.logger.info(f"{platform_name} 자동 매매를 시작합니다.")
        self.notifier.send_system_notification(
            title="자동 매매 시작",
            message_body=f"{platform_name} 자동 매매가 시작되었습니다."
        )
        
        # 거래 대상 목록 준비
        try:
            if self.platform == 'upbit':
                markets = api.get_market_all()
                trading_targets = [market['market'] for market in markets if market['market'].startswith('KRW-')]
                self.logger.info(f"거래 대상 마켓: {len(trading_targets)}개")
            else:  # kis
                # 거래할 종목 목록 (예시)
                domestic_symbols = ['005930', '000660', '035720']  # 삼성전자, SK하이닉스, 카카오
                overseas_symbols = [
                    {'symbol': 'AAPL', 'market': 'NASD'},  # 애플
                    {'symbol': 'MSFT', 'market': 'NASD'},  # 마이크로소프트
                    {'symbol': 'GOOGL', 'market': 'NASD'}  # 구글
                ]
                trading_targets = {
                    'domestic': domestic_symbols,
                    'overseas': overseas_symbols
                }
                self.logger.info(f"거래 대상: 국내 {len(domestic_symbols)}개, 해외 {len(overseas_symbols)}개")
        except Exception as e:
            self.logger.error(f"거래 대상 목록 가져오기 실패: {str(e)}")
            self.notifier.send_error_notification(f"거래 대상 목록 가져오기 실패: {str(e)}")
            return
        
        # 자동 매매 루프
        while True:
            try:
                # 플랫폼별 매매 전략 실행
                if self.platform == 'upbit':
                    trader.run_trading_strategy(trading_targets)
                else:  # kis
                    # 국내 주식 매매 전략 실행
                    trader.run_domestic_trading_strategy(trading_targets['domestic'])
                    
                    # 해외 주식 매매 전략 실행 (미국 장 시간에만)
                    now = datetime.now()
                    if 22 <= now.hour or now.hour <= 5:  # 한국 시간 기준 미국 장 시간 (대략)
                        trader.run_overseas_trading_strategy(trading_targets['overseas'])
                
                # 매 시간 정각에 요약 정보 전송
                now = datetime.now()
                if now.minute == 0 and now.second < 10:
                    summary = trader.get_trading_summary()
                    message = self._format_summary_message(summary)
                    self.notifier.send_message(message)
                    
                # 대기
                time.sleep(self.interval)
                
            except Exception as e:
                self.logger.error(f"매매 전략 실행 중 오류 발생: {str(e)}")
                self.notifier.send_error_notification(f"매매 전략 실행 중 오류 발생: {str(e)}")
                time.sleep(self.interval)


def parse_arguments():
    """
    명령행 인수를 파싱합니다.
    
    Returns:
        argparse.Namespace: 파싱된 인수
    """
    parser = argparse.ArgumentParser(description='JATS - 자동 트레이딩 시스템')
    parser.add_argument('platform', type=str, choices=['upbit', 'kis'],
                        help='거래 플랫폼 (upbit 또는 kis)')
    parser.add_argument('env', type=str, choices=['dev', 'prod'],
                        help='실행 환경 (dev 또는 prod)')
    parser.add_argument('--interval', type=int, default=60,
                        help='매매 전략 실행 간격 (초 단위, 기본값: 60)')
    return parser.parse_args()


def main():
    """
    프로그램 메인 함수
    """
    # 명령행 인수 파싱
    args = parse_arguments()
    
    try:
        # 트레이딩 매니저 생성 및 실행
        manager = TradingManager(args.platform, args.env, args.interval)
        manager.run_trading()
    except Exception as e:
        # 로거가 초기화되지 않았을 수 있으므로 표준 에러에 출력
        print(f"오류 발생: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main() 