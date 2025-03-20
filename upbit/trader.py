"""
Upbit 트레이딩 시스템 모듈
"""
from typing import Dict, List, Optional, Any, Tuple
import time
import schedule
from datetime import datetime, timedelta
import traceback

from upbit.api import UpbitAPI
from upbit.analyzer import UpbitAnalyzer


class UpbitTrader:
    """
    Upbit 트레이딩을 담당하는 클래스
    """
    
    def __init__(self, config: Any, logger: Any, notifier: Any):
        """
        Upbit 트레이더 초기화
        
        Args:
            config: 설정 객체
            logger: 로거 객체
            notifier: 알림 객체
        """
        self.config = config
        self.logger = logger
        self.notifier = notifier
        
        # API 초기화
        upbit_config = config.get('upbit', {})
        self.access_key = upbit_config.get('access_key', '')
        self.secret_key = upbit_config.get('secret_key', '')
        self.server_url = upbit_config.get('server_url', 'https://api.upbit.com')
        
        # API 클라이언트 초기화 (notifier 전달)
        self.api = UpbitAPI(
            access_key=self.access_key,
            secret_key=self.secret_key,
            server_url=self.server_url,
            logger=self.logger,
            notifier=self.notifier
        )
        
        # 분석기 초기화
        self.analyzer = UpbitAnalyzer(self.api, logger=self.logger, config=self.config)
        
        # 포지션 정보 초기화
        # 포지션 정보
        self.position = {
            'market': '',           # 마켓
            'before_market': '',    # 이전 마켓
            'entry_price': 0,       # 진입 가격
            'current_price': 0,     # 현재 가격
            'amount': 0,            # 수량
            'top_price': 0,         # 최고 가격
            'value_krw': 0,         # KRW 가치
            'profit_pct': 0,        # 수익률
            'entry_time': None,     # 진입 시간
            'krw_balance': 0        # KRW 잔고
        }

        # 타이머 초기화
        self.last_check_time = {
            '10s': datetime.now(),
            '1m': datetime.now(),
            '5m': datetime.now()
        }
        
        # 초기 코인 정보를 BTC로 초기화
        self.top_volume_coins = {
            'KRW-BTC': {
                'korean_name': '비트코인',
                'english_name': 'BTC',
                'trade_price': 0,
                'volume_24h': 0,
                'trade_price_24h': 0, 
                'change': '0',
                'change_rate': 0
            }
        } 

        # 승률 관련 정보 초기화
        self.trading_stats = {
            'wins': 0,           # 수익 거래 횟수
            'losses': 0,         # 손실 거래 횟수
            'total_trades': 0,   # 총 거래 횟수
            'win_rate': 0.0,     # 승률
            'last_reset': datetime.now()  # 마지막 초기화 시간
        }
        
        # 초기 승률 통계 출력
        self.log_win_rate()

    def run(self):
        """
        트레이딩 시스템의 메인 실행 루프
        
        10초/1분/5분/1시간 주기로 다양한 작업 수행
        포지션 체크, 매매 시그널 분석, 리포트 생성 등
        """
        
        try:
            # 초기 포지션 체크
            self.check_position()
            self.dis_portfolio()
            # 거래량 상위 코인 갱신
            self.check_signal()
            
            schedule.every().day.at("06:30").do(self.dis_portfolio)
            schedule.every().day.at("09:00").do(self.dis_portfolio)
            schedule.every().day.at("11:20").do(self.dis_portfolio)
            schedule.every().day.at("17:30").do(self.dis_portfolio)
            schedule.every().day.at("21:00").do(self.dis_portfolio)
            schedule.every().day.at("21:52").do(self.dis_portfolio)
            
            # 메인 루프
            while True:
                now = datetime.now()
                
                # 스케줄 실행
                schedule.run_pending()
                
                # 아침 6시에 승률 통계 초기화
                if now.hour == 6 and now.minute == 0 and (now - self.trading_stats['last_reset']).total_seconds() >= 3600:
                    self.reset_win_rate()
                
                if (now - self.last_check_time['10s']).total_seconds() >= 10:
                    self.last_check_time['10s'] = now
                    # 포지션 체크
                    self.check_position()

                    # 매수/매도 시그널 체크
                    self.check_signal()
                    
                if (now - self.last_check_time['1m']).total_seconds() >= 60:
                    self.last_check_time['1m'] = now
                    self.get_top_volume_interval(interval="1m", count=2)

                
                if (now - self.last_check_time['5m']).total_seconds() >= 300:
                    self.last_check_time['5m'] = now
                    # 비정상 주문 취소
                    self.cancel_abnormal_orders()
                    
                # 잠시 대기
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("사용자에 의해 트레이더가 중지되었습니다.")
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"트레이더 실행 중 오류 발생: {str(e)}\n{error_traceback}")
    
    def buy(self, market: str):
        """
        지정된 마켓에 시장가 매수 주문 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
        """
        
        try:
            # 이미 포지션이 있는 경우 매수하지 않음
            if self.position['market']:
                self.logger.warning(f"이미 {self.position['market']} 포지션이 있어 {market} 매수를 진행하지 않습니다.")
                return
            
            # 매수 금액 계산 (잔고의 90%, 수수료 고려)
            buy_amount = self.position['krw_balance'] * 0.9
            if buy_amount < 5000:  # 최소 주문 금액
                self.logger.warning(f"KRW 잔고 부족: {self.position['krw_balance']}원")
                return
                
            # 시장가 매수 주문
            order_result = self.api.run_order(market=market, side='bid', price=buy_amount)
            
            if not order_result or 'uuid' not in order_result:
                self.logger.error(f"{market} 매수 주문 실패: {order_result}")
                return
                
            order_uuid = order_result['uuid']
            
            for _ in range(20):
                time.sleep(1)
                order_status = self.api.get_order_status(order_uuid)
                
                if order_status.get('state') == 'done':
                    # 매수 완료
                    executed_volume = float(order_status.get('executed_volume', 0))
                    avg_price = float(order_status.get('avg_price', 0))
                    
                    # 마켓 한글 이름 가져오기
                    market_korean_name = self.api.get_market_name().get(market, market)
                    self.logger.critical(f"{market}({market_korean_name}) 매수 완료: {avg_price:,.0f}원")
                    self.notifier.send_message(
                        f"{market}({market_korean_name}) 매수 완료\n가격: {avg_price:,.0f}원\n"
                    )
                    
                    return
            
            # 20초 이내에 체결되지 않은 경우
            market_korean_name = self.api.get_market_name().get(market, market)
            self.logger.error(f"{market}({market_korean_name}) 매수 주문이 20초 이내에 체결되지 않았습니다.")
            self.notifier.send_message("매수 오류\n" + f"{market}({market_korean_name}) 매수 주문이 20초 이내에 체결되지 않았습니다.")
            
        except Exception as e:
            self.logger.error(f"{market} 매수 중 오류 발생: {str(e)}")
            self.notifier.send_message("매수 오류\n" + f"{market} 매수 중 오류 발생: {str(e)}")
    
    def sell(self, market: str):
        """
        지정된 마켓의 보유 수량 전체 시장가 매도
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
        """
        
        try:
            # 포지션 확인
            if not self.position['market'] or self.position['market'] != market:
                self.logger.warning(f"{market} 포지션이 없어 매도를 진행하지 않습니다.")
                return
                
            # 보유 수량 확인
            amount = self.position['amount']
            if amount <= 0:
                self.logger.warning(f"{market} 보유 수량이 없습니다.")
                return
                
            # 시장가 매도 주문
            order_result = self.api.run_order(market=market, side='ask', volume=amount)
            
            if not order_result or 'uuid' not in order_result:
                self.logger.error(f"{market} 매도 주문 실패: {order_result}")
                return
                
            order_uuid = order_result['uuid']
            
            # 주문 상태 확인 (최대 10초 대기)
            for _ in range(10):
                time.sleep(1)
                order_status = self.api.get_order_status(order_uuid)
                
                if order_status.get('state') == 'done':

                    # 매도 완료
                    executed_volume = float(order_status.get('executed_volume', 0))
                    
                    # 실제 체결 가격 가져오기
                    trades = order_status.get('trades', [])
                    if trades and len(trades) > 0:
                        current_price = float(trades[0].get('price', 0))
                    else:
                        current_price = 0


                    # 매도 총액 계산
                    total_value = float(current_price) * executed_volume
                    
                    # 매수 총액 계산 
                    buy_value = float(self.position['entry_price']) * executed_volume
                    
                    # 수수료 계산 (소수점 절삭)
                    fee = int(float(order_status.get('paid_fee', 0)))
                    
                    # 실현손익 = 매도총액 - 매수총액 - 수수료
                    realized_profit = int(total_value - buy_value - fee)
                    
                    # 수익률 = (실현손익 / 매수총액) * 100
                    profit_rate = (realized_profit / buy_value) * 100 if buy_value > 0 else 0
                    
                    # 이모지 추가
                    emoji = "📈" if profit_rate > 0 else "📉"
                                

                    # 수익률 계산
                    # 진입가격과 평균 매도가격으로 수익률 계산
                    entry_price = self.position['entry_price']
                    profit_pct = (current_price - entry_price) / entry_price * 100
                    
                    # 승률 통계 업데이트
                    if profit_pct > 0:
                        self.trading_stats['wins'] += 1
                    else:
                        self.trading_stats['losses'] += 1
                    self.trading_stats['total_trades'] += 1
                    self.update_win_rate()
                    
                    # 매수 시간과 매도 시간 계산하여 보유 시간 계산
                    if self.position['entry_time']:
                        sell_time = datetime.now()
                        holding_duration = sell_time - self.position['entry_time']
                        
                        # 보유 시간을 시간, 분, 초로 변환
                        days = holding_duration.days
                        hours, remainder = divmod(holding_duration.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        # 보유 시간 문자열 생성
                        holding_time_str = ""
                        if days > 0:
                            holding_time_str += f"{days}일 "
                        if hours > 0:
                            holding_time_str += f"{hours}시간 "
                        if minutes > 0:
                            holding_time_str += f"{minutes}분 "
                        holding_time_str += f"{seconds}초"
                        
                        self.logger.critical(f"{market} 매도 완료 {emoji} 수익률: {profit_pct:.2f}% 보유시간: {holding_time_str} 실현손익: {realized_profit}원")
                    # 로그에 수익률 계산 과정 기록
                    self.notifier.send_message(
                        f"{market}({self.api.get_market_name().get(market, market)}) 매도 완료\n{emoji} 수익률: {profit_pct:.2f}%\n보유시간: {holding_time_str}\n실현손익: {realized_profit:,}원\n현재 승률: {self.trading_stats['win_rate']:.2f}% ({self.trading_stats['wins']}승 {self.trading_stats['losses']}패)"
                    )
                    
                    return
            
            # 10초 이내에 체결되지 않은 경우
            market_name = self.api.get_market_name().get(market, market)
            self.logger.warning(f"{market}({market_name}) 매도 주문이 10초 이내에 체결되지 않았습니다.")
            self.notifier.send_message("매도 오류\n" + f"{market}({market_name}) 매도 주문이 10초 이내에 체결되지 않았습니다.")

        except Exception as e:
            self.logger.error(f"{market} 매도 중 오류 발생: {str(e)}")
            self.notifier.send_message("매도 오류\n" + f"{market} 매도 중 오류 발생: {str(e)}")
    
    def cancel_abnormal_orders(self, market: Optional[str] = None):
        """
        미체결된 비정상 주문들 일괄 취소
        
        Args:
            market: 특정 마켓 지정 시 해당 마켓만 취소
        """
        try:
            # 대기 중인 주문 조회
            wait_orders = self.api.get_wait_order(market)
            
            if not wait_orders:
                return
                
            # 주문 취소
            for order in wait_orders:
                uuid = order.get('uuid')
                if uuid:
                    self.logger.info(f"미체결 주문 취소: {order.get('market')} - {uuid}")
                    self.api.set_order_cancel(uuid)
                    
        except Exception as e:
            self.logger.error(f"주문 취소 중 오류 발생: {str(e)}")
    
    def check_signal(self):
        """
        매수/매도 시그널 체크 및 거래 실행
        
        포지션 있을 때는 매도 시그널만 체크
        포지션 없을 때는 매수 시그널 체크
        """
        # 포지션이 있는 경우 매도 시그널 체크
        if self.position['market']:
            if self.analyzer.check_stop_loss_condition(self.position):
                self.sell(self.position['market'])
                self.check_position()
            return

        else:
            # 포지션이 없는 경우 매수 시그널 체크
            # 거래량 상위 코인 대상으로 매수 시그널 체크
            for market in self.top_volume_coins.keys(): 
                time.sleep(0.1)
                if self.analyzer.run_trading_analyzer(market):
                    # 마켓 한글 이름 가져오기
                    market_korean_name = self.api.get_market_name().get(market, market)
                    self.logger.info(f"{market}({market_korean_name}) 매수 시그널 발생")
                    # 이전 마켓과 동일한 경우 매수 스킵
                    if market == self.position['before_market']:
                        self.logger.warning(f"이전 포지션과 동일한 {market}({market_korean_name})은 매수를 스킵합니다.")
                        continue
                    self.buy(market)
                    self.check_position()
                    break  # 한 번에 하나의 코인만 매수
            else:
                self.logger.info("모든 코인 검사 완료: 매수 시그널이 발생하지 않았습니다.")
            # 변동율이 가장 높은 코인 가져오기
            try:
                highest_change_coin = None
                highest_change_rate = -100.0  # 초기값을 충분히 낮게 설정
                
                for market, coin_info in self.top_volume_coins.items():
                    change_rate = coin_info.get('change_rate', 0)
                    
                    # 변동율이 더 높은 코인 찾기
                    if change_rate > highest_change_rate:
                        highest_change_rate = change_rate
                        highest_change_coin = market
                
                if highest_change_coin:
                    market_korean_name = self.api.get_market_name().get(highest_change_coin, highest_change_coin)
                    self.logger.info(f"변동율 최고 코인: {highest_change_coin}({market_korean_name}) - 변동율: {highest_change_rate:.2f}%")
                    # 이전 마켓과 동일한 경우 매수 스킵
                    if highest_change_coin == self.position['before_market']:
                        market_korean_name = self.api.get_market_name().get(highest_change_coin, highest_change_coin)
                        self.logger.warning(f"이전 포지션과 동일한 {highest_change_coin}({market_korean_name})은 매수를 스킵합니다.")
                    else:
                        self.buy(highest_change_coin)
                        self.check_position()
            except Exception as e:
                self.logger.error(f"변동율 최고 코인 확인 중 오류 발생: {str(e)}")
            self.logger.info("=====================================")
        return

    def check_position(self) -> bool:
        """
        현재 보유 중인 포지션 상태 확인
        앱이나 다른 곳에서의 변화 반영
        
        Returns:
            bool: 매수 포지션이면 True, 매도 포지션이면 False
        """
        try:
            # 잔고 조회
            balances = self.api.get_balances()
            
            # 총 KRW 초기화
            total_krw = 0

            if len(balances) == 1 and balances[0]['currency'] == 'KRW':
                # 기존에 다른 코인을 가지고 있었는지 확인
                if self.position.get('market'):
                    market_korean_name = self.api.get_market_name().get(self.position['market'], self.position['market'])
                    self.logger.info(f"기존 포지션 정리: {market_korean_name} > KRW") 
                    self.position['before_market'] = self.position['market']

                # 기존 position 값을 유지하면서 필요한 값만 초기화
                self.position['market'] = ''
                self.position['entry_price'] = 0
                self.position['current_price'] = 0
                self.position['amount'] = 0
                self.position['top_price'] = 0
                self.position['value_krw'] = 0
                self.position['profit_pct'] = 0
                self.position['entry_time'] = None
                self.position['krw_balance'] = float(balances[0]['balance'])
                return False  # 매도 포지션 (KRW만 보유)
            else: 
                # 각 자산별 정보 계산
                for balance in balances:
                    currency = balance.get('currency')
                    balance_amount = float(balance.get('balance', 0))
                    
                    if currency == 'KRW':
                        # KRW는 그대로 합산
                        total_krw += balance_amount
                        self.position['krw_balance'] = total_krw
                    else:
                        market = f"KRW-{currency}"
                        current_price_info = self.api.get_current_price(market)
                        current_price = float(current_price_info.get('trade_price', 0))
                        avg_buy_price = float(balance.get('avg_buy_price', 0))
                        
                        # 평가금액 및 수익률 계산
                        value_krw = balance_amount * current_price
                        profit_pct = (current_price - avg_buy_price) / avg_buy_price * 100 if avg_buy_price > 0 else 0
                        total_value = balance_amount * avg_buy_price

                        total_krw += value_krw
                        
                        if not self.position['market'] or self.position['market'] != market:
                            market_korean_name = self.api.get_market_name()[market]
                            # 기존 포지션 정보 저장
                            self.position['before_market'] = self.position.get('market', '')
                            
                            # 포지션 정보 업데이트
                            self.position['market'] = market
                            self.position['entry_price'] = avg_buy_price
                            self.position['current_price'] = current_price
                            self.position['amount'] = balance_amount
                            self.position['top_price'] = avg_buy_price  # 초기 최고가는 매수가로 설정
                            self.position['value_krw'] = value_krw
                            self.position['profit_pct'] = profit_pct
                            self.position['entry_time'] = datetime.now()
                            self.position['krw_balance'] = total_krw
                            self.logger.info(f"포지션 진입: {market_korean_name} 평가금액: {total_value:,.0f}원 ")
                            return True  # 매수 포지션 (코인 보유)
                        else:
                            self.position['current_price'] = current_price
                            self.position['value_krw'] = value_krw
                            self.position['profit_pct'] = profit_pct
                            self.position['krw_balance'] = total_krw
                            if current_price > self.position['top_price']:
                                market_korean_name = self.api.get_market_name()[market]
                                self.logger.info(f"최고가 갱신: {market_korean_name} - {self.position['top_price']}원 -> {current_price}원 DIFF {current_price - self.position['top_price']}원")
                                self.position['top_price'] = current_price
                            return True  # 매수 포지션 (코인 보유)
                
                # 코인을 찾지 못했지만 KRW는 있는 경우
                return False  # 매도 포지션 (코인 없음)
                    
        except Exception as e:
            self.logger.error(f"포지션 체크 중 오류 발생: {str(e)}")
            return False  # 오류 발생 시 기본적으로 매도 포지션으로 간주

    def get_top_volume_interval(self, interval: str = "10min", count: int = 5):
        """
        최근 10분간 거래량 상위 코인 조회
        거래대금 기준 정렬 및 변동률 분석
        """
        start_time = datetime.now()
        self.logger.debug(f"거래량 상위 코인 조회 시작: {start_time}")
        
        try:
            # 마켓 정보 조회
            markets = self.api.get_market_info()
            #self.logger.info(f"조회할 마켓 코드 목록: {markets}")
            market_codes = [market['market'] for market in markets]
            
            # 거래량 정보 저장할 리스트
            volume_data = []
            
            # 각 마켓별 거래량 조회
            for market in market_codes:  
                try:
                    #candles = self.api.get_candles(market, interval="1m", count=10)
                    candles = self.api.get_candles(market, interval=interval, count=count)
                    if not candles:
                        continue
                        
                    # 거래대금 합산
                    total_volume_krw = sum(float(candle['candle_acc_trade_price']) for candle in candles)
                    
                    # 가격 변동률 계산
                    first_price = float(candles[-1]['opening_price'])
                    last_price = float(candles[0]['trade_price'])
                    price_change_pct = (last_price - first_price) / first_price * 100
                    
                    volume_data.append({
                        'market': market,
                        'volume_krw': total_volume_krw,
                        'price_change_pct': price_change_pct,
                        'current_price': last_price
                    })
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"{market} 거래량 조회 중 오류: {str(e)}")
            
            # 상위 10개 코인 저장
            # 거래량이 1억 이상인 코인만 필터링
            filtered_volume_data = [data for data in volume_data if data['volume_krw'] >= 100000000]
            # 필터링된 코인 중 상승률 기준으로 정렬
            filtered_volume_data.sort(key=lambda x: x['price_change_pct'], reverse=True)
            # 상위 10개 코인만 선택
            top_10_coins = filtered_volume_data[:10]

            # top_volume_coins 초기화 - 기존 데이터 삭제 후 새로운 데이터로 갱신
            self.top_volume_coins = {}
            # 거래량 상위 코인 상세 정보 로깅
            if volume_data:
                self.logger.info(f"===== 거래량 상위 코인 상세 정보 {interval} : {count} =====")
                for idx, data in enumerate(top_10_coins, 1):
                    market_name = next((m['korean_name'] for m in markets if m['market'] == data['market']), data['market'])
                    change_emoji = "📈" if data['price_change_pct'] > 0 else "📉"
                    self.logger.info(
                        f"{idx:2d}. {data['market']:10s} {market_name:15s} | "
                        f"거래대금: {data['volume_krw']:,.0f}원 | "
                        f"현재가: {data['current_price']:,.0f}원 | "
                        f"{change_emoji} 변동률: {data['price_change_pct']:+.2f}%"
                    )
                    self.top_volume_coins[data['market']] = {
                        'korean_name': market_name,
                        'english_name': data['market'].split('-')[1],  
                        'trade_price': data['current_price'],
                        'volume': data['volume_krw'], 
                        'change_rate': data['price_change_pct']
                    }
    
                self.logger.info("=====================================")
        except Exception as e:
            self.logger.error(f"거래량 상위 코인 조회 중 오류 발생: {str(e)}")
        
        end_time = datetime.now()
        elapsed_time = (end_time - start_time).total_seconds()
        self.logger.debug(f"거래량 상위 코인 조회 종료: {end_time}, 소요시간: {elapsed_time:.2f}초")


    def dis_portfolio(self):
        """
        포트폴리오 상세 분석 및 수익률 계산
        코인별 수익률, 보유 수량 평가금액 등 계산
        """
        try:
            # 현재 시각 추가
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            summary = f"({current_time}) 포트폴리오 현황 \n"
            summary += f"KRW: {self.position['krw_balance']:,.0f}원\n"
            
            # 포지션이 있는 경우에만 상세 정보 표시
            if self.position['market']:
                market_korean_name = self.api.get_market_name()[self.position['market']]
                summary += f"{market_korean_name}\n"
                summary += f"평가금액: {self.position['value_krw']:,.0f}원\n"
                summary += f"수익률: {self.position['profit_pct']:.2f}%\n"
            else:
                summary += "현재 보유 중인 코인이 없습니다.\n"
            
            # 승률 정보 추가
            summary += f"\n📊 오늘의 승률: {self.trading_stats['win_rate']:.2f}%\n"
            summary += f"총 {self.trading_stats['total_trades']}건 : {self.trading_stats['wins']}승 {self.trading_stats['losses']}패\n"
            
            # 알림 전송
            self.logger.info(summary)
            self.notifier.send_message(summary)
            
        except Exception as e:
            self.logger.error(f"포트폴리오 분석 중 오류 발생: {str(e)}")

    # 승률 관련 새로운 메소드들
    def update_win_rate(self):
        """
        승률 통계 업데이트
        """
        if self.trading_stats['total_trades'] > 0:
            self.trading_stats['win_rate'] = (self.trading_stats['wins'] / self.trading_stats['total_trades']) * 100
        else:
            self.trading_stats['win_rate'] = 0.0
        
        # 승률 로그 출력
        self.log_win_rate()
    
    def log_win_rate(self):
        """
        현재 승률 통계를 로그에 기록
        """
        stats = self.trading_stats
        self.logger.info(
            f"📊 트레이딩 승률: {stats['win_rate']:.2f}% ({stats['wins']}승 {stats['losses']}패, 총 {stats['total_trades']}건)"
        )
    
    def reset_win_rate(self):
        """
        승률 통계 초기화 (아침 6시에 호출)
        """
        now = datetime.now()
        
        # 어제 승률 요약
        yesterday_stats = self.trading_stats.copy()
        
        # 승률 정보 초기화
        self.trading_stats = {
            'wins': 0,
            'losses': 0,
            'total_trades': 0,
            'win_rate': 0.0,
            'last_reset': now
        }
        
        # 전날 통계 로그 및 알림
        if yesterday_stats['total_trades'] > 0:
            self.logger.critical(
                f"🔄 일일 승률 초기화! 어제 승률: {yesterday_stats['win_rate']:.2f}% ({yesterday_stats['wins']}승 {yesterday_stats['losses']}패, 총 {yesterday_stats['total_trades']}건)"
            )
            self.notifier.send_message(
                f"🔄 일일 승률 초기화!\n어제 승률: {yesterday_stats['win_rate']:.2f}%\n{yesterday_stats['wins']}승 {yesterday_stats['losses']}패 (총 {yesterday_stats['total_trades']}건)"
            )
        else:
            self.logger.info("🔄 일일 승률 초기화 완료 (어제 거래 없음)")
            self.notifier.send_message("🔄 일일 승률 초기화 완료 (어제 거래 없음)") 

    def scheduled_portfolio_report(self, time):
        """
        스케줄에 따라 실행되는 포트폴리오 분석 래퍼 함수
        
        Args:
            time: 실행 예약 시간 (로깅용)
        """
        self.logger.info(f"🕒 예약된 포트폴리오 분석 실행 중 (예약 시간: {time})")
        return  # schedule 라이브러리가 필요로 함 
        self.dis_portfolio()