import yaml
from pathlib import Path
from .analyze_spectral_variability import analyze_source
from .source import Source
from .logging_config import setup_logging
import logging


def main():
    base_path = Path("data/downloaded_spectra")
    output_path = Path("data/")
    log_dir = output_path / "logs"

    # Setup logging before any operations
    setup_logging(log_dir, "fit_observation_")

    with open("config/sources.yaml") as f:
        config = yaml.safe_load(f)

    for source_id, params in config["sources"].items():
        logging.info(f"\nProcessing source: {source_id}")
        logging.info(f"Parameters: {params}")

        source = Source(
            source_id=source_id,
            redshift=params["redshift"],
            base_path=base_path
        )

        try:
            results_df = analyze_source(source, output_path)
            output_file = output_path / f"source_{source_id}_results.csv"
            results_df.to_csv(output_file, index=None)
            logging.info(f"Results saved to: {output_file}")
        except Exception as e:
            logging.error(f"Failed to analyze source {source_id}: {e}")
            logging.debug("Traceback:", exc_info=True)


if __name__ == "__main__":
    main()
