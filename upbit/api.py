"""
Upbit API 호출 모듈
"""
from typing import Dict, List, Optional, Any
import requests
import jwt
import uuid
import hashlib
from urllib.parse import urlencode


class UpbitAPI:
    """
    Upbit API 호출을 담당하는 클래스
    """
    
    def __init__(self, access_key: str, secret_key: str, server_url: str = "https://api.upbit.com", logger=None):
        """
        Upbit API 클래스 초기화
        
        Args:
            access_key: Upbit API 액세스 키
            secret_key: Upbit API 시크릿 키
            server_url: Upbit API 서버 URL
            logger: 로깅을 위한 로거 객체
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.server_url = server_url
        self.logger = logger
    
    def _get_auth_header(self, query_params: Optional[Dict] = None) -> Dict:
        """
        인증 헤더 생성
        
        Args:
            query_params: 쿼리 파라미터
            
        Returns:
            인증 헤더 딕셔너리
        """
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4())
        }
        
        if query_params:
            query_string = urlencode(query_params)
            payload['query'] = query_string
            
        jwt_token = jwt.encode(payload, self.secret_key)
        authorization = f"Bearer {jwt_token}"
        
        return {"Authorization": authorization}
    
    def get_current_price(self, ticker_name: str = "KRW-BTC") -> Dict:
        """
        특정 코인의 현재가를 조회
        
        Args:
            ticker_name: 코인 티커 (기본값: KRW-BTC)
            
        Returns:
            현재가 정보 딕셔너리
        """
        if self.logger:
            self.logger.info(f"현재가 조회 시작 - 티커: {ticker_name}")
            
        url = f"{self.server_url}/v1/ticker"
        params = {'markets': ticker_name}
        headers = self._get_auth_header(params)
        
        if self.logger:
            self.logger.debug(f"API 요청 URL: {url}")
            self.logger.debug(f"API 요청 파라미터: {params}")
            
        try:
            response = requests.get(url, params=params, headers=headers)
            
            if self.logger:
                self.logger.debug(f"API 응답 상태 코드: {response.status_code}")
                
            if response.status_code == 200:
                result = response.json()
                if result and len(result) > 0:
                    if self.logger:
                        self.logger.info(f"현재가 조회 성공 - 티커: {ticker_name}, 가격: {result[0].get('trade_price')}")
                    return result[0]
                else:
                    if self.logger:
                        self.logger.warning(f"현재가 조회 결과 없음 - 티커: {ticker_name}")
                    return {}
            else:
                if self.logger:
                    self.logger.error(f"현재가 조회 실패 - 상태 코드: {response.status_code}, 응답: {response.text}")
                return {}
        except Exception as e:
            if self.logger:
                self.logger.error(f"현재가 조회 중 예외 발생: {str(e)}")
            return {}
    
    def get_candles(self, market: str, interval: str = "1d", count: int = 200, to: Optional[str] = None) -> List[Dict]:
        """
        캔들 데이터 조회
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            interval: 캔들 간격 (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
            count: 캔들 개수 (최대 200)
            to: 마지막 캔들 시간 (ISO 8601 형식)
            
        Returns:
            캔들 데이터 리스트
        """
        # 간격에 따른 엔드포인트 결정
        if interval in ['1m', '3m', '5m', '15m', '30m', '1h', '4h']:
            url = f"{self.server_url}/v1/candles/minutes/{interval.replace('m', '').replace('h', '60')}"
        elif interval == '1d':
            url = f"{self.server_url}/v1/candles/days"
        elif interval == '1w':
            url = f"{self.server_url}/v1/candles/weeks"
        elif interval == '1M':
            url = f"{self.server_url}/v1/candles/months"
        else:
            raise ValueError(f"지원하지 않는 간격: {interval}")
        
        params = {
            'market': market,
            'count': count
        }
        
        if to:
            params['to'] = to
            
        headers = self._get_auth_header(params)
        response = requests.get(url, params=params, headers=headers)
        
        return response.json() if response.status_code == 200 else []
    
    def run_order(self, market: str, side: str, volume: Optional[float] = None, price: Optional[float] = None) -> Dict:
        """
        주문 실행
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            side: 주문 종류 (bid: 매수, ask: 매도)
            volume: 주문량 (매도 시 필수)
            price: 주문 가격 (매수 시 필수)
            
        Returns:
            주문 결과 딕셔너리
        """
        order_type = "매수" if side == "bid" else "매도"
        
        if self.logger:
            self.logger.info(f"{order_type} 주문 실행 시작 - 마켓: {market}, 타입: {order_type}")
            if side == "bid":
                self.logger.info(f"매수 금액: {price} KRW")
            else:
                self.logger.info(f"매도 수량: {volume}")
                
        url = f"{self.server_url}/v1/orders"
        
        params = {
            'market': market,
            'side': side,
            'ord_type': 'price' if side == 'bid' else 'market'
        }
        
        try:
            if side == 'bid' and price:
                params['price'] = str(price)
            elif side == 'ask' and volume:
                params['volume'] = str(volume)
                params['ord_type'] = 'market'
            else:
                error_msg = "매수 시 price, 매도 시 volume이 필요합니다."
                if self.logger:
                    self.logger.error(f"주문 실패 - {error_msg}")
                raise ValueError(error_msg)
            
            if self.logger:
                self.logger.debug(f"API 요청 URL: {url}")
                self.logger.debug(f"API 요청 파라미터: {params}")
                
            headers = self._get_auth_header(params)
            response = requests.post(url, json=params, headers=headers)
            
            if self.logger:
                self.logger.debug(f"API 응답 상태 코드: {response.status_code}")
                
            if response.status_code == 201:
                result = response.json()
                if self.logger:
                    self.logger.info(f"{order_type} 주문 성공 - UUID: {result.get('uuid')}, 마켓: {result.get('market')}")
                    self.logger.debug(f"주문 상세 정보: {result}")
                return result
            else:
                if self.logger:
                    self.logger.error(f"{order_type} 주문 실패 - 상태 코드: {response.status_code}, 응답: {response.text}")
                return {}
        except Exception as e:
            if self.logger:
                self.logger.error(f"{order_type} 주문 중 예외 발생: {str(e)}")
            return {}
    
    def get_order_status(self, uuid: str) -> Dict:
        """
        특정 주문의 상태 조회
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            주문 상태 딕셔너리
        """
        url = f"{self.server_url}/v1/order"
        params = {'uuid': uuid}
        headers = self._get_auth_header(params)
        
        response = requests.get(url, params=params, headers=headers)
        return response.json() if response.status_code == 200 else {}
    
    def set_order_cancel(self, uuid: str) -> Dict:
        """
        특정 주문 취소
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            취소 결과 딕셔너리
        """
        url = f"{self.server_url}/v1/order"
        params = {'uuid': uuid}
        headers = self._get_auth_header(params)
        
        response = requests.delete(url, params=params, headers=headers)
        return response.json() if response.status_code == 200 else {}
    
    def get_wait_order(self, market: Optional[str] = None) -> List[Dict]:
        """
        대기 중인 주문 조회
        
        Args:
            market: 마켓 코드 (선택 사항)
            
        Returns:
            대기 중인 주문 리스트
        """
        if self.logger:
            self.logger.info(f"대기 중인 주문 조회 시작 - 마켓: {market if market else '전체'}")
            
        url = f"{self.server_url}/v1/orders"
        params = {'state': 'wait'}
        
        if market:
            params['market'] = market
            
        headers = self._get_auth_header(params)
        
        if self.logger:
            self.logger.debug(f"API 요청 URL: {url}")
            self.logger.debug(f"API 요청 파라미터: {params}")
            
        try:
            response = requests.get(url, params=params, headers=headers)
            
            if self.logger:
                self.logger.debug(f"API 응답 상태 코드: {response.status_code}")
                
            if response.status_code == 200:
                result = response.json()
                if self.logger:
                    self.logger.info(f"대기 중인 주문 조회 성공 - 주문 수: {len(result)}")
                    if result:
                        for order in result:
                            self.logger.debug(f"주문 정보: 마켓={order.get('market')}, UUID={order.get('uuid')}, 타입={order.get('side')}, 가격={order.get('price')}, 수량={order.get('volume')}")
                return result
            else:
                if self.logger:
                    self.logger.error(f"대기 중인 주문 조회 실패 - 상태 코드: {response.status_code}, 응답: {response.text}")
                return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"대기 중인 주문 조회 중 예외 발생: {str(e)}")
            return []
    
    def get_closed_orders(self, market: str, to: Optional[str] = None, 
                         page: int = 1, limit: int = 100, 
                         order_by: str = 'desc') -> List[Dict]:
        """
        종료된 주문 내역 조회
        
        Args:
            market: 마켓 코드
            to: 마지막 주문 시간 (ISO 8601 형식)
            page: 페이지 번호
            limit: 페이지당 개수 (최대 100)
            order_by: 정렬 방식 (desc, asc)
            
        Returns:
            종료된 주문 내역 리스트
        """
        url = f"{self.server_url}/v1/orders"
        params = {
            'market': market,
            'state': 'done',
            'page': page,
            'limit': limit,
            'order_by': order_by
        }
        
        if to:
            params['to'] = to
            
        headers = self._get_auth_header(params)
        response = requests.get(url, params=params, headers=headers)
        
        return response.json() if response.status_code == 200 else []
    
    def get_balances(self) -> List[Dict]:
        """
        보유 자산 잔고 조회
        
        Returns:
            보유 자산 리스트
        """
        if self.logger:
            self.logger.info("보유 자산 잔고 조회 시작")
            
        url = f"{self.server_url}/v1/accounts"
        headers = self._get_auth_header()
        
        if self.logger:
            self.logger.debug(f"API 요청 URL: {url}")
            
        try:
            response = requests.get(url, headers=headers)
            
            if self.logger:
                self.logger.debug(f"API 응답 상태 코드: {response.status_code}")
                
            if response.status_code == 200:
                result = response.json()
                if self.logger:
                    self.logger.info(f"보유 자산 잔고 조회 성공 - 자산 수: {len(result)}")
                    for balance in result:
                        if float(balance.get('balance', 0)) > 0:
                            self.logger.debug(f"자산 정보: 화폐={balance.get('currency')}, 잔고={balance.get('balance')}, 평가금액={balance.get('avg_buy_price', '0')}원")
                return result
            else:
                if self.logger:
                    self.logger.error(f"보유 자산 잔고 조회 실패 - 상태 코드: {response.status_code}, 응답: {response.text}")
                return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"보유 자산 잔고 조회 중 예외 발생: {str(e)}")
            return []
    
    def get_market_info(self) -> List[Dict]:
        """
        KRW 마켓의 코인들만 필터링하여 제공
        
        Returns:
            마켓 정보 리스트
        """
        url = f"{self.server_url}/v1/market/all"
        params = {'isDetails': 'true'}
        headers = self._get_auth_header(params)
        
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            markets = response.json()
            # KRW 마켓만 필터링
            return [market for market in markets if market['market'].startswith('KRW-')]
        return []
    
    def get_market_name(self) -> Dict[str, str]:
        """
        마켓의 한글 이름 조회
        
        Returns:
            마켓 코드와 한글 이름 매핑 딕셔너리
        """
        markets = self.get_market_info()
        return {market['market']: market['korean_name'] for market in markets} 