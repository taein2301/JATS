"""
Upbit 트레이딩 모듈

Upbit API를 통해 매매 전략을 실행합니다.
"""
import logging
import time
import datetime
from typing import Dict, List, Any, Optional, Tuple

from util.config import ConfigManager
from util.telegram_bot import TelegramNotifier
from upbit.api import UpbitAPI
from upbit.analyzer import UpbitAnalyzer


class UpbitTrader:
    """Upbit 트레이딩 클래스"""

    def __init__(self, api: UpbitAPI, analyzer: UpbitAnalyzer, 
                config: ConfigManager, logger: logging.Logger, notifier: TelegramNotifier):
        """
        UpbitTrader 초기화
        
        Args:
            api: Upbit API 인스턴스
            analyzer: Upbit 분석기 인스턴스
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
            notifier: 텔레그램 알림 인스턴스
        """
        self.api = api
        self.analyzer = analyzer
        self.config = config
        self.logger = logger
        self.notifier = notifier
        
        # 리스크 관리 설정 로드
        self.stop_loss_percent = config.get('risk.stop_loss_percent', 3)
        self.stop_loss_percent_high = config.get('risk.stop_loss_percent_high', 2)
        self.max_investment_per_trade = config.get('risk.max_investment_per_trade', 100000)
        self.max_daily_loss = config.get('risk.max_daily_loss', 50000)
        
        # 거래 내역 및 상태 관리
        self.positions = {}  # 보유 포지션
        self.trade_history = []  # 거래 내역
        self.daily_loss = 0  # 일일 손실 금액
        self.last_reset_date = datetime.datetime.now().date()

    def reset_daily_stats(self) -> None:
        """일일 통계 초기화"""
        today = datetime.datetime.now().date()
        if today > self.last_reset_date:
            self.daily_loss = 0
            self.last_reset_date = today
            self.logger.info("일일 통계가 초기화되었습니다.")

    def update_positions(self) -> None:
        """보유 포지션 업데이트"""
        try:
            accounts = self.api.get_account()
            
            # 포지션 초기화
            self.positions = {}
            
            for account in accounts:
                currency = account['currency']
                balance = float(account['balance'])
                avg_buy_price = float(account['avg_buy_price'])
                
                # KRW는 제외
                if currency == 'KRW':
                    continue
                    
                # 잔액이 있는 경우만 포지션에 추가
                if balance > 0:
                    market = f"KRW-{currency}"
                    self.positions[market] = {
                        'currency': currency,
                        'balance': balance,
                        'avg_buy_price': avg_buy_price,
                        'current_price': 0,  # 현재가는 나중에 업데이트
                        'profit_percent': 0  # 수익률은 나중에 계산
                    }
                    
            # 현재가 업데이트
            if self.positions:
                markets = list(self.positions.keys())
                tickers = self.api.get_ticker(markets)
                
                for ticker in tickers:
                    market = ticker['market']
                    if market in self.positions:
                        current_price = ticker['trade_price']
                        avg_buy_price = self.positions[market]['avg_buy_price']
                        
                        self.positions[market]['current_price'] = current_price
                        self.positions[market]['profit_percent'] = ((current_price - avg_buy_price) / avg_buy_price) * 100
                        
            self.logger.debug(f"포지션 업데이트 완료: {len(self.positions)}개 보유 중")
            
        except Exception as e:
            self.logger.error(f"포지션 업데이트 실패: {str(e)}")
            raise

    def check_stop_loss(self) -> None:
        """손절 조건 확인 및 실행"""
        for market, position in list(self.positions.items()):
            profit_percent = position['profit_percent']
            
            # 기본 손절 조건
            if profit_percent <= -self.stop_loss_percent:
                self.logger.warning(f"{market} 손절 조건 충족 (기본): {profit_percent:.2f}%")
                self.sell(market, position['balance'], reason="stop_loss")
                
            # 고점 대비 손절 조건 (향후 구현)
            # TODO: 고점 추적 및 고점 대비 손절 로직 구현

    def buy(self, market: str, amount: float) -> bool:
        """
        매수 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            amount: 매수 금액 (원)
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            # 리스크 관리: 거래당 최대 투자금액 제한
            if amount > self.max_investment_per_trade:
                amount = self.max_investment_per_trade
                self.logger.info(f"거래당 최대 투자금액 제한으로 매수 금액 조정: {amount:,.0f}원")
                
            # 매수 주문
            order = self.api.order_buy_market(market, amount)
            
            if 'uuid' in order:
                self.logger.info(f"{market} 매수 주문 성공: {amount:,.0f}원")
                
                # 주문 정보 가져오기
                time.sleep(1)  # 주문 처리 대기
                order_info = self.api.get_order(order['uuid'])
                
                # 거래 내역 추가
                trade = {
                    'market': market,
                    'type': 'buy',
                    'price': float(order_info.get('price', 0)),
                    'volume': float(order_info.get('volume', 0)),
                    'amount': amount,
                    'date': datetime.datetime.now(),
                    'uuid': order['uuid']
                }
                self.trade_history.append(trade)
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매수",
                    symbol=market,
                    price=float(order_info.get('price', 0)),
                    amount=float(order_info.get('volume', 0)),
                    total=amount
                )
                
                # 포지션 업데이트
                self.update_positions()
                
                return True
            else:
                self.logger.error(f"{market} 매수 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{market} 매수 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{market} 매수 중 오류 발생: {str(e)}")
            return False

    def sell(self, market: str, volume: float, reason: str = "manual") -> bool:
        """
        매도 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            volume: 매도 수량
            reason: 매도 이유 (manual, stop_loss, take_profit)
            
        Returns:
            bool: 매도 성공 여부
        """
        try:
            # 매도 주문
            order = self.api.order_sell_market(market, volume)
            
            if 'uuid' in order:
                self.logger.info(f"{market} 매도 주문 성공: {volume} 개, 이유: {reason}")
                
                # 주문 정보 가져오기
                time.sleep(1)  # 주문 처리 대기
                order_info = self.api.get_order(order['uuid'])
                
                # 거래 내역 추가
                trade = {
                    'market': market,
                    'type': 'sell',
                    'price': float(order_info.get('price', 0)),
                    'volume': volume,
                    'amount': float(order_info.get('price', 0)) * volume,
                    'date': datetime.datetime.now(),
                    'uuid': order['uuid'],
                    'reason': reason
                }
                self.trade_history.append(trade)
                
                # 수익률 계산
                profit_percent = 0
                if market in self.positions:
                    avg_buy_price = self.positions[market]['avg_buy_price']
                    current_price = float(order_info.get('price', 0))
                    profit_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100
                    
                    # 손실인 경우 일일 손실 금액 업데이트
                    if profit_percent < 0:
                        loss_amount = abs(current_price - avg_buy_price) * volume
                        self.daily_loss += loss_amount
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매도",
                    symbol=market,
                    price=float(order_info.get('price', 0)),
                    amount=volume,
                    total=float(order_info.get('price', 0)) * volume,
                    profit=profit_percent
                )
                
                # 포지션 업데이트
                self.update_positions()
                
                return True
            else:
                self.logger.error(f"{market} 매도 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{market} 매도 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{market} 매도 중 오류 발생: {str(e)}")
            return False

    def run_trading_strategy(self, markets: List[str]) -> None:
        """
        트레이딩 전략 실행
        
        Args:
            markets: 거래할 마켓 코드 목록
        """
        self.logger.info(f"트레이딩 전략 실행 시작: {len(markets)}개 마켓")
        
        # 일일 통계 초기화 확인
        self.reset_daily_stats()
        
        # 포지션 업데이트
        self.update_positions()
        
        # 손절 확인
        self.check_stop_loss()
        
        # 일일 손실 한도 확인
        if self.daily_loss >= self.max_daily_loss:
            self.logger.warning(f"일일 손실 한도 도달: {self.daily_loss:,.0f}원 / {self.max_daily_loss:,.0f}원")
            self.notifier.send_system_notification(
                title="일일 손실 한도 도달",
                message_body=f"일일 손실 한도에 도달하여 추가 매수를 중단합니다.\n"
                            f"현재 손실: {self.daily_loss:,.0f}원 / {self.max_daily_loss:,.0f}원"
            )
            return
        
        # 각 마켓 분석 및 매매 신호 확인
        for market in markets:
            try:
                # 이미 보유 중인 코인은 매수 신호 무시
                if market in self.positions:
                    continue
                    
                # 시장 분석
                analysis = self.analyzer.analyze_market(market)
                signals = analysis['signals']
                
                # 매수 신호 확인
                if signals['strong_buy']:
                    self.logger.info(f"{market} 강한 매수 신호 감지")
                    self.buy(market, self.max_investment_per_trade)
                elif signals['buy']:
                    self.logger.info(f"{market} 매수 신호 감지")
                    # 일반 매수 신호는 최대 투자금액의 50%만 사용
                    self.buy(market, self.max_investment_per_trade * 0.5)
                    
            except Exception as e:
                self.logger.error(f"{market} 분석 중 오류 발생: {str(e)}")
                continue
                
        self.logger.info("트레이딩 전략 실행 완료")

    def get_trading_summary(self) -> Dict[str, Any]:
        """
        트레이딩 요약 정보 반환
        
        Returns:
            Dict[str, Any]: 트레이딩 요약 정보
        """
        # 포지션 업데이트
        self.update_positions()
        
        # 총 자산 계산
        total_balance = 0
        total_value = 0
        
        try:
            # KRW 잔액 가져오기
            accounts = self.api.get_account()
            for account in accounts:
                if account['currency'] == 'KRW':
                    total_balance = float(account['balance'])
                    break
                    
            # 보유 코인 가치 계산
            for market, position in self.positions.items():
                coin_value = position['balance'] * position['current_price']
                total_value += coin_value
                
            # 총 자산
            total_assets = total_balance + total_value
            
            # 수익률 계산
            total_invested = 0
            total_current = 0
            for market, position in self.positions.items():
                invested = position['balance'] * position['avg_buy_price']
                current = position['balance'] * position['current_price']
                total_invested += invested
                total_current += current
                
            total_profit_percent = 0
            if total_invested > 0:
                total_profit_percent = ((total_current - total_invested) / total_invested) * 100
                
            # 오늘의 거래 내역
            today = datetime.datetime.now().date()
            today_trades = [trade for trade in self.trade_history if trade['date'].date() == today]
            
            # 요약 정보
            summary = {
                'total_balance': total_balance,
                'total_value': total_value,
                'total_assets': total_assets,
                'total_profit_percent': total_profit_percent,
                'positions_count': len(self.positions),
                'daily_loss': self.daily_loss,
                'today_trades_count': len(today_trades)
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"트레이딩 요약 정보 생성 중 오류 발생: {str(e)}")
            return {
                'error': str(e)
            } 