"""Structured logging configuration for UDA-Hub."""

import logging
import json
import os
from datetime import datetime
from typing import Any, Dict
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "agent"):
            log_data["agent"] = record.agent
        if hasattr(record, "ticket_id"):
            log_data["ticket_id"] = record.ticket_id
        if hasattr(record, "thread_id"):
            log_data["thread_id"] = record.thread_id
        if hasattr(record, "tool_name"):
            log_data["tool_name"] = record.tool_name
        if hasattr(record, "tool_args"):
            log_data["tool_args"] = record.tool_args
        if hasattr(record, "tool_result"):
            log_data["tool_result"] = str(record.tool_result)[:500]  # Truncate long results
        if hasattr(record, "classification"):
            log_data["classification"] = record.classification
        if hasattr(record, "routing_decision"):
            log_data["routing_decision"] = record.routing_decision
        if hasattr(record, "outcome"):
            log_data["outcome"] = record.outcome
        if hasattr(record, "error"):
            log_data["error"] = str(record.error)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """
    Set up structured logging for the application.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("udahub")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with simple format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler with JSON format
    log_file = os.path.join(log_dir, f"udahub_{datetime.now().strftime('%Y%m%d')}.jsonl")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str = "udahub") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)

