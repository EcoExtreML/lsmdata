"""ERA5 dataset."""

from pathlib import Path
from typing import Union
import numpy as np
from zampy.datasets import utils
from zampy.datasets import validation
from zampy.datasets.dataset_protocol import Dataset
from zampy.datasets.dataset_protocol import SpatialBounds
from zampy.datasets.dataset_protocol import TimeBounds
from zampy.datasets.dataset_protocol import Variable
from zampy.datasets.dataset_protocol import write_properties_file
from zampy.reference.variables import unit_registry


## Ignore missing class/method docstrings: they are implemented in the Dataset class.
# ruff: noqa: D102


class ERA5(Dataset):  # noqa: D101
    name = "era5"
    time_bounds = TimeBounds(np.datetime64("1940-01-01"), np.datetime64("2023-06-30"))
    spatial_bounds = SpatialBounds(90, 180, -90, -180)

    raw_variables = (
        Variable(name="mtpr", unit=unit_registry.precipitation),
        Variable(name="strd", unit=unit_registry.radiation),
        Variable(name="ssrd", unit=unit_registry.radiation),
        Variable(name="sp", unit=unit_registry.pascal),
        Variable(name="u10", unit=unit_registry.velocity),
        Variable(name="v10", unit=unit_registry.velocity),
    )

    variable_names = (
        "mean_total_precipitation_rate",
        "surface_thermal_radiation_downwards",
        "surface_solar_radiation_downwards",
        "surface_pressure",
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
    )

    license = "cc-by-4.0"
    bib = """
    @article{hersbach2020era5,
        title={The ERA5 global reanalysis},
        author={Hersbach, Hans et al.},
        journal={Quarterly Journal of the Royal Meteorological Society},
        volume={146},
        number={730},
        pages={1999--2049},
        year={2020},
        publisher={Wiley Online Library}
        }
    """

    def download(  # noqa: PLR0913
        self,
        download_dir: Path,
        time_bounds: TimeBounds,
        spatial_bounds: SpatialBounds,
        variable_names: list[str],
        overwrite: bool = False,
    ) -> bool:
        validation.validate_download_request(
            self,
            download_dir,
            time_bounds,
            spatial_bounds,
            variable_names,
        )

        download_folder = download_dir / self.name
        download_folder.mkdir(parents=True, exist_ok=True)

        utils.cds_request(
            product="reanalysis-era5-single-levels",
            variables=variable_names,
            time_bounds=time_bounds,
            spatial_bounds=spatial_bounds,
            path=download_folder,
            overwrite=overwrite,
        )

        write_properties_file(
            download_folder, spatial_bounds, time_bounds, variable_names
        )

        return True

    def ingest(
        self,
        download_dir: Path,
        ingest_dir: Path,
        overwrite: bool = False,
    ) -> bool:
        return True

    # def load(  # noqa: PLR0913
    #     self,
    #     ingest_dir: Path,
    #     time_bounds: TimeBounds,
    #     spatial_bounds: SpatialBounds,
    #     resolution: float,
    #     regrid_method: str,
    #     variable_names: List[str],
    # ) -> None:
    #     pass

    def convert(
        self,
        ingest_dir: Path,
        convention: Union[str, Path],
    ) -> bool:
        return True
