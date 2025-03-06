"""
로깅 모듈

파일 및 콘솔 로깅, 로그 레벨 관리, 로그 포맷팅, 로그 로테이션 기능을 제공합니다.
"""
import os
import logging
import datetime
from logging.handlers import TimedRotatingFileHandler
import colorlog
from typing import Optional, Dict, Any

from util.config import ConfigManager


class Logger:
    """로깅 기능을 위한 메인 클래스"""

    _loggers: Dict[str, logging.Logger] = {}

    @classmethod
    def get_logger(cls, name: str, platform: str, config: ConfigManager) -> logging.Logger:
        """
        로거 인스턴스 반환
        
        Args:
            name: 로거 이름
            platform: 플랫폼 (upbit 또는 kis)
            config: 설정 관리자 인스턴스
            
        Returns:
            logging.Logger: 로거 인스턴스
        """
        if name in cls._loggers:
            return cls._loggers[name]

        # 로그 레벨 설정
        log_level_str = config.get('logging.level', 'INFO')
        log_level = getattr(logging, log_level_str)

        # 로거 생성
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        
        # 이미 핸들러가 있으면 추가하지 않음
        if logger.handlers:
            cls._loggers[name] = logger
            return logger

        # 로그 포맷 설정
        log_format = '%(asctime)s [%(levelname)s] %(name)s - %(message)s [%(filename)s:%(lineno)d]'
        date_format = '%Y-%m-%d %H:%M:%S'

        # 콘솔 핸들러 설정 (색상 지원)
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(log_level)
        
        color_formatter = colorlog.ColoredFormatter(
            '%(log_color)s' + log_format,
            datefmt=date_format,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(color_formatter)
        logger.addHandler(console_handler)

        # 파일 핸들러 설정
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
        os.makedirs(log_dir, exist_ok=True)
        
        today = datetime.datetime.now().strftime('%Y%m%d')
        log_file = os.path.join(log_dir, f'{platform}-{today}.log')
        
        # 로그 로테이션 설정
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=config.get('logging.backup_count', 30),
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        cls._loggers[name] = logger
        return logger


def setup_logger(name: str, platform: str, config: ConfigManager) -> logging.Logger:
    """
    로거 설정 및 반환
    
    Args:
        name: 로거 이름
        platform: 플랫폼 (upbit 또는 kis)
        config: 설정 관리자 인스턴스
        
    Returns:
        logging.Logger: 설정된 로거 인스턴스
    """
    return Logger.get_logger(name, platform, config) 