import logging
from pathlib import Path
from datetime import datetime

class MatplotlibFilter(logging.Filter):
    """Filter out matplotlib debug messages."""
    def filter(self, record):
        return not record.name.startswith('matplotlib')

def setup_logging(output_dir: Path, prefix: str = "") -> None:
    """Configure logging to both file and console with detailed formatting.
    
    Args:
        output_dir: Directory to store log files
        prefix: Optional prefix for log filename
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"{prefix}fit_session_{timestamp}.log"
    
    # Create formatters for file and console
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s'
    )

    # Configure file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add filter for matplotlib
    matplotlib_filter = MatplotlibFilter()
    file_handler.addFilter(matplotlib_filter)
    console_handler.addFilter(matplotlib_filter)
    
    # Set matplotlib logging level to WARNING
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    # Reduce other common noisy loggers
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('fontTools').setLevel(logging.WARNING)

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info(f"Log file created: {log_file}")
