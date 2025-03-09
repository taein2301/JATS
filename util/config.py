"""
설정 파일 관리 모듈

YAML 설정 파일을 로드하고 환경 변수를 처리합니다.
"""
import os
import yaml
from typing import Dict, Any, Optional, Union, List, TypeVar, cast

# 제네릭 타입 정의
T = TypeVar('T')


class ConfigManager:
    """설정 파일 관리 클래스"""

    def __init__(self, env: str):
        """
        ConfigManager 초기화
        
        Args:
            env: 환경 (dev 또는 prod)
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config',
            f'{env}_config.yaml'
        )
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

    def get(self, key: str, default: Optional[T] = None) -> Union[Any, T]:
        """
        특정 설정값 반환
        
        Args:
            key: 설정 키 (점으로 구분된 경로, 예: 'telegram.token')
            default: 키가 없을 경우 반환할 기본값
            
        Returns:
            Any: 설정값 또는 기본값
        """
        keys = key.split('.')
        value: Any = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value


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
    
    return ConfigManager(env) 