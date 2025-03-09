"""
Upbit 트레이딩 시스템 모듈
"""
from typing import Dict, List, Optional, Any, Tuple
import time
from datetime import datetime, timedelta
import threading
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
        self.api = UpbitAPI(
            access_key=upbit_config.get('access_key', ''),
            secret_key=upbit_config.get('secret_key', ''),
            server_url=upbit_config.get('server_url', 'https://api.upbit.com')
        )
        
        # 분석기 초기화
        self.analyzer = UpbitAnalyzer(api=self.api, logger=self.logger, config=upbit_config)
        
        # 포지션 정보 초기화
        self.position = {
            'market': '',
            'entry_price': 0,
            'amount': 0,
            'top_price': 0,
            'entry_time': None
        }
        
        # 타이머 초기화
        self.last_check_time = {
            '10s': datetime.now(),
            '1m': datetime.now(),
            '5m': datetime.now(),
            '1h': datetime.now()
        }
        
        # 거래량 상위 코인 목록
        self.top_volume_coins = []
        
        self.logger.info("Upbit 트레이더 초기화 완료")
        
    def run(self):
        """
        트레이딩 시스템의 메인 실행 루프
        
        10초/1분/5분/1시간 주기로 다양한 작업 수행
        포지션 체크, 매매 시그널 분석, 리포트 생성 등
        """
        self.logger.info("🚀 Upbit 트레이더 실행 시작")
        self.logger.info(f"⚙️ 설정 정보: 리스크 설정 - 손절 비율: {self.config.get('risk.stop_loss_percent', 3)}%")
        self.logger.info(f"⚙️ 설정 정보: 최고가 대비 손절 비율: {self.config.get('risk.stop_loss_percent_high', 2)}%")
        self.notifier.send_system_notification("Upbit 트레이더 실행", "트레이딩 시스템이 시작되었습니다.")
        
        # 시작 시간 기록
        start_time = datetime.now()
        self.logger.info(f"🕐 시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 초기 포지션 체크
            self.logger.info("🔍 초기 포지션 체크 중...")
            self.check_position()
            self.dis_portfolio()
            
            # 메인 루프
            self.logger.info("⏱️ 메인 루프 시작")
            loop_count = 0
            
            while True:
                now = datetime.now()
                loop_count += 1
                
                # 매 100회 반복마다 실행 상태 로깅
                if loop_count % 100 == 0:
                    runtime = now - start_time
                    days, seconds = runtime.days, runtime.seconds
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    seconds = seconds % 60
                    self.logger.info(f"⏱️ 트레이더 실행 중: {days}일 {hours}시간 {minutes}분 {seconds}초 경과 (반복 횟수: {loop_count})")
                
                # 10초마다 실행
                if (now - self.last_check_time['10s']).total_seconds() >= 10:
                    self.last_check_time['10s'] = now
                    
                    # 포지션이 있을 경우 손절 조건 체크
                    if self.position['market']:
                        self.logger.debug(f"🔍 {self.position['market']} 손절 조건 체크 중...")
                        if self.analyzer.check_stop_loss_condition():
                            self.logger.warning(f"📉 {self.position['market']} 손절 조건 충족! 매도 실행")
                            self.sell(self.position['market'])
                    
                # 1분마다 실행
                if (now - self.last_check_time['1m']).total_seconds() >= 60:
                    self.last_check_time['1m'] = now
                    self.logger.debug("⏱️ 1분 주기 작업 실행")
                    
                    # 매수/매도 시그널 체크
                    self.logger.debug("🔍 매수/매도 시그널 체크 중...")
                    self.check_signal()
                    
                    # 비정상 주문 취소
                    self.logger.debug("🔍 비정상 주문 체크 중...")
                    self.cancel_abnormal_orders()
                
                # 5분마다 실행
                if (now - self.last_check_time['5m']).total_seconds() >= 300:
                    self.last_check_time['5m'] = now
                    self.logger.debug("⏱️ 5분 주기 작업 실행")
                    
                    # 거래량 상위 코인 갱신
                    self.logger.debug("📊 거래량 상위 코인 분석 중...")
                    self.set_top_volume_10min()
                    
                    # 포지션 체크
                    self.logger.debug("🔍 포지션 상태 체크 중...")
                    self.check_position()
                
                # 1시간마다 실행
                if (now - self.last_check_time['1h']).total_seconds() >= 3600:
                    self.last_check_time['1h'] = now
                    self.logger.info("⏱️ 1시간 주기 작업 실행")
                    
                    # 포트폴리오 분석 및 리포트
                    self.logger.info("📊 포트폴리오 분석 중...")
                    self.dis_portfolio()
                
                # 잠시 대기
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("❌ 사용자에 의해 트레이더가 중지되었습니다.")
            self.notifier.send_system_notification("트레이더 중지", "사용자에 의해 트레이더가 중지되었습니다.")
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ 트레이더 실행 중 오류 발생: {str(e)}\n{error_traceback}")
            self.notifier.send_system_notification("트레이더 오류", f"트레이더 실행 중 오류 발생: {str(e)}")
    
    def buy(self, market: str):
        """
        지정된 마켓에 시장가 매수 주문 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
        """
        self.logger.info(f"💰 {market} 매수 시도")
        
        try:
            # 이미 포지션이 있는 경우 매수하지 않음
            if self.position['market']:
                self.logger.warning(f"⚠️ 이미 {self.position['market']} 포지션이 있어 {market} 매수를 진행하지 않습니다.")
                return
            
            # KRW 잔고 확인
            self.logger.debug(f"🔍 {market} 매수를 위한 KRW 잔고 확인 중...")
            balances = self.api.get_balances()
            krw_balance = next((float(b['balance']) for b in balances if b['currency'] == 'KRW'), 0)
            self.logger.info(f"💵 현재 KRW 잔고: {krw_balance:,.0f}원")
            
            # 매수 금액 계산 (잔고의 90%, 수수료 고려)
            buy_amount = krw_balance * 0.9
            if buy_amount < 5000:  # 최소 주문 금액
                self.logger.warning(f"⚠️ KRW 잔고 부족: {krw_balance:,.0f}원 (최소 주문 금액: 5,000원)")
                return
            
            self.logger.info(f"💰 {market} 매수 금액: {buy_amount:,.0f}원 (잔고의 90%)")
                
            # 시장가 매수 주문
            self.logger.debug(f"🔄 {market} 시장가 매수 주문 요청 중...")
            order_result = self.api.run_order(market=market, side='bid', price=buy_amount)
            
            if not order_result or 'uuid' not in order_result:
                self.logger.error(f"❌ {market} 매수 주문 실패: {order_result}")
                return
                
            order_uuid = order_result['uuid']
            self.logger.info(f"✅ {market} 매수 주문 완료: {order_uuid}")
            
            # 주문 상태 확인 (최대 10초 대기)
            self.logger.debug(f"🔍 {market} 주문 상태 확인 중...")
            for i in range(10):
                time.sleep(1)
                self.logger.debug(f"⏱️ {market} 주문 상태 확인 중... ({i+1}/10)")
                order_status = self.api.get_order_status(order_uuid)
                
                if order_status.get('state') == 'done':
                    # 매수 완료
                    executed_volume = float(order_status.get('executed_volume', 0))
                    avg_price = float(order_status.get('avg_price', 0))
                    total_price = executed_volume * avg_price
                    
                    self.logger.info(f"🎯 {market} 매수 완료:")
                    self.logger.info(f"   - 수량: {executed_volume}")
                    self.logger.info(f"   - 평균가: {avg_price:,.0f}원")
                    self.logger.info(f"   - 총액: {total_price:,.0f}원")
                    
                    self.notifier.send_trade_notification(
                        "매수 완료",
                        f"{market} 매수 완료\n수량: {executed_volume}\n가격: {avg_price:,.0f}원\n총액: {total_price:,.0f}원"
                    )
                    
                    # 포지션 정보 업데이트
                    self.position_entered(market, avg_price, executed_volume)
                    return
            
            # 10초 이내에 체결되지 않은 경우
            self.logger.warning(f"⚠️ {market} 매수 주문이 10초 이내에 체결되지 않았습니다. 주문 ID: {order_uuid}")
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ {market} 매수 중 오류 발생: {str(e)}\n{error_traceback}")
            self.notifier.send_system_notification("매수 오류", f"{market} 매수 중 오류 발생: {str(e)}")
    
    def sell(self, market: str):
        """
        지정된 마켓의 보유 수량 전체 시장가 매도
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
        """
        self.logger.info(f"💸 {market} 매도 시도")
        
        try:
            # 포지션 확인
            if not self.position['market'] or self.position['market'] != market:
                self.logger.warning(f"⚠️ {market} 포지션이 없어 매도를 진행하지 않습니다.")
                return
                
            # 보유 수량 확인
            amount = self.position['amount']
            if amount <= 0:
                self.logger.warning(f"⚠️ {market} 보유 수량이 없습니다.")
                return
            
            # 현재가 조회
            current_price_info = self.api.get_current_price(market)
            if current_price_info:
                current_price = float(current_price_info.get('trade_price', 0))
                entry_price = self.position['entry_price']
                top_price = self.position['top_price']
                
                # 현재 수익률 계산
                current_profit_pct = (current_price - entry_price) / entry_price * 100
                top_profit_pct = (top_price - entry_price) / entry_price * 100
                
                self.logger.info(f"📊 {market} 매도 전 상태:")
                self.logger.info(f"   - 보유 수량: {amount}")
                self.logger.info(f"   - 매수 가격: {entry_price:,.0f}원")
                self.logger.info(f"   - 현재 가격: {current_price:,.0f}원")
                self.logger.info(f"   - 최고 가격: {top_price:,.0f}원")
                self.logger.info(f"   - 현재 수익률: {current_profit_pct:.2f}%")
                self.logger.info(f"   - 최고 수익률: {top_profit_pct:.2f}%")
                
            # 시장가 매도 주문
            self.logger.debug(f"🔄 {market} 시장가 매도 주문 요청 중...")
            order_result = self.api.run_order(market=market, side='ask', volume=amount)
            
            if not order_result or 'uuid' not in order_result:
                self.logger.error(f"❌ {market} 매도 주문 실패: {order_result}")
                return
                
            order_uuid = order_result['uuid']
            self.logger.info(f"✅ {market} 매도 주문 완료: {order_uuid}")
            
            # 주문 상태 확인 (최대 10초 대기)
            self.logger.debug(f"🔍 {market} 매도 주문 상태 확인 중...")
            for i in range(10):
                time.sleep(1)
                self.logger.debug(f"⏱️ {market} 매도 주문 상태 확인 중... ({i+1}/10)")
                order_status = self.api.get_order_status(order_uuid)
                
                if order_status.get('state') == 'done':
                    # 매도 완료
                    executed_volume = float(order_status.get('executed_volume', 0))
                    avg_price = float(order_status.get('avg_price', 0))
                    total_price = executed_volume * avg_price
                    
                    # 수익률 계산
                    entry_price = self.position['entry_price']
                    profit_pct = (avg_price - entry_price) / entry_price * 100
                    profit_amount = total_price - (executed_volume * entry_price)
                    
                    # 수익/손실 이모티콘 선택
                    profit_emoji = "📈" if profit_pct >= 0 else "📉"
                    
                    self.logger.info(f"{profit_emoji} {market} 매도 완료:")
                    self.logger.info(f"   - 수량: {executed_volume}")
                    self.logger.info(f"   - 평균가: {avg_price:,.0f}원")
                    self.logger.info(f"   - 총액: {total_price:,.0f}원")
                    self.logger.info(f"   - 수익률: {profit_pct:.2f}%")
                    self.logger.info(f"   - 수익금액: {profit_amount:,.0f}원")
                    
                    # 보유 기간 계산
                    if self.position['entry_time']:
                        holding_time = datetime.now() - self.position['entry_time']
                        days, seconds = holding_time.days, holding_time.seconds
                        hours = seconds // 3600
                        minutes = (seconds % 3600) // 60
                        seconds = seconds % 60
                        self.logger.info(f"   - 보유 기간: {days}일 {hours}시간 {minutes}분 {seconds}초")
                    
                    self.notifier.send_trade_notification(
                        "매도 완료",
                        f"{profit_emoji} {market} 매도 완료\n"
                        f"수량: {executed_volume}\n"
                        f"가격: {avg_price:,.0f}원\n"
                        f"총액: {total_price:,.0f}원\n"
                        f"수익률: {profit_pct:.2f}%\n"
                        f"수익금액: {profit_amount:,.0f}원"
                    )
                    
                    # 포지션 정보 초기화
                    self.position_exited()
                    return
            
            # 10초 이내에 체결되지 않은 경우
            self.logger.warning(f"⚠️ {market} 매도 주문이 10초 이내에 체결되지 않았습니다. 주문 ID: {order_uuid}")
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ {market} 매도 중 오류 발생: {str(e)}\n{error_traceback}")
            self.notifier.send_system_notification("매도 오류", f"{market} 매도 중 오류 발생: {str(e)}")
    
    def cancel_abnormal_orders(self, market: Optional[str] = None):
        """
        미체결된 비정상 주문들 일괄 취소
        
        Args:
            market: 특정 마켓 지정 시 해당 마켓만 취소
        """
        try:
            self.logger.debug(f"🔍 미체결 주문 확인 중... {market if market else '전체 마켓'}")
            
            # 대기 중인 주문 조회
            wait_orders = self.api.get_wait_order(market)
            
            if not wait_orders:
                self.logger.debug("✅ 미체결 주문이 없습니다.")
                return
                
            self.logger.info(f"🔄 미체결 주문 {len(wait_orders)}건 발견, 취소 진행 중...")
                
            # 주문 취소
            canceled_count = 0
            for order in wait_orders:
                uuid = order.get('uuid')
                order_market = order.get('market', '알 수 없음')
                side = order.get('side', '알 수 없음')
                price = order.get('price', '0')
                volume = order.get('volume', '0')
                created_at = order.get('created_at', '알 수 없음')
                
                side_str = '매수' if side == 'bid' else '매도' if side == 'ask' else side
                
                if uuid:
                    self.logger.info(
                        f"❌ 미체결 주문 취소: {order_market} - {side_str} "
                        f"(수량: {volume}, 가격: {price}, 주문시각: {created_at})"
                    )
                    cancel_result = self.api.set_order_cancel(uuid)
                    
                    if cancel_result and 'uuid' in cancel_result:
                        self.logger.info(f"✅ 주문 취소 성공: {order_market} - {uuid}")
                        canceled_count += 1
                    else:
                        self.logger.warning(f"⚠️ 주문 취소 실패: {order_market} - {uuid}")
            
            if canceled_count > 0:
                self.logger.info(f"🧹 총 {canceled_count}건의 미체결 주문 취소 완료")
                self.notifier.send_system_notification(
                    "미체결 주문 취소",
                    f"🧹 총 {canceled_count}건의 미체결 주문이 취소되었습니다."
                )
                    
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ 주문 취소 중 오류 발생: {str(e)}\n{error_traceback}")
    
    def check_signal(self):
        """
        매수/매도 시그널 체크 및 거래 실행
        
        포지션 있을 때는 매도 시그널만 체크
        포지션 없을 때는 매수 시그널 체크
        """
        # 포지션이 있는 경우 매도 시그널 체크
        if self.position['market']:
            market = self.position['market']
            self.logger.debug(f"🔍 {market} 매도 시그널 체크 중...")
            
            # 매도 시그널 체크 로직 구현
            # 예: 손절 조건, 목표가 도달 등
            # 여기서는 손절 조건만 체크 (run 메서드에서 이미 처리)
            
            return
            
        # 포지션이 없는 경우 매수 시그널 체크
        self.logger.debug("🔍 매수 시그널 체크 중...")
        
        # 거래량 상위 코인 대상으로 매수 시그널 체크
        if not self.top_volume_coins:
            self.logger.warning("⚠️ 거래량 상위 코인 목록이 비어 있어 매수 시그널을 체크할 수 없습니다.")
            return
            
        self.logger.debug(f"📊 거래량 상위 5개 코인 매수 시그널 체크: {', '.join(self.top_volume_coins[:5])}")
        
        for market in self.top_volume_coins[:5]:  # 상위 5개만 체크
            self.logger.debug(f"🔍 {market} 매수 시그널 분석 중...")
            if self.analyzer.run_trading_analyzer(market):
                self.logger.info(f"🎯 {market} 매수 시그널 발생!")
                self.buy(market)
                break  # 한 번에 하나의 코인만 매수
    
    def check_position(self):
        """
        현재 보유 중인 포지션 상태 확인
        앱이나 다른 곳에서의 변화 반영
        """
        try:
            self.logger.debug("🔍 현재 포지션 상태 확인 중...")
            
            # 잔고 조회
            balances = self.api.get_balances()
            
            # KRW가 아닌 자산 찾기 (코인)
            coin_found = False
            for balance in balances:
                currency = balance.get('currency')
                if currency != 'KRW' and float(balance.get('balance', 0)) > 0:
                    market = f"KRW-{currency}"
                    amount = float(balance.get('balance', 0))
                    avg_buy_price = float(balance.get('avg_buy_price', 0))
                    
                    # 포지션 정보 업데이트
                    if not self.position['market'] or self.position['market'] != market:
                        self.logger.info(f"🔎 새로운 포지션 발견: {market} - {amount} @ {avg_buy_price:,.0f}원")
                        self.position_entered(market, avg_buy_price, amount)
                    else:
                        # 기존 포지션 정보 업데이트 (수량 변경 등)
                        if self.position['amount'] != amount:
                            self.logger.info(f"📝 {market} 포지션 수량 변경: {self.position['amount']} → {amount}")
                            self.position['amount'] = amount
                        
                        # 현재가 조회 및 최고가 갱신
                        current_price_info = self.api.get_current_price(market)
                        if current_price_info:
                            current_price = float(current_price_info.get('trade_price', 0))
                            if current_price > self.position['top_price']:
                                old_top = self.position['top_price']
                                self.position['top_price'] = current_price
                                self.logger.info(f"📈 {market} 최고가 갱신: {old_top:,.0f}원 → {current_price:,.0f}원")
                    
                    coin_found = True
                    break  # 첫 번째 코인만 처리
            
            # 코인 보유가 없는 경우 포지션 초기화
            if not coin_found and self.position['market']:
                self.logger.info(f"📝 포지션 종료 확인: {self.position['market']}")
                self.position_exited()
                
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ 포지션 체크 중 오류 발생: {str(e)}\n{error_traceback}")
    
    def position_entered(self, market: str, price: float = 0, amount: float = 0):
        """
        매수 포지션 진입 처리
        
        Args:
            market: 마켓 코드
            price: 매수 가격
            amount: 매수 수량
        """
        # 이전 포지션 정보 저장 (로깅용)
        old_position = self.position.copy()
        
        # 새 포지션 정보 설정
        self.position = {
            'market': market,
            'entry_price': price,
            'amount': amount,
            'top_price': price,  # 초기 최고가는 매수가로 설정
            'entry_time': datetime.now()
        }
        
        # 상세 로깅
        if old_position['market']:
            self.logger.info(f"📝 포지션 변경: {old_position['market']} → {market}")
        else:
            self.logger.info(f"📝 새 포지션 진입: {market}")
            
        self.logger.info(f"💰 {market} 포지션 상세:")
        self.logger.info(f"   - 수량: {amount}")
        self.logger.info(f"   - 매수가: {price:,.0f}원")
        self.logger.info(f"   - 총액: {price * amount:,.0f}원")
        self.logger.info(f"   - 진입 시간: {self.position['entry_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.notifier.send_system_notification(
            "포지션 진입",
            f"💰 {market} 포지션 진입\n"
            f"수량: {amount}\n"
            f"가격: {price:,.0f}원\n"
            f"총액: {price * amount:,.0f}원\n"
            f"시간: {self.position['entry_time'].strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    def position_exited(self):
        """
        매도 포지션 정리
        포지션 관련 정보 초기화
        """
        market = self.position['market']
        entry_time = self.position['entry_time']
        
        # 보유 기간 계산
        holding_period = ""
        if entry_time:
            holding_time = datetime.now() - entry_time
            days, seconds = holding_time.days, holding_time.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            holding_period = f"{days}일 {hours}시간 {minutes}분 {seconds}초"
            
        self.logger.info(f"📝 {market} 포지션 종료")
        if holding_period:
            self.logger.info(f"⏱️ 보유 기간: {holding_period}")
        
        # 포지션 정보 초기화
        self.position = {
            'market': '',
            'entry_price': 0,
            'amount': 0,
            'top_price': 0,
            'entry_time': None
        }
        
        self.notifier.send_system_notification(
            "포지션 종료", 
            f"📝 {market} 포지션 종료" + (f"\n보유 기간: {holding_period}" if holding_period else "")
        )
    
    def set_top_volume_10min(self):
        """
        최근 10분간 거래량 상위 코인 조회
        거래대금 기준 정렬 및 변동률 분석
        """
        try:
            self.logger.debug("📊 거래량 상위 코인 분석 시작")
            
            # 마켓 정보 조회
            self.logger.debug("🔍 마켓 정보 조회 중...")
            markets = self.api.get_market_info()
            market_codes = [market['market'] for market in markets]
            self.logger.debug(f"📝 총 {len(market_codes)}개 마켓 정보 조회 완료")
            
            # 거래량 정보 저장할 리스트
            volume_data = []
            
            # 각 마켓별 거래량 조회
            self.logger.debug("🔍 마켓별 거래량 조회 중...")
            for i, market in enumerate(market_codes[:30]):  # 상위 30개만 조회 (API 호출 최소화)
                try:
                    if i % 10 == 0:
                        self.logger.debug(f"🔄 거래량 조회 진행 중... ({i+1}/30)")
                        
                    # 1분봉 10개 조회
                    candles = self.api.get_candles(market, interval="1m", count=10)
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
                    
                except Exception as e:
                    self.logger.error(f"❌ {market} 거래량 조회 중 오류: {str(e)}")
            
            # 거래대금 기준 정렬
            volume_data.sort(key=lambda x: x['volume_krw'], reverse=True)
            
            # 상위 10개 코인 저장
            old_top_coins = self.top_volume_coins.copy() if self.top_volume_coins else []
            self.top_volume_coins = [data['market'] for data in volume_data[:10]]
            
            # 변경 사항 로깅
            if old_top_coins:
                new_coins = [coin for coin in self.top_volume_coins if coin not in old_top_coins]
                removed_coins = [coin for coin in old_top_coins if coin not in self.top_volume_coins]
                
                if new_coins:
                    self.logger.info(f"📈 거래량 상위 진입 코인: {', '.join(new_coins)}")
                if removed_coins:
                    self.logger.info(f"📉 거래량 상위 이탈 코인: {', '.join(removed_coins)}")
            
            # 상위 10개 코인 상세 정보 로깅
            self.logger.info(f"📊 거래량 상위 10개 코인:")
            for i, data in enumerate(volume_data[:10]):
                market = data['market']
                volume_krw = data['volume_krw']
                price_change_pct = data['price_change_pct']
                
                # 가격 변동 이모티콘
                change_emoji = "📈" if price_change_pct >= 0 else "📉"
                
                self.logger.info(f"   {i+1}. {market}: {volume_krw/1000000:,.1f}백만원 {change_emoji} {price_change_pct:+.2f}%")
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ 거래량 상위 코인 조회 중 오류 발생: {str(e)}\n{error_traceback}")
    
    def dis_portfolio(self):
        """
        포트폴리오 상세 분석 및 수익률 계산
        코인별 수익률, 보유 수량 평가금액 등 계산
        """
        try:
            self.logger.info("💰 포트폴리오 분석 시작")
            
            # 잔고 조회
            self.logger.debug("🔍 잔고 정보 조회 중...")
            balances = self.api.get_balances()
            self.logger.debug(f"📝 총 {len(balances)}개 자산 정보 조회 완료")
            
            # 총 평가금액
            total_krw = 0
            portfolio_items = []
            
            # 각 자산별 정보 계산
            for balance in balances:
                currency = balance.get('currency')
                balance_amount = float(balance.get('balance', 0))
                
                if currency == 'KRW':
                    # KRW는 그대로 합산
                    total_krw += balance_amount
                    portfolio_items.append({
                        'currency': 'KRW',
                        'amount': balance_amount,
                        'value_krw': balance_amount,
                        'profit_pct': 0
                    })
                    self.logger.debug(f"💵 KRW 잔고: {balance_amount:,.0f}원")
                else:
                    # 코인은 현재가로 평가
                    market = f"KRW-{currency}"
                    self.logger.debug(f"🔍 {market} 현재가 조회 중...")
                    current_price_info = self.api.get_current_price(market)
                    
                    if current_price_info:
                        current_price = float(current_price_info.get('trade_price', 0))
                        avg_buy_price = float(balance.get('avg_buy_price', 0))
                        
                        # 평가금액 및 수익률 계산
                        value_krw = balance_amount * current_price
                        profit_pct = (current_price - avg_buy_price) / avg_buy_price * 100 if avg_buy_price > 0 else 0
                        profit_amount = value_krw - (balance_amount * avg_buy_price)
                        
                        # 수익/손실 이모티콘
                        profit_emoji = "📈" if profit_pct >= 0 else "📉"
                        
                        self.logger.debug(
                            f"{profit_emoji} {market}: {balance_amount} 개, "
                            f"매수가: {avg_buy_price:,.0f}원, 현재가: {current_price:,.0f}원, "
                            f"평가금액: {value_krw:,.0f}원, 수익률: {profit_pct:+.2f}%"
                        )
                        
                        total_krw += value_krw
                        portfolio_items.append({
                            'currency': currency,
                            'market': market,
                            'amount': balance_amount,
                            'avg_buy_price': avg_buy_price,
                            'current_price': current_price,
                            'value_krw': value_krw,
                            'profit_pct': profit_pct,
                            'profit_amount': profit_amount,
                            'emoji': profit_emoji
                        })
            
            # 포트폴리오 요약 로깅
            self.logger.info(f"💰 총 평가금액: {total_krw:,.0f}원")
            
            # 코인 자산만 필터링
            coin_items = [item for item in portfolio_items if item.get('market')]
            
            # 코인 보유 중인 경우 상세 정보 로깅
            if coin_items:
                # 수익률 기준 정렬
                coin_items.sort(key=lambda x: x['profit_pct'], reverse=True)
                
                self.logger.info("📊 코인별 수익률 (높은 순):")
                for item in coin_items:
                    self.logger.info(
                        f"   {item['emoji']} {item['market']}: {item['profit_pct']:+.2f}% "
                        f"({item['profit_amount']:+,.0f}원)"
                    )
            
            # 포트폴리오 요약 메시지 생성
            summary = f"💰 총 평가금액: {total_krw:,.0f}원\n\n"
            
            for item in portfolio_items:
                if item['currency'] == 'KRW':
                    summary += f"💵 KRW: {item['amount']:,.0f}원\n\n"
                else:
                    emoji = item.get('emoji', '')
                    summary += (
                        f"{emoji} {item['market']}: {item['amount']} 개\n"
                        f"평균매수가: {item['avg_buy_price']:,.0f}원\n"
                        f"현재가: {item['current_price']:,.0f}원\n"
                        f"평가금액: {item['value_krw']:,.0f}원\n"
                        f"수익률: {item['profit_pct']:+.2f}%\n"
                        f"수익금액: {item['profit_amount']:+,.0f}원\n\n"
                    )
            
            # 알림 전송
            self.logger.info("✅ 포트폴리오 분석 완료")
            self.notifier.send_system_notification("포트폴리오 현황", summary)
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.logger.error(f"❌ 포트폴리오 분석 중 오류 발생: {str(e)}\n{error_traceback}") 