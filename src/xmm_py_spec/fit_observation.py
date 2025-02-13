import yaml
from pathlib import Path
import logging
from .analyze_spectral_variability import analyze_source
from .source import Source
from .plotting_settings import set_mpl


def setup_logging(output_path: Path):
    """Configure logging to both file and console."""
    # Create logs directory if it doesn't exist
    log_dir = output_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "fitting.log"

    # Clear the log file by opening it in write mode
    log_file.write_text('')

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)


def main():
    """
    Main entry point for fitting observations.
    Implemented in analyze_spectral_variability.py.
    """
    # Convert paths to absolute at the start
    base_path = Path("data/downloaded_spectra").resolve()
    output_path = Path("data").resolve()

    # Ensure base output directory exists
    output_path.mkdir(parents=True, exist_ok=True)

    # Set up logging and plotting
    setup_logging(output_path)
    set_mpl()

    try:
        with open("config/sources.yaml") as f:
            config = yaml.safe_load(f)
            logging.info("Successfully loaded configuration file")
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise

    for source_id, params in config["sources"].items():
        try:
            source = Source(
                source_id=source_id,
                redshift=params["redshift"],
                base_path=base_path
            )

            results_df = analyze_source(source, output_path)
            if results_df is not None and not results_df.empty:
                output_file = output_path / f"source_{source_id}_results.csv"
                results_df.to_csv(output_file, index=None)
                logging.info(f"Results saved to {output_file}")

        except Exception as e:
            logging.error(f"Failed to process source {source_id}: {e}")
            continue


if __name__ == "__main__":
    main()
