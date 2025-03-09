"""
트레이딩 봇 메인 모듈
"""
import sys
from typing import List, Dict, Any

from util.config import ConfigManager
from util.logger import Logger
from util.telegram_bot import TelegramNotifier
from upbit.trader import UpbitTrader
# from kis.trader import KisTrader

def main():
    try:
        # 커맨드 라인 인자 확인
        if len(sys.argv) < 3:
            print("사용법: python main.py [platform] [env]")
            print("예시: python main.py upbit prod")
            sys.exit(1)
            
        platform = sys.argv[1]
        env = sys.argv[2]
        
        # 설정 로드
        config = ConfigManager(env)
        
        # 로거 초기화
        logger = Logger.get_logger('main', platform, config)
        
        # 텔레그램 알림 초기화
        notifier = TelegramNotifier(platform=platform, config=config, logger=logger)
        
        # 트레이더 초기화 및 실행
        if platform == 'upbit':
            trader = UpbitTrader(config=config, logger=logger, notifier=notifier)
        elif platform == 'kis':
            # trader = KisTrader(config=config, logger=logger, notifier=notifier)
            pass
        else:
            logger.error(f"지원하지 않는 플랫폼: {platform}")
            sys.exit(1)
        
        # 트레이더 실행
        notifier.send_system_notification("트레이더 실행 시작", f"{platform} 트레이더가 {env} 환경에서 시작되었습니다.")
        trader.run()
                
    except KeyboardInterrupt:
        notifier.send_system_notification("프로그램 종료", f"{platform} {env} 프로그램이 KeyboardInterrupt 예외로 종료되었습니다.")
        logger.info("사용자에 의해 프로그램이 종료되었습니다.")
    except Exception as e:
        # 기본 로거로 에러 출력 (예외 발생 위치 포함)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"프로그램 실행 중 오류 발생: {str(e)}\n스택 트레이스:\n{error_traceback}")
        notifier.send_system_notification("프로그램 실행 중 오류 발생", f"프로그램 실행 중 오류 발생: {str(e)}\n스택 트레이스:\n{error_traceback}")
        print(f"프로그램 실행 중 오류 발생: {str(e)}\n스택 트레이스:\n{error_traceback}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 