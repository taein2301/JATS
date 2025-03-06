"""
Upbit API 모듈

Upbit API를 통해 시세 데이터를 가져오고 주문을 실행합니다.
"""
import os
import jwt
import uuid
import hashlib
import requests
import logging
import time
from urllib.parse import urlencode
from typing import Dict, List, Any, Optional, Union, Tuple

from util.config import ConfigManager
from util.api_base import APIBase


class UpbitAPI(APIBase):
    """Upbit API 클래스"""

    BASE_URL = "https://api.upbit.com/v1"

    def __init__(self, config: ConfigManager, logger: logging.Logger):
        """
        UpbitAPI 초기화
        
        Args:
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
        """
        super().__init__(config, logger)
        
        self.access_key = config.get('upbit.access_key')
        self.secret_key = config.get('upbit.secret_key')
        
        if not self.access_key or not self.secret_key:
            self.logger.error("Upbit API 키가 설정되지 않았습니다.")
            raise ValueError("Upbit API 키가 설정되지 않았습니다.")
            
        self.session = requests.Session()
        
        # API 요청 제한 관리
        self.request_limit = 30  # 분당 최대 요청 수
        self.request_count = 0
        self.request_reset_time = time.time() + 60

    def _generate_auth_token(self, query_string: Optional[str] = None) -> Dict[str, str]:
        """
        인증 토큰 생성
        
        Args:
            query_string: 쿼리 문자열
            
        Returns:
            Dict[str, str]: 인증 헤더
        """
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query_string:
            m = hashlib.sha512()
            m.update(query_string.encode())
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
            
        jwt_token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {jwt_token}"}

    def _handle_rate_limit(self) -> None:
        """API 요청 제한 처리"""
        current_time = time.time()
        
        # 1분이 지났으면 요청 카운트 초기화
        if current_time > self.request_reset_time:
            self.request_count = 0
            self.request_reset_time = current_time + 60
            
        # 요청 제한에 도달했으면 대기
        if self.request_count >= self.request_limit:
            wait_time = self.request_reset_time - current_time
            self.logger.warning(f"API 요청 제한에 도달했습니다. {wait_time:.2f}초 대기합니다.")
            time.sleep(wait_time)
            self.request_count = 0
            self.request_reset_time = time.time() + 60
            
        self.request_count += 1

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        API 요청 실행
        
        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            data: 요청 데이터
            
        Returns:
            Dict[str, Any]: API 응답
        """
        self._handle_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        # 인증 헤더 생성
        headers = {}
        if params:
            query_string = urlencode(params)
            headers.update(self._generate_auth_token(query_string))
        else:
            headers.update(self._generate_auth_token())
            
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, headers=headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = self.session.delete(url, json=data, headers=headers)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API 요청 실패: {str(e)}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"응답: {e.response.text}")
            raise

    def _request_upbit(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Upbit API 요청 실행
        
        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            data: 요청 데이터
            
        Returns:
            Dict[str, Any]: API 응답
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        # 인증 헤더 생성
        headers = {}
        if params:
            query_string = urlencode(params)
            headers.update(self._generate_auth_token(query_string))
        else:
            headers.update(self._generate_auth_token())
            
        return self._request(method, url, params=params, data=data, headers=headers)

    def get_ticker(self, markets: Union[str, List[str]]) -> List[Dict[str, Any]]:
        """
        현재가 정보 조회
        
        Args:
            markets: 마켓 코드 (예: KRW-BTC) 또는 마켓 코드 목록
            
        Returns:
            List[Dict[str, Any]]: 현재가 정보
        """
        if isinstance(markets, list):
            markets = ','.join(markets)
            
        params = {'markets': markets}
        return self._request_upbit('GET', '/ticker', params=params)

    def get_orderbook(self, markets: Union[str, List[str]]) -> List[Dict[str, Any]]:
        """
        호가 정보 조회
        
        Args:
            markets: 마켓 코드 (예: KRW-BTC) 또는 마켓 코드 목록
            
        Returns:
            List[Dict[str, Any]]: 호가 정보
        """
        if isinstance(markets, list):
            markets = ','.join(markets)
            
        params = {'markets': markets}
        return self._request_upbit('GET', '/orderbook', params=params)

    def get_market_all(self) -> List[Dict[str, Any]]:
        """
        마켓 코드 조회
        
        Returns:
            List[Dict[str, Any]]: 마켓 코드 목록
        """
        return self._request_upbit('GET', '/market/all')

    def get_candles_minutes(self, market: str, unit: int, count: int = 200) -> List[Dict[str, Any]]:
        """
        분 캔들 조회
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            unit: 분 단위 (1, 3, 5, 15, 10, 30, 60, 240)
            count: 캔들 개수 (최대 200)
            
        Returns:
            List[Dict[str, Any]]: 분 캔들 목록
        """
        params = {
            'market': market,
            'count': count
        }
        return self._request_upbit('GET', f'/candles/minutes/{unit}', params=params)

    def get_candles_days(self, market: str, count: int = 200) -> List[Dict[str, Any]]:
        """
        일 캔들 조회
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            count: 캔들 개수 (최대 200)
            
        Returns:
            List[Dict[str, Any]]: 일 캔들 목록
        """
        params = {
            'market': market,
            'count': count
        }
        return self._request_upbit('GET', '/candles/days', params=params)

    def get_account(self) -> List[Dict[str, Any]]:
        """
        계좌 정보 조회
        
        Returns:
            List[Dict[str, Any]]: 계좌 정보
        """
        return self._request_upbit('GET', '/accounts')

    def order_buy_market(self, market: str, price: float) -> Dict[str, Any]:
        """
        시장가 매수
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            price: 매수 금액
            
        Returns:
            Dict[str, Any]: 주문 정보
        """
        data = {
            'market': market,
            'side': 'bid',
            'price': str(price),
            'ord_type': 'price',
        }
        return self._request_upbit('POST', '/orders', data=data)

    def order_sell_market(self, market: str, volume: float) -> Dict[str, Any]:
        """
        시장가 매도
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            volume: 매도 수량
            
        Returns:
            Dict[str, Any]: 주문 정보
        """
        data = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'ord_type': 'market',
        }
        return self._request_upbit('POST', '/orders', data=data)

    def order_buy_limit(self, market: str, price: float, volume: float) -> Dict[str, Any]:
        """
        지정가 매수
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            price: 매수 가격
            volume: 매수 수량
            
        Returns:
            Dict[str, Any]: 주문 정보
        """
        data = {
            'market': market,
            'side': 'bid',
            'volume': str(volume),
            'price': str(price),
            'ord_type': 'limit',
        }
        return self._request_upbit('POST', '/orders', data=data)

    def order_sell_limit(self, market: str, price: float, volume: float) -> Dict[str, Any]:
        """
        지정가 매도
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            price: 매도 가격
            volume: 매도 수량
            
        Returns:
            Dict[str, Any]: 주문 정보
        """
        data = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'price': str(price),
            'ord_type': 'limit',
        }
        return self._request_upbit('POST', '/orders', data=data)

    def cancel_order(self, uuid: str) -> Dict[str, Any]:
        """
        주문 취소
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            Dict[str, Any]: 취소된 주문 정보
        """
        data = {'uuid': uuid}
        return self._request_upbit('DELETE', '/order', data=data)

    def get_order(self, uuid: str) -> Dict[str, Any]:
        """
        주문 조회
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            Dict[str, Any]: 주문 정보
        """
        params = {'uuid': uuid}
        return self._request_upbit('GET', '/order', params=params) 