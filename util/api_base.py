"""
API 기본 모듈

API 요청을 처리하는 기본 클래스를 제공합니다.
"""
import logging
import time
import requests
from typing import Dict, Any, Optional, Union, List, Tuple

from util.config import ConfigManager


class APIBase:
    """API 기본 클래스"""

    def __init__(self, config: ConfigManager, logger: logging.Logger):
        """
        APIBase 초기화
        
        Args:
            config: 설정 관리자 인스턴스
            logger: 로거 인스턴스
        """
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        
        # API 요청 제한 관리
        self.request_limit = 30  # 분당 최대 요청 수 (기본값)
        self.request_count = 0
        self.request_reset_time = time.time() + 60
        
    def _handle_rate_limit(self) -> None:
        """API 요청 제한 처리"""
        current_time = time.time()
        
        # 시간이 지났으면 요청 카운트 초기화
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
        
    def _request(self, method: str, url: str, params: Optional[Dict[str, Any]] = None, 
                data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
                timeout: int = 10) -> Dict[str, Any]:
        """
        API 요청 실행
        
        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            url: API URL
            params: 쿼리 파라미터
            data: 요청 데이터
            headers: 요청 헤더
            timeout: 요청 타임아웃 (초)
            
        Returns:
            Dict[str, Any]: API 응답
        """
        self._handle_rate_limit()
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, json=data, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API 요청 실패: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"응답: {e.response.text}")
            raise
        except Exception as e:
            self.logger.error(f"API 요청 처리 중 오류 발생: {str(e)}")
            raise 