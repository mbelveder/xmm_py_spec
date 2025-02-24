import yaml
from pathlib import Path
from .analyze_spectral_variability import analyze_source
from .source import Source


def main():
    base_path = Path("data/downloaded_spectra")
    output_path = Path("data/")

    with open("config/sources.yaml") as f:
        config = yaml.safe_load(f)

    for source_id, params in config["sources"].items():
        source = Source(
            source_id=source_id,
            redshift=params["redshift"],
            base_path=base_path
        )

        results_df = analyze_source(source, output_path)
        results_df.to_csv(
            output_path / f"source_{source_id}_results.csv",
            index=None
        )


if __name__ == "__main__":
    main()
