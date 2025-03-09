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
        self.position_info = {
            'market': '',
            'entry_price': 0,
            'amount': 0,
            'top_price': 0,
            'entry_time': None
        }
    
    def run_trading_analyzer(self, market: str = "KRW-BTC") -> bool:
        """
        매매 전략 실행
        
        Args:
            market: 마켓 코드 (기본값: KRW-BTC)
            
        Returns:
            매수 시그널 여부
        """
        self.logger.info(f"{market} 매매 전략 분석 시작")
        
        # 기술적 지표 계산
        metrics = self._get_technical_metrics(market)
        if not metrics:
            self.logger.error(f"{market} 기술적 지표 계산 실패")
            return False
        
        # 여기에 매수/매도 조건 확인 로직 구현
        # 예: RSI, MACD, 볼린저 밴드 등을 활용한 매매 시그널 생성
        # 아래는 예시 로직이며, 실제 전략에 맞게 수정 필요
        
        rsi = metrics.get('rsi', 0)
        macd = metrics.get('macd', 0)
        macd_signal = metrics.get('macd_signal', 0)
        bb_upper = metrics.get('bb_upper', 0)
        bb_lower = metrics.get('bb_lower', 0)
        current_price = metrics.get('current_price', 0)
        
        # 매수 조건 예시 (RSI 과매도 + MACD 골든크로스)
        buy_signal = (rsi < 30) and (macd > macd_signal) and (current_price < bb_lower * 1.02)
        
        if buy_signal:
            self.logger.info(f"{market} 매수 시그널 발생: RSI={rsi}, MACD={macd}, MACD_SIGNAL={macd_signal}")
        
        return buy_signal
    
    def check_stop_loss_condition(self) -> bool:
        """
        손절 조건 체크
        
        Returns:
            손절 시그널 여부
        """
        if not self.position_info['market']:
            return False
            
        market = self.position_info['market']
        entry_price = self.position_info['entry_price']
        top_price = self.position_info['top_price']
        
        # 현재가 조회
        current_price_info = self.api.get_current_price(market)
        if not current_price_info:
            self.logger.error(f"{market} 현재가 조회 실패")
            return False
            
        current_price = float(current_price_info.get('trade_price', 0))
        
        # 손절 조건 계산
        loss_from_entry = (current_price - entry_price) / entry_price * 100
        loss_from_top = (current_price - top_price) / top_price * 100
        
        # 손절 조건 예시 (매수가 대비 -5% 또는 최고가 대비 -3%)
        stop_loss_threshold = self.config.get('stop_loss_threshold', -5.0)
        trailing_stop_threshold = self.config.get('trailing_stop_threshold', -3.0)
        
        stop_loss_signal = (loss_from_entry <= stop_loss_threshold) or (loss_from_top <= trailing_stop_threshold)
        
        if stop_loss_signal:
            self.logger.info(f"{market} 손절 시그널 발생: 매수가 대비 {loss_from_entry:.2f}%, 최고가 대비 {loss_from_top:.2f}%")
            
        return stop_loss_signal
    
    def _get_technical_metrics(self, market: str = "KRW-BTC", retry_count: int = 3) -> Dict[str, float]:
        """
        기술적 지표 계산
        
        Args:
            market: 마켓 코드 (기본값: KRW-BTC)
            retry_count: API 호출 재시도 횟수
            
        Returns:
            기술적 지표 딕셔너리
        """
        # 캔들 데이터 조회
        for attempt in range(retry_count):
            try:
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