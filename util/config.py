"""
설정 파일 관리 모듈

YAML 설정 파일을 로드하고 환경 변수를 처리합니다.
"""
import os
import yaml
import re
from typing import Dict, Any, Optional, Union, List, TypeVar, cast

# 환경 변수 패턴
ENV_VAR_PATTERN = re.compile(r'\${([A-Za-z0-9_]+)(:-([^}]+))?}')

# 제네릭 타입 정의
T = TypeVar('T')


class ConfigManager:
    """설정 파일 관리 클래스"""

    _instance = None
    _config: Optional[Dict[str, Any]] = None
    _config_path: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        """
        ConfigManager 초기화
        
        Args:
            config_path: 설정 파일 경로 (기본값: None)
        """
        if config_path and (self._config is None or config_path != self._config_path):
            self._config_path = config_path
            self._load_config()

    def _load_config(self) -> None:
        """설정 파일 로드 및 환경 변수 처리"""
        if not self._config_path or not os.path.exists(self._config_path):
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self._config_path}")

        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
            
        # 환경 변수 처리
        if self._config:
            self._process_env_vars(self._config)

    def _process_env_vars(self, config_section: Dict[str, Any]) -> None:
        """
        설정 값의 환경 변수 참조를 실제 환경 변수 값으로 대체
        
        Args:
            config_section: 처리할 설정 섹션
        """
        for key, value in config_section.items():
            if isinstance(value, dict):
                self._process_env_vars(value)
            elif isinstance(value, str):
                config_section[key] = self._replace_env_vars(value)

    def _replace_env_vars(self, value: str) -> str:
        """
        문자열 내의 환경 변수 참조를 실제 환경 변수 값으로 대체
        
        Args:
            value: 처리할 문자열
            
        Returns:
            str: 환경 변수가 대체된 문자열
        """
        def _replace_match(match):
            env_var_name = match.group(1)
            default_value = match.group(3)
            
            # 환경 변수 값 가져오기 (없으면 기본값 사용)
            env_value = os.environ.get(env_var_name)
            if env_value is not None:
                return env_value
            elif default_value is not None:
                return default_value
            else:
                return f"${{{env_var_name}}}"  # 환경 변수가 없고 기본값도 없으면 원래 표현식 유지
                
        return ENV_VAR_PATTERN.sub(_replace_match, value)

    def get_config(self) -> Dict[str, Any]:
        """
        전체 설정 반환
        
        Returns:
            Dict[str, Any]: 설정 정보
        """
        if self._config is None:
            raise ValueError("설정이 로드되지 않았습니다. 먼저 설정 파일을 지정하세요.")
        return self._config

    def get(self, key: str, default: Optional[T] = None) -> Union[Any, T]:
        """
        특정 설정값 반환
        
        Args:
            key: 설정 키 (점으로 구분된 경로, 예: 'telegram.token')
            default: 키가 없을 경우 반환할 기본값
            
        Returns:
            Any: 설정값 또는 기본값
        """
        if self._config is None:
            raise ValueError("설정이 로드되지 않았습니다. 먼저 설정 파일을 지정하세요.")

        keys = key.split('.')
        value: Any = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value

    def reload(self) -> None:
        """설정 파일 다시 로드"""
        if self._config_path:
            self._load_config()
        else:
            raise ValueError("설정 파일 경로가 지정되지 않았습니다.")


def load_config(platform: str, env: str) -> ConfigManager:
    """
    플랫폼과 환경에 맞는 설정 파일 로드
    
    Args:
        platform: 플랫폼 (upbit 또는 kis)
        env: 환경 (dev 또는 prod)
        
    Returns:
        ConfigManager: 설정 관리자 인스턴스
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config',
        f'{env}_config.yaml'
    )
    
    return ConfigManager(config_path) 