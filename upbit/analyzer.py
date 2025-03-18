"""
Upbit 시장 분석 모듈
"""
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from upbit.api import UpbitAPI


class UpbitAnalyzer:
    """
    Upbit 시장 분석을 담당하는 클래스
    """
    
    def __init__(self, api: UpbitAPI, logger: Any, config: Any):
        """
        Upbit 분석기 초기화
        
        Args:
            api: Upbit API 객체
            logger: 로거 객체
            config: 설정 객체
        """
        self.api = api
        self.logger = logger
        self.config = config
        
        # 리스크 관리 설정
        self.stop_loss_percent = self.config.get('risk.stop_loss_percent', 3.0)
        self.stop_loss_percent_high = self.config.get('risk.stop_loss_percent_high', 2.0)
        
        if self.logger:
            self.logger.info(f"리스크 관리 파라미터 설정 - 기본 손절: {self.stop_loss_percent}%, 최고가 대비 손절: {self.stop_loss_percent_high}%")
    
    def run_trading_analyzer(self, market: str = "KRW-BTC") -> bool:
        """
        매매 전략 실행
        
        Args:
            market: 마켓 코드 (기본값: KRW-BTC)
            
        Returns:
            매수 시그널 여부
        """
        
        try:
            # 기술적 지표 계산
            metrics = self._get_technical_metrics(market)
            if not metrics:
                self.logger.error(f"{market} 기술적 지표 계산 실패")
                return False
            
            # 매수 조건 확인 (예시)
            rsi = metrics.get('rsi', 50)
            macd = metrics.get('macd', 0)
            macd_signal = metrics.get('macd_signal', 0)
            
            # 매수 시그널 (RSI 30 이하이고 MACD가 시그널 라인을 상향 돌파)
            buy_signal = rsi < 30 and macd > macd_signal and macd > 0
            
            # 마켓 한글 이름 가져오기
            market_korean_name = self.api.get_market_name().get(market, market)
            
            if buy_signal:
                self.logger.info(f"{market}({market_korean_name}) 매수 시그널 발생: RSI={rsi:.2f}, MACD={macd:.2f}, MACD_SIGNAL={macd_signal:.2f}")
            else:
                self.logger.info(f"{market}({market_korean_name}) 매수 시그널 발생 안됨 - RSI={rsi:.2f}, MACD={macd:.2f}, MACD_SIGNAL={macd_signal:.2f}")
            
            return buy_signal
            
        except Exception as e:
            self.logger.error(f"매매 전략 분석 중 오류 발생: {str(e)}")
            return False
    
    def check_stop_loss_condition(self, position: Dict[str, Any]) -> bool:
        """
        손절 조건 체크
        
        Args:
            position: 포지션 정보 딕셔너리
            
        Returns:
            손절 시그널 여부
        """
        try:
            market = position.get('market', '')
            if not market:
                self.logger.warning("손절 조건 체크: 마켓 정보가 없습니다.")
                return False
                
            entry_price = position.get('entry_price', 0)
            if entry_price <= 0:
                self.logger.warning(f"{market} 손절 조건 체크: 진입 가격이 유효하지 않습니다. (진입가: {entry_price})")
                return False
                
            # 현재가 조회
            current_price_info = self.api.get_current_price(market)
            if not current_price_info:
                self.logger.error(f"{market} 현재가 조회 실패")
                return False
                
            current_price = float(current_price_info.get('trade_price', 0))
            
            if current_price <= 0:
                return False
                
            # 최고가 갱신
            top_price = position.get('top_price', 0)
            if current_price > top_price:
                top_price = current_price
                
            # 손실률 계산
            loss_rate = (current_price - entry_price) / entry_price * 100
            high_loss_rate = (current_price - top_price) / top_price * 100
            
            # 손절 조건 확인
            # 기본 손절 조건: 진입가 대비 손실률이 설정된 손절 퍼센트보다 낮을 때
            stop_loss = loss_rate <= self.stop_loss_percent
            stop_loss_from_high = high_loss_rate <= self.stop_loss_percent_high
            
            market_korean_name = self.api.get_market_name().get(market, market)
            change_emoji = "📈" if loss_rate > 0 else "📉"
            value_krw = position.get('value_krw', 0)
            if stop_loss:
                self.logger.info(f"{market} ({market_korean_name}) {change_emoji} 기본 손절 조건 충족: 손실률={loss_rate:.2f}%, 평가금액={value_krw:,.0f}원")
            elif stop_loss_from_high:
                self.logger.info(f"{market} ({market_korean_name}) {change_emoji} 최고가 대비 손절 조건 충족: 최고가 대비 하락률={high_loss_rate:.2f}%, 평가금액={value_krw:,.0f}원")
            else:
                self.logger.info(f"{market} ({market_korean_name}) {change_emoji} 평가금액={value_krw:,.0f}원 수익률: {loss_rate:.2f}%, 최고가 대비 하락률 ( 1% 이상 ) : {high_loss_rate:.2f}%")

            return stop_loss or stop_loss_from_high
            
        except Exception as e:
            self.logger.error(f"손절 조건 체크 중 오류 발생: {str(e)}")
            return False

    def _get_technical_metrics(self, market: str = "KRW-BTC", retry_count: int = 3) -> Dict[str, float]:
        """
        기술적 지표 계산
        
        Args:
            market: 마켓 코드 (기본값: KRW-BTC)
            retry_count: API 호출 재시도 횟수
            
        Returns:
            기술적 지표 딕셔너리
        """
        for attempt in range(retry_count):
            try:
                # 캔들 데이터 조회
                candles = self.api.get_candles(market, interval="1d", count=100)
                if not candles:
                    self.logger.error(f"{market} 캔들 데이터 조회 실패 (시도 {attempt+1}/{retry_count})")
                    continue
                    
                # 데이터프레임 변환
                df = pd.DataFrame(candles)
                df = df.sort_values(by='candle_date_time_utc')
                
                # 필요한 컬럼만 추출
                df['close'] = df['trade_price'].astype(float)
                df['high'] = df['high_price'].astype(float)
                df['low'] = df['low_price'].astype(float)
                df['open'] = df['opening_price'].astype(float)
                df['volume'] = df['candle_acc_trade_volume'].astype(float)
                
                # 현재가
                current_price = float(df['close'].iloc[-1])
                
                # RSI 계산 (14일)
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                avg_gain = gain.rolling(window=14).mean()
                avg_loss = loss.rolling(window=14).mean()
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                
                # MACD 계산
                exp1 = df['close'].ewm(span=12, adjust=False).mean()
                exp2 = df['close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                
                # 볼린저 밴드 계산 (20일, 2표준편차)
                ma20 = df['close'].rolling(window=20).mean()
                std20 = df['close'].rolling(window=20).std()
                bb_upper = ma20 + 2 * std20
                bb_lower = ma20 - 2 * std20
                
                # 이동평균선 계산
                ma20 = df['close'].rolling(window=20).mean()
                ma50 = df['close'].rolling(window=50).mean()
                ma200 = df['close'].rolling(window=200).mean()
                
                return {
                    'current_price': current_price,
                    'rsi': rsi.iloc[-1],
                    'macd': macd.iloc[-1],
                    'macd_signal': signal.iloc[-1],
                    'bb_upper': bb_upper.iloc[-1],
                    'bb_lower': bb_lower.iloc[-1],
                    'ma20': ma20.iloc[-1],
                    'ma50': ma50.iloc[-1],
                    'ma200': ma200.iloc[-1]
                }
                
            except Exception as e:
                self.logger.error(f"{market} 기술적 지표 계산 중 오류 발생: {str(e)} (시도 {attempt+1}/{retry_count})")
                
        return {} 