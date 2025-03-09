"""
텔레그램 알림 모듈

텔레그램 봇을 통해 알림 메시지를 전송합니다.
"""
import requests
import logging
import datetime
from typing import Optional, Dict, Any, Union, List

from util.config import ConfigManager


# 이모티콘 상수
UP_ARROW = "📈"         # 상승 추세
DOWN_ARROW = "📉"       # 하락 추세
MONEY_BAG = "💰"        # 수익/자금
CROSS_MARK = "❌"       # 실패/오류
CHART = "📊"           # 차트/분석
BELL = "🔔"            # 알림
ROCKET = "🚀"          # 급등/급상승
FIRE = "🔥"            # 인기/화제
STOPWATCH = "⏱️"       # 타이밍/시간
TARGET = "🎯"          # 목표/타겟
LIGHT_BULB = "💡"      # 아이디어/인사이트
GEAR = "⚙️"            # 설정/시스템
MAGNIFIER = "🔍"       # 검색/조사
CLOCK = "🕐"            # 시계
HOURGLASS = "⌛"        # 모래시계
ALARM_CLOCK = "⏰"      # 알람시계
LOCK = "🔒"            # 보안/잠금
FOUR_LEAF_CLOVER = "🍀"  # 행운의 네잎클로버
STAR = "⭐"             # 행운의 별
SPARKLES = "✨"         # 행운의 반짝임


class TelegramNotifier:
    """텔레그램 알림 클래스"""

    def __init__(self, platform: str, config: ConfigManager, logger: logging.Logger):
        """
        TelegramNotifier 초기화
        
        Args:
            platform: 플랫폼 (upbit 또는 kis)
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
        """
        self.platform = platform
        self.config = config
        self.logger = logger
        
        self.token = config.get('telegram.token')
        self.chat_id = config.get('telegram.chat_id')
        
        # 초기화 추가
        self.is_shutdown_message = False
        
        if not self.token or not self.chat_id:
            self.logger.warning("텔레그램 설정이 없습니다. 알림이 비활성화됩니다.")
            self.enabled = False
        else:
            self.enabled = True
            
        # 조용한 시간 설정
        self.quiet_start = config.get('telegram.quiet_hours.start', '22:00')
        self.quiet_end = config.get('telegram.quiet_hours.end', '08:00')

    def _is_quiet_time(self) -> bool:
        """
        현재 시간이 조용한 시간인지 확인
        
        Returns:
            bool: 조용한 시간이면 True, 아니면 False
        """
        # 프로그램 종료 알림은 항상 전송
        if self.is_shutdown_message:
            return False
            
        now = datetime.datetime.now().time()
        
        # 시간 문자열을 datetime.time 객체로 변환
        quiet_start = datetime.datetime.strptime(self.quiet_start, '%H:%M').time()
        quiet_end = datetime.datetime.strptime(self.quiet_end, '%H:%M').time()
        
        if quiet_start > quiet_end:
            return now >= quiet_start or now <= quiet_end
        else:
            return quiet_start <= now <= quiet_end

    def send_message(self, message: str, is_shutdown: bool = False) -> bool:
        """
        텔레그램으로 메시지 전송
        
        Args:
            message: 전송할 메시지
            is_shutdown: 프로그램 종료 메시지 여부
            
        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            self.logger.debug("텔레그램 알림이 비활성화되어 있습니다.")
            return False
            
        self.is_shutdown_message = is_shutdown
        
        # 조용한 시간에는 메시지 전송하지 않음 (종료 메시지 제외)
        if self._is_quiet_time() and not is_shutdown:
            self.logger.debug(f"조용한 시간 ({self.quiet_start}~{self.quiet_end})에는 알림을 전송하지 않습니다.")
            return False
            
        # 플랫폼 접두사 추가 - 일반 텍스트 형식 사용
        platform_name = self.platform
        if platform_name.lower() == 'kis':
            platform_name = '한국투자증권'

        formatted_message = f"[{platform_name}]\n{message}"
        
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload: Dict[str, Any] = {
                'chat_id': self.chat_id,
                'text': formatted_message
                # parse_mode 파라미터 제거 (일반 텍스트로 전송)
            }
            
            response = requests.post(url, json=payload, timeout=10)  # 타임아웃 추가
            
            if response.status_code == 200:
                return True
            else:
                self.logger.error(f"텔레그램 메시지 전송 실패: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.logger.exception(f"텔레그램 메시지 전송 중 네트워크 오류 발생: {str(e)}")
            return False
        except Exception as e:
            self.logger.exception(f"텔레그램 메시지 전송 중 오류 발생: {str(e)}")
            return False

    def send_trade_notification(self, action: str, symbol: str, price: float, 
                               amount: float, total: float, profit: Optional[float] = None) -> bool:
        """
        거래 알림 전송
        
        Args:
            action: 거래 유형 (매수/매도)
            symbol: 종목 심볼
            price: 거래 가격
            amount: 거래 수량
            total: 총 거래 금액
            profit: 수익률 (매도 시)
            
        Returns:
            bool: 전송 성공 여부
        """
        emoji = MONEY_BAG
        
        if action == "매수":
            title = f"{BELL} 매수 체결"
        elif action == "매도":
            title = f"{BELL} 매도 체결"
            if profit is not None:
                if profit > 0:
                    emoji = UP_ARROW
                else:
                    emoji = DOWN_ARROW
        else:
            title = f"{BELL} 거래 알림"
            
        message = f"{title}\n\n"
        message += f"종목: {symbol}\n"
        message += f"가격: {price:,.0f}원\n"
        message += f"수량: {amount:.4f}\n"
        message += f"총액: {total:,.0f}원\n"
        
        if profit is not None:
            message += f"수익률: {emoji} {profit:.2f}%\n"
        
        return self.send_message(message)

    def send_system_notification(self, title: str, message_body: str) -> bool:
        """
        시스템 알림 전송
        
        Args:
            title: 알림 제목
            message_body: 알림 내용
            
        Returns:
            bool: 전송 성공 여부
        """
        message = f"{GEAR} {title} {GEAR}\n"
        message += f"{message_body}\n"
        
        return self.send_message(message) 