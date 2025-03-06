"""
Upbit 데이터 분석 모듈

Upbit API에서 가져온 데이터를 분석하여 매매 신호를 생성합니다.
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

from util.config import ConfigManager
from upbit.api import UpbitAPI


class UpbitAnalyzer:
    """Upbit 데이터 분석 클래스"""

    def __init__(self, api: UpbitAPI, config: ConfigManager, logger: logging.Logger):
        """
        UpbitAnalyzer 초기화
        
        Args:
            api: Upbit API 인스턴스
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
        """
        self.api = api
        self.config = config
        self.logger = logger
        
        # 전략 설정 로드
        self.rsi_period = config.get('strategy.rsi_period', 14)
        self.macd_fast = config.get('strategy.macd_fast', 12)
        self.macd_slow = config.get('strategy.macd_slow', 26)
        self.macd_signal = config.get('strategy.macd_signal', 9)

    def get_candles_as_dataframe(self, market: str, interval: str = 'minutes', unit: int = 60, count: int = 200) -> pd.DataFrame:
        """
        캔들 데이터를 DataFrame으로 변환
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            interval: 캔들 간격 (minutes 또는 days)
            unit: 분 단위 (interval이 minutes일 때만 사용)
            count: 캔들 개수
            
        Returns:
            pd.DataFrame: 캔들 데이터 DataFrame
        """
        try:
            if interval == 'minutes':
                candles = self.api.get_candles_minutes(market, unit, count)
            elif interval == 'days':
                candles = self.api.get_candles_days(market, count)
            else:
                raise ValueError(f"지원하지 않는 캔들 간격: {interval}")
                
            df = pd.DataFrame(candles)
            
            # 컬럼 이름 변경
            df = df.rename(columns={
                'opening_price': 'open',
                'high_price': 'high',
                'low_price': 'low',
                'trade_price': 'close',
                'candle_date_time_utc': 'date',
                'candle_date_time_kst': 'date_kst',
                'candle_acc_trade_volume': 'volume',
                'candle_acc_trade_price': 'value'
            })
            
            # 날짜 형식 변환
            df['date'] = pd.to_datetime(df['date'])
            
            # 정렬 (최신 데이터가 마지막에 오도록)
            df = df.sort_values('date')
            
            return df
            
        except Exception as e:
            self.logger.error(f"캔들 데이터 가져오기 실패: {str(e)}")
            raise

    def calculate_rsi(self, df: pd.DataFrame, period: int = None) -> pd.DataFrame:
        """
        RSI(Relative Strength Index) 계산
        
        Args:
            df: 캔들 데이터 DataFrame
            period: RSI 기간 (기본값: None, 설정값 사용)
            
        Returns:
            pd.DataFrame: RSI가 추가된 DataFrame
        """
        if period is None:
            period = self.rsi_period
            
        # 가격 변화 계산
        delta = df['close'].diff()
        
        # 상승/하락 구분
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 평균 계산
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # 첫 번째 값 계산 (SMA 방식)
        avg_gain.iloc[period] = gain.iloc[1:period+1].mean()
        avg_loss.iloc[period] = loss.iloc[1:period+1].mean()
        
        # 나머지 값 계산 (EMA 방식)
        for i in range(period+1, len(df)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period-1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period-1) + loss.iloc[i]) / period
        
        # RS 계산
        rs = avg_gain / avg_loss
        
        # RSI 계산
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df

    def calculate_macd(self, df: pd.DataFrame, fast_period: int = None, 
                      slow_period: int = None, signal_period: int = None) -> pd.DataFrame:
        """
        MACD(Moving Average Convergence Divergence) 계산
        
        Args:
            df: 캔들 데이터 DataFrame
            fast_period: 빠른 EMA 기간 (기본값: None, 설정값 사용)
            slow_period: 느린 EMA 기간 (기본값: None, 설정값 사용)
            signal_period: 시그널 기간 (기본값: None, 설정값 사용)
            
        Returns:
            pd.DataFrame: MACD가 추가된 DataFrame
        """
        if fast_period is None:
            fast_period = self.macd_fast
        if slow_period is None:
            slow_period = self.macd_slow
        if signal_period is None:
            signal_period = self.macd_signal
            
        # 지수 이동 평균 계산
        ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD 계산
        df['macd'] = ema_fast - ema_slow
        
        # 시그널 계산
        df['macd_signal'] = df['macd'].ewm(span=signal_period, adjust=False).mean()
        
        # 히스토그램 계산
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        return df

    def calculate_moving_averages(self, df: pd.DataFrame, periods: List[int] = [5, 20, 60, 120]) -> pd.DataFrame:
        """
        이동 평균 계산
        
        Args:
            df: 캔들 데이터 DataFrame
            periods: 이동 평균 기간 목록
            
        Returns:
            pd.DataFrame: 이동 평균이 추가된 DataFrame
        """
        for period in periods:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
            
        return df

    def analyze_market(self, market: str) -> Dict[str, Any]:
        """
        시장 분석 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            
        Returns:
            Dict[str, Any]: 분석 결과
        """
        try:
            # 캔들 데이터 가져오기
            df = self.get_candles_as_dataframe(market)
            
            # 기술적 지표 계산
            df = self.calculate_rsi(df)
            df = self.calculate_macd(df)
            df = self.calculate_moving_averages(df)
            
            # 최신 데이터 가져오기
            latest = df.iloc[-1]
            
            # 분석 결과
            result = {
                'market': market,
                'price': latest['close'],
                'volume': latest['volume'],
                'date': latest['date'],
                'indicators': {
                    'rsi': latest['rsi'],
                    'macd': latest['macd'],
                    'macd_signal': latest['macd_signal'],
                    'macd_hist': latest['macd_hist'],
                    'ma5': latest['ma5'],
                    'ma20': latest['ma20'],
                    'ma60': latest['ma60'],
                    'ma120': latest['ma120'],
                },
                'signals': self.generate_signals(df)
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"시장 분석 실패: {str(e)}")
            raise

    def generate_signals(self, df: pd.DataFrame) -> Dict[str, bool]:
        """
        매매 신호 생성
        
        Args:
            df: 분석된 캔들 데이터 DataFrame
            
        Returns:
            Dict[str, bool]: 매매 신호
        """
        signals = {
            'buy': False,
            'sell': False,
            'strong_buy': False,
            'strong_sell': False
        }
        
        # 최신 데이터와 이전 데이터
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # RSI 기반 신호
        if current['rsi'] < 30:
            signals['buy'] = True
        elif current['rsi'] > 70:
            signals['sell'] = True
            
        # MACD 기반 신호
        if current['macd'] > current['macd_signal'] and previous['macd'] <= previous['macd_signal']:
            signals['buy'] = True
        elif current['macd'] < current['macd_signal'] and previous['macd'] >= previous['macd_signal']:
            signals['sell'] = True
            
        # 이동 평균 기반 신호
        if current['ma5'] > current['ma20'] and previous['ma5'] <= previous['ma20']:
            signals['buy'] = True
        elif current['ma5'] < current['ma20'] and previous['ma5'] >= previous['ma20']:
            signals['sell'] = True
            
        # 강한 매수/매도 신호 (여러 지표가 동시에 신호를 보낼 때)
        if (current['rsi'] < 30 and 
            current['macd'] > current['macd_signal'] and 
            current['ma5'] > current['ma20']):
            signals['strong_buy'] = True
            
        if (current['rsi'] > 70 and 
            current['macd'] < current['macd_signal'] and 
            current['ma5'] < current['ma20']):
            signals['strong_sell'] = True
            
        return signals 