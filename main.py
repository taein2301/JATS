"""
트레이딩 봇 메인 모듈
"""
import sys
import traceback
from typing import List, Dict, Any

from util.config import ConfigManager
from util.logger import Logger
from util.telegram_bot import TelegramNotifier
from upbit.trader import UpbitTrader
# from kis.trader import KisTrader

def main():
    # 전역 변수로 선언하여 finally 블록에서 접근 가능하도록 함
    logger = None
    notifier = None
    platform = None
    env = None
    
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
            logger.warning("KIS 트레이더는 아직 구현되지 않았습니다.")
            notifier.send_message("⚠️ 미구현 기능\nKIS 트레이더는 아직 구현되지 않았습니다.")
            sys.exit(1)
        else:
            error_msg = f"지원하지 않는 플랫폼: {platform}"
            logger.error(error_msg)
            notifier.send_message("❌ 플랫폼 오류\n" + error_msg)
            sys.exit(1)
        
        # 트레이더 실행
        logger.info(f"{platform} 트레이더 시작 - 환경: {env}")
        notifier.send_message("🚀 트레이더 실행 시작\n" + f"{platform} 트레이더가 {env} 환경에서 시작되었습니다.")
        trader.run()
                
    except KeyboardInterrupt:
        if logger and notifier:
            logger.info("사용자에 의해 프로그램이 종료되었습니다.")
            notifier.send_message("⚠️ 프로그램 종료\n" + f"{platform} {env} 프로그램이 사용자에 의해 종료되었습니다.")
    except Exception as e:
        # 상세한 예외 정보 수집
        error_traceback = traceback.format_exc()
        error_message = f"프로그램 실행 중 오류 발생: {str(e)}"
        
        # 로그 기록
        if logger:
            logger.critical(f"{error_message}\n스택 트레이스:\n{error_traceback}")
        else:
            print(f"{error_message}\n스택 트레이스:\n{error_traceback}", file=sys.stderr)
        
        # 텔레그램 알림 전송
        if notifier:
            notifier.send_message("🔥 심각한 오류 발생\n" + f"{error_message}\n\n스택 트레이스 요약:\n{error_traceback.splitlines()[-3:]}")
        
        sys.exit(1)
    finally:
        # 프로그램 종료 시 항상 실행되는 코드
        if logger:
            logger.info("프로그램 종료")
        if notifier and platform and env:
            notifier.send_message("🔚 프로그램 종료\n" + f"{platform} {env} 프로그램이 종료되었습니다.")

if __name__ == "__main__":
    main() 