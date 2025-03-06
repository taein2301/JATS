"""
한국투자증권 트레이딩 모듈

한국투자증권 API를 통해 매매 전략을 실행합니다.
"""
import logging
import time
import datetime
from typing import Dict, List, Any, Optional, Tuple

from util.config import ConfigManager
from util.telegram_bot import TelegramNotifier
from kis.api import KisAPI
from kis.analyzer import KisAnalyzer


class KisTrader:
    """한국투자증권 트레이딩 클래스"""

    def __init__(self, api: KisAPI, analyzer: KisAnalyzer, 
                config: ConfigManager, logger: logging.Logger, notifier: TelegramNotifier):
        """
        KisTrader 초기화
        
        Args:
            api: 한국투자증권 API 인스턴스
            analyzer: 한국투자증권 분석기 인스턴스
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

    def update_domestic_positions(self) -> None:
        """국내 주식 포지션 업데이트"""
        try:
            # 계좌 잔고 조회
            balance_info = self.api.get_account_balance()
            
            # 포지션 초기화
            self.positions = {}
            
            # 응답 데이터 추출
            output1 = balance_info.get('output1', {})
            output2 = balance_info.get('output2', [])
            
            # 예수금 정보
            self.cash_balance = int(output1.get('prvs_rcdl_excc_amt', 0))
            
            # 보유 종목 정보
            for item in output2:
                symbol = item.get('pdno', '')
                name = item.get('prdt_name', '')
                quantity = int(item.get('hldg_qty', 0))
                avg_price = int(item.get('pchs_avg_pric', 0))
                current_price = int(item.get('prpr', 0))
                
                if quantity > 0:
                    profit_percent = ((current_price - avg_price) / avg_price) * 100
                    
                    self.positions[symbol] = {
                        'symbol': symbol,
                        'name': name,
                        'quantity': quantity,
                        'avg_price': avg_price,
                        'current_price': current_price,
                        'profit_percent': profit_percent,
                        'market_type': 'domestic'
                    }
                    
            self.logger.debug(f"국내 주식 포지션 업데이트 완료: {len(self.positions)}개 보유 중")
            
        except Exception as e:
            self.logger.error(f"국내 주식 포지션 업데이트 실패: {str(e)}")
            raise

    def check_stop_loss(self) -> None:
        """손절 조건 확인 및 실행"""
        for symbol, position in list(self.positions.items()):
            profit_percent = position['profit_percent']
            
            # 기본 손절 조건
            if profit_percent <= -self.stop_loss_percent:
                self.logger.warning(f"{symbol} ({position['name']}) 손절 조건 충족 (기본): {profit_percent:.2f}%")
                
                if position['market_type'] == 'domestic':
                    self.sell_domestic_stock(symbol, position['quantity'], reason="stop_loss")
                else:
                    self.sell_overseas_stock(symbol, position['market'], position['quantity'], reason="stop_loss")

    def buy_domestic_stock(self, symbol: str, price: int, quantity: int) -> bool:
        """
        국내 주식 매수
        
        Args:
            symbol: 종목 코드 (예: 005930)
            price: 매수 가격 (시장가 주문시 0)
            quantity: 매수 수량
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            # 매수 주문
            order = self.api.order_domestic_stock(symbol, "02", quantity, price)
            
            # 응답 확인
            output = order.get('output', {})
            if 'KRX_FWDG_ORD_ORGNO' in output:
                self.logger.info(f"{symbol} 매수 주문 성공: {quantity}주, 가격: {price if price > 0 else '시장가'}")
                
                # 거래 내역 추가
                trade = {
                    'symbol': symbol,
                    'type': 'buy',
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity if price > 0 else 0,
                    'date': datetime.datetime.now(),
                    'market_type': 'domestic'
                }
                self.trade_history.append(trade)
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매수",
                    symbol=symbol,
                    price=price,
                    amount=quantity,
                    total=price * quantity if price > 0 else 0
                )
                
                # 포지션 업데이트
                self.update_domestic_positions()
                
                return True
            else:
                self.logger.error(f"{symbol} 매수 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{symbol} 매수 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{symbol} 매수 중 오류 발생: {str(e)}")
            return False

    def sell_domestic_stock(self, symbol: str, quantity: int, price: int = 0, reason: str = "manual") -> bool:
        """
        국내 주식 매도
        
        Args:
            symbol: 종목 코드 (예: 005930)
            quantity: 매도 수량
            price: 매도 가격 (시장가 주문시 0)
            reason: 매도 이유 (manual, stop_loss, take_profit)
            
        Returns:
            bool: 매도 성공 여부
        """
        try:
            # 매도 주문
            order = self.api.order_domestic_stock(symbol, "01", quantity, price)
            
            # 응답 확인
            output = order.get('output', {})
            if 'KRX_FWDG_ORD_ORGNO' in output:
                self.logger.info(f"{symbol} 매도 주문 성공: {quantity}주, 가격: {price if price > 0 else '시장가'}, 이유: {reason}")
                
                # 수익률 계산
                profit_percent = 0
                if symbol in self.positions:
                    position = self.positions[symbol]
                    avg_price = position['avg_price']
                    current_price = position['current_price']
                    profit_percent = position['profit_percent']
                    
                    # 손실인 경우 일일 손실 금액 업데이트
                    if profit_percent < 0:
                        loss_amount = abs(current_price - avg_price) * quantity
                        self.daily_loss += loss_amount
                
                # 거래 내역 추가
                trade = {
                    'symbol': symbol,
                    'type': 'sell',
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity if price > 0 else 0,
                    'date': datetime.datetime.now(),
                    'market_type': 'domestic',
                    'reason': reason,
                    'profit_percent': profit_percent
                }
                self.trade_history.append(trade)
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매도",
                    symbol=symbol,
                    price=price if price > 0 else self.positions[symbol]['current_price'],
                    amount=quantity,
                    total=price * quantity if price > 0 else self.positions[symbol]['current_price'] * quantity,
                    profit=profit_percent
                )
                
                # 포지션 업데이트
                self.update_domestic_positions()
                
                return True
            else:
                self.logger.error(f"{symbol} 매도 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{symbol} 매도 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{symbol} 매도 중 오류 발생: {str(e)}")
            return False

    def buy_overseas_stock(self, symbol: str, market: str, quantity: int, price: float = 0) -> bool:
        """
        해외 주식 매수
        
        Args:
            symbol: 종목 코드 (예: AAPL)
            market: 시장 코드 (예: NASD)
            quantity: 매수 수량
            price: 매수 가격 (시장가 주문시 0)
            
        Returns:
            bool: 매수 성공 여부
        """
        try:
            # 매수 주문
            order = self.api.order_overseas_stock(symbol, market, "2", quantity, price)
            
            # 응답 확인
            output = order.get('output', {})
            if 'ODNO' in output:
                self.logger.info(f"{symbol} ({market}) 매수 주문 성공: {quantity}주, 가격: {price if price > 0 else '시장가'}")
                
                # 거래 내역 추가
                trade = {
                    'symbol': symbol,
                    'market': market,
                    'type': 'buy',
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity if price > 0 else 0,
                    'date': datetime.datetime.now(),
                    'market_type': 'overseas'
                }
                self.trade_history.append(trade)
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매수",
                    symbol=f"{symbol} ({market})",
                    price=price,
                    amount=quantity,
                    total=price * quantity if price > 0 else 0
                )
                
                return True
            else:
                self.logger.error(f"{symbol} ({market}) 매수 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{symbol} ({market}) 매수 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{symbol} ({market}) 매수 중 오류 발생: {str(e)}")
            return False

    def sell_overseas_stock(self, symbol: str, market: str, quantity: int, 
                          price: float = 0, reason: str = "manual") -> bool:
        """
        해외 주식 매도
        
        Args:
            symbol: 종목 코드 (예: AAPL)
            market: 시장 코드 (예: NASD)
            quantity: 매도 수량
            price: 매도 가격 (시장가 주문시 0)
            reason: 매도 이유 (manual, stop_loss, take_profit)
            
        Returns:
            bool: 매도 성공 여부
        """
        try:
            # 매도 주문
            order = self.api.order_overseas_stock(symbol, market, "1", quantity, price)
            
            # 응답 확인
            output = order.get('output', {})
            if 'ODNO' in output:
                self.logger.info(f"{symbol} ({market}) 매도 주문 성공: {quantity}주, 가격: {price if price > 0 else '시장가'}, 이유: {reason}")
                
                # 거래 내역 추가
                trade = {
                    'symbol': symbol,
                    'market': market,
                    'type': 'sell',
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity if price > 0 else 0,
                    'date': datetime.datetime.now(),
                    'market_type': 'overseas',
                    'reason': reason
                }
                self.trade_history.append(trade)
                
                # 텔레그램 알림
                self.notifier.send_trade_notification(
                    action="매도",
                    symbol=f"{symbol} ({market})",
                    price=price,
                    amount=quantity,
                    total=price * quantity if price > 0 else 0
                )
                
                return True
            else:
                self.logger.error(f"{symbol} ({market}) 매도 주문 실패: {order}")
                return False
                
        except Exception as e:
            self.logger.error(f"{symbol} ({market}) 매도 중 오류 발생: {str(e)}")
            self.notifier.send_error_notification(f"{symbol} ({market}) 매도 중 오류 발생: {str(e)}")
            return False

    def run_domestic_trading_strategy(self, symbols: List[str]) -> None:
        """
        국내 주식 트레이딩 전략 실행
        
        Args:
            symbols: 거래할 종목 코드 목록
        """
        self.logger.info(f"국내 주식 트레이딩 전략 실행 시작: {len(symbols)}개 종목")
        
        # 일일 통계 초기화 확인
        self.reset_daily_stats()
        
        # 포지션 업데이트
        self.update_domestic_positions()
        
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
        
        # 각 종목 분석 및 매매 신호 확인
        for symbol in symbols:
            try:
                # 이미 보유 중인 종목은 매수 신호 무시
                if symbol in self.positions:
                    continue
                    
                # 종목 분석
                analysis = self.analyzer.analyze_domestic_stock(symbol)
                signals = analysis['signals']
                
                # 매수 신호 확인
                if signals['strong_buy']:
                    self.logger.info(f"{symbol} ({analysis['name']}) 강한 매수 신호 감지")
                    
                    # 매수 수량 계산 (최대 투자금액 / 현재가)
                    price = analysis['price']
                    quantity = int(self.max_investment_per_trade / price)
                    
                    if quantity > 0:
                        self.buy_domestic_stock(symbol, 0, quantity)  # 시장가 매수
                        
                elif signals['buy']:
                    self.logger.info(f"{symbol} ({analysis['name']}) 매수 신호 감지")
                    
                    # 일반 매수 신호는 최대 투자금액의 50%만 사용
                    price = analysis['price']
                    quantity = int((self.max_investment_per_trade * 0.5) / price)
                    
                    if quantity > 0:
                        self.buy_domestic_stock(symbol, 0, quantity)  # 시장가 매수
                    
            except Exception as e:
                self.logger.error(f"{symbol} 분석 중 오류 발생: {str(e)}")
                continue
                
        self.logger.info("국내 주식 트레이딩 전략 실행 완료")

    def run_overseas_trading_strategy(self, symbols: List[Dict[str, str]]) -> None:
        """
        해외 주식 트레이딩 전략 실행
        
        Args:
            symbols: 거래할 종목 정보 목록 (예: [{'symbol': 'AAPL', 'market': 'NASD'}])
        """
        self.logger.info(f"해외 주식 트레이딩 전략 실행 시작: {len(symbols)}개 종목")
        
        # 일일 통계 초기화 확인
        self.reset_daily_stats()
        
        # 일일 손실 한도 확인
        if self.daily_loss >= self.max_daily_loss:
            self.logger.warning(f"일일 손실 한도 도달: {self.daily_loss:,.0f}원 / {self.max_daily_loss:,.0f}원")
            self.notifier.send_system_notification(
                title="일일 손실 한도 도달",
                message_body=f"일일 손실 한도에 도달하여 추가 매수를 중단합니다.\n"
                            f"현재 손실: {self.daily_loss:,.0f}원 / {self.max_daily_loss:,.0f}원"
            )
            return
        
        # 각 종목 분석 및 매매 신호 확인
        for item in symbols:
            symbol = item['symbol']
            market = item['market']
            
            try:
                # 종목 분석
                analysis = self.analyzer.analyze_overseas_stock(symbol, market)
                signals = analysis['signals']
                
                # 매수 신호 확인
                if signals['strong_buy']:
                    self.logger.info(f"{symbol} ({market}, {analysis['name']}) 강한 매수 신호 감지")
                    
                    # 매수 수량 계산 (최대 투자금액 / 현재가)
                    price = analysis['price']
                    quantity = int(self.max_investment_per_trade / price)
                    
                    if quantity > 0:
                        self.buy_overseas_stock(symbol, market, quantity)  # 시장가 매수
                        
                elif signals['buy']:
                    self.logger.info(f"{symbol} ({market}, {analysis['name']}) 매수 신호 감지")
                    
                    # 일반 매수 신호는 최대 투자금액의 50%만 사용
                    price = analysis['price']
                    quantity = int((self.max_investment_per_trade * 0.5) / price)
                    
                    if quantity > 0:
                        self.buy_overseas_stock(symbol, market, quantity)  # 시장가 매수
                    
            except Exception as e:
                self.logger.error(f"{symbol} ({market}) 분석 중 오류 발생: {str(e)}")
                continue
                
        self.logger.info("해외 주식 트레이딩 전략 실행 완료")

    def get_trading_summary(self) -> Dict[str, Any]:
        """
        트레이딩 요약 정보 반환
        
        Returns:
            Dict[str, Any]: 트레이딩 요약 정보
        """
        # 포지션 업데이트
        self.update_domestic_positions()
        
        # 총 자산 계산
        total_value = 0
        
        try:
            # 보유 종목 가치 계산
            for symbol, position in self.positions.items():
                stock_value = position['quantity'] * position['current_price']
                total_value += stock_value
                
            # 총 자산
            total_assets = self.cash_balance + total_value
            
            # 수익률 계산
            total_invested = 0
            total_current = 0
            for symbol, position in self.positions.items():
                invested = position['quantity'] * position['avg_price']
                current = position['quantity'] * position['current_price']
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
                'cash_balance': self.cash_balance,
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