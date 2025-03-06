"""
한국투자증권 API 모듈

한국투자증권 API를 통해 시세 데이터를 가져오고 주문을 실행합니다.
"""
import os
import logging
import time
import json
from typing import Dict, List, Any, Optional, Union, Tuple

from util.config import ConfigManager
from util.api_base import APIBase


class KisAPI(APIBase):
    """한국투자증권 API 클래스"""

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, config: ConfigManager, logger: logging.Logger):
        """
        KisAPI 초기화
        
        Args:
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
        """
        super().__init__(config, logger)
        
        self.access_key = config.get('kis.access_key')
        self.secret_key = config.get('kis.secret_key')
        self.account_number = config.get('kis.account_number')
        self.account_code = config.get('kis.account_code', '01')
        
        if not self.access_key or not self.secret_key or not self.account_number:
            self.logger.error("한국투자증권 API 키가 설정되지 않았습니다.")
            raise ValueError("한국투자증권 API 키가 설정되지 않았습니다.")
        
        # 토큰 관리
        self.token = None
        self.token_expires_at = 0
        
        # API 요청 제한 설정 (한국투자증권 기준)
        self.request_limit = 20  # 초당 최대 요청 수
        self.request_reset_time = time.time() + 1  # 초 단위로 리셋

    def _get_auth_token(self) -> str:
        """
        인증 토큰 가져오기 (필요시 갱신)
        
        Returns:
            str: 인증 토큰
        """
        current_time = time.time()
        
        # 토큰이 없거나 만료되었으면 갱신
        if self.token is None or current_time >= self.token_expires_at:
            self._refresh_token()
            
        return self.token

    def _refresh_token(self) -> None:
        """인증 토큰 갱신"""
        url = f"{self.BASE_URL}/oauth2/tokenP"
        
        data = {
            "grant_type": "client_credentials",
            "appkey": self.access_key,
            "appsecret": self.secret_key
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            response = self._request('POST', url, data=data, headers=headers, auth_required=False)
            
            self.token = response.get('access_token')
            expires_in = response.get('expires_in', 86400)  # 기본 1일
            
            self.token_expires_at = time.time() + expires_in - 60  # 1분 여유
            self.logger.info("한국투자증권 API 토큰이 갱신되었습니다.")
            
        except Exception as e:
            self.logger.error(f"토큰 갱신 실패: {str(e)}")
            raise

    def _request_kis(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                data: Optional[Dict[str, Any]] = None, auth_required: bool = True) -> Dict[str, Any]:
        """
        한국투자증권 API 요청 실행
        
        Args:
            method: HTTP 메서드 (GET, POST)
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            data: 요청 데이터
            auth_required: 인증 필요 여부
            
        Returns:
            Dict[str, Any]: API 응답
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        # 헤더 설정
        headers = {
            "Content-Type": "application/json"
        }
        
        # 인증 필요시 토큰 추가
        if auth_required:
            token = self._get_auth_token()
            headers["Authorization"] = f"Bearer {token}"
            headers["appkey"] = self.access_key
            headers["appsecret"] = self.secret_key
            
        return self._request(method, url, params=params, data=data, headers=headers)

    def get_domestic_stock_price(self, symbol: str) -> Dict[str, Any]:
        """
        국내 주식 현재가 조회
        
        Args:
            symbol: 종목 코드 (예: 005930)
            
        Returns:
            Dict[str, Any]: 현재가 정보
        """
        endpoint = "/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        return self._request_kis('GET', endpoint, params=params)

    def get_domestic_stock_daily(self, symbol: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        국내 주식 일봉 조회
        
        Args:
            symbol: 종목 코드 (예: 005930)
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            
        Returns:
            Dict[str, Any]: 일봉 정보
        """
        endpoint = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1"
        }
        
        if start_date:
            params["FID_INPUT_DATE_1"] = start_date
        if end_date:
            params["FID_INPUT_DATE_2"] = end_date
            
        return self._request_kis('GET', endpoint, params=params)

    def get_overseas_stock_price(self, symbol: str, market: str) -> Dict[str, Any]:
        """
        해외 주식 현재가 조회
        
        Args:
            symbol: 종목 코드 (예: AAPL)
            market: 시장 코드 (예: NASD)
            
        Returns:
            Dict[str, Any]: 현재가 정보
        """
        endpoint = "/uapi/overseas-price/v1/quotations/price"
        params = {
            "AUTH": "",
            "EXCD": market,
            "SYMB": symbol
        }
        return self._request_kis('GET', endpoint, params=params)

    def get_overseas_stock_daily(self, symbol: str, market: str, 
                               start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        해외 주식 일봉 조회
        
        Args:
            symbol: 종목 코드 (예: AAPL)
            market: 시장 코드 (예: NASD)
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            
        Returns:
            Dict[str, Any]: 일봉 정보
        """
        endpoint = "/uapi/overseas-price/v1/quotations/dailyprice"
        params = {
            "AUTH": "",
            "EXCD": market,
            "SYMB": symbol,
            "GUBN": "0",
            "BYMD": start_date or "",
            "MODP": "0"
        }
        return self._request_kis('GET', endpoint, params=params)

    def get_account_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회
        
        Returns:
            Dict[str, Any]: 계좌 잔고 정보
        """
        endpoint = "/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        return self._request_kis('GET', endpoint, params=params)

    def order_domestic_stock(self, symbol: str, order_type: str, quantity: int, price: int = 0) -> Dict[str, Any]:
        """
        국내 주식 주문
        
        Args:
            symbol: 종목 코드 (예: 005930)
            order_type: 주문 유형 (01: 매도, 02: 매수)
            quantity: 주문 수량
            price: 주문 가격 (시장가 주문시 0)
            
        Returns:
            Dict[str, Any]: 주문 결과
        """
        endpoint = "/uapi/domestic-stock/v1/trading/order-cash"
        
        # 시장가 여부 결정
        if price == 0:
            price_type = "03"  # 시장가
        else:
            price_type = "00"  # 지정가
            
        data = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "PDNO": symbol,
            "ORD_DVSN": price_type,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
            "CTAC_TLNO": "",
            "SLL_BUY_DVSN_CD": order_type,
            "ALGO_NO": ""
        }
        
        return self._request_kis('POST', endpoint, data=data)

    def order_overseas_stock(self, symbol: str, market: str, order_type: str, 
                           quantity: int, price: float = 0) -> Dict[str, Any]:
        """
        해외 주식 주문
        
        Args:
            symbol: 종목 코드 (예: AAPL)
            market: 시장 코드 (예: NASD)
            order_type: 주문 유형 (1: 매도, 2: 매수)
            quantity: 주문 수량
            price: 주문 가격 (시장가 주문시 0)
            
        Returns:
            Dict[str, Any]: 주문 결과
        """
        endpoint = "/uapi/overseas-stock/v1/trading/order"
        
        # 시장가 여부 결정
        if price == 0:
            price_type = "00"  # 시장가
        else:
            price_type = "10"  # 지정가
            
        data = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "OVRS_EXCG_CD": market,
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price) if price > 0 else "",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": price_type,
            "SLL_BUY_DVSN_CD": order_type
        }
        
        return self._request_kis('POST', endpoint, data=data) 