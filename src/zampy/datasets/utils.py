"""Shared utilities from datasets."""
import urllib.request
from pathlib import Path
from typing import Optional
from typing import Union
import cdsapi
import pandas as pd
import requests
import xarray as xr
from tqdm import tqdm
from tqdm.contrib.itertools import product
from zampy.datasets import converter
from zampy.datasets.dataset_protocol import SpatialBounds
from zampy.datasets.dataset_protocol import TimeBounds
from zampy.reference.variables import VARIABLE_REFERENCE_LOOKUP


PRODUCT_FNAME = {
    "reanalysis-era5-single-levels": "era5",
    "reanalysis-era5-land": "era5-land",
}
CDSAPI_CONFIG_PATH = Path.home() / ".cdsapirc"


class TqdmUpdate(tqdm):
    """Wrap a tqdm progress bar to be updateable by urllib.request.urlretrieve."""

    def update_to(
        self, b: int = 1, bsize: int = 1, tsize: Optional[int] = None
    ) -> Union[bool, None]:
        """Update the progress bar.

        Args:
            b: Number of blocks transferred so far.
            bsize: Size of each block (in tqdm units).
            tsize: Total size (in tqdm units). If `None`, remains unchanged.
        """
        if tsize is not None:
            self.total = tsize
        return self.update(b * bsize - self.n)


def download_url(url: str, fpath: Path, overwrite: bool) -> None:
    """Download a URL, and display a progress bar for that file.

    Args:
        url: URL to be downloaded.
        fpath: File path to which the URL should be saved.
        overwrite: If an existing file (of the same size!) should be overwritten.
    """
    if get_file_size(fpath) != get_url_size(url) or overwrite:
        with TqdmUpdate(
            unit="B", unit_scale=True, miniters=1, desc=url.split("/")[-1]
        ) as t:
            urllib.request.urlretrieve(url, filename=fpath, reporthook=t.update_to)
    else:
        print(f"File '{fpath.name}' already exists, skipping...")


def get_url_size(url: str) -> int:
    """Return the size (bytes) of a given URL."""
    response = requests.head(url)
    return int(response.headers["Content-Length"])


def get_file_size(fpath: Path) -> int:
    """Return the size (bytes) of a given Path."""
    if not fpath.exists():
        return 0
    else:
        return fpath.stat().st_size


def cds_request(
    dataset: str,
    variables: list[str],
    time_bounds: TimeBounds,
    spatial_bounds: SpatialBounds,
    path: Path,
    cds_var_names: dict[str, str],
    overwrite: bool,
) -> None:
    """Download data via CDS API.

    To raise a request via CDS API, the user needs to set up the
    configuration file `.cdsapirc` following the instructions on
    https://cds.climate.copernicus.eu/api-how-to.

    Following the efficiency tips of request,
    https://confluence.ecmwf.int/display/CKB/Climate+Data+Store+%28CDS%29+documentation
    The downloading is organized by asking for one month of data per request.

    Args:
        dataset: Dataset name for retrieval via `cdsapi`.
        variables: Zampy variables.
        time_bounds: Zampy time bounds object.
        spatial_bounds: Zampy spatial bounds object.
        path: File path to which the data should be saved.
        cds_var_names: Variable names from CDS server side.
        overwrite: If an existing file (of the same size!) should be overwritten.
    """
    fname = PRODUCT_FNAME[dataset]

    with CDSAPI_CONFIG_PATH.open(encoding="utf8") as f:
        url = f.readline().split(":", 1)[1].strip()
        api_key = f.readline().split(":", 1)[1].strip()

    c = cdsapi.Client(
        url=url,
        key=api_key,
        verify=True,
        quiet=True,
    )

    # create list of year/month pairs
    year_month_pairs = time_bounds_to_year_month(time_bounds)

    for (year, month), variable in product(
        year_month_pairs, variables, position=0, leave=True
    ):
        # raise download request
        r = c.retrieve(
            dataset,
            {
                "product_type": "reanalysis",
                "variable": [cds_var_names[variable]],
                "year": year,
                "month": month,
                # fmt: off
                "day": [
                    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
                    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
                    "21", "22", "23", "24", "25", "26", "27", "28", "29", "30",
                    "31",
                ],
                "time": [
                    "00:00", "01:00", "02:00", "03:00", "04:00", "05:00", "06:00",
                    "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00",
                    "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00",
                    "21:00", "22:00", "23:00",
                ],
                # fmt: on
                "area": [
                    spatial_bounds.north,
                    spatial_bounds.west,
                    spatial_bounds.south,
                    spatial_bounds.east,
                ],
                "format": "netcdf",
            },
        )
        # check existence and overwrite
        fpath = path / f"{fname}_{variable}_{year}-{month}.nc"

        if get_file_size(fpath) != r.content_length or overwrite:
            r.download(fpath)
            tqdm.write(f"Download {fpath.name} successfully.")
        else:
            print(f"File '{fpath.name}' already exists, skipping...")


def time_bounds_to_year_month(time_bounds: TimeBounds) -> list[tuple[str, str]]:
    """Return year/month pairs."""
    date_range = pd.date_range(start=time_bounds.start, end=time_bounds.end, freq="M")
    year_month_pairs = [(str(date.year), str(date.month)) for date in date_range]
    return year_month_pairs


def convert_to_zampy(
    ingest_folder: Path,
    file: Path,
    overwrite: bool = False,
) -> None:
    """Convert the downloaded nc files to standard CF/Zampy netCDF files.

    The downloaded ERA5/ERA5-land data already follows CF1.6 convention. However,
    it uses (abbreviated) variable name instead of standard name, which prohibits
    the format conversion. Therefore we need to ingest the downloaded files and
    rename all variables to standard names.

    Args:
        ingest_folder: Folder where the files have to be written to.
        file: Path to the ERA5 nc file.
        overwrite: Overwrite all existing files. If False, file that already exist will
            be skipped.
    """
    ncfile = ingest_folder / file.with_suffix(".nc").name
    if ncfile.exists() and not overwrite:
        print(f"File '{ncfile.name}' already exists, skipping...")
    else:
        ds = parse_nc_file(file)

        ds.to_netcdf(path=ncfile)


var_reference_era5_to_zampy = {
    # era5 variables
    "mtpr": "total_precipitation",
    "strd": "surface_thermal_radiation_downwards",
    "ssrd": "surface_solar_radiation_downwards",
    "sp": "surface_pressure",
    "u10": "eastward_component_of_wind",
    "v10": "northward_component_of_wind",
    # era5-land variables
    "t2m": "air_temperature",
    "d2m": "dewpoint_temperature",
}

WATER_DENSITY = 997.0  # kg/m3


def parse_nc_file(file: Path) -> xr.Dataset:
    """Parse the downloaded ERA5 nc files, to CF/Zampy standard dataset.

    Args:
        file: Path to the ERA5 nc file.

    Returns:
        CF/Zampy formatted xarray Dataset
    """
    # Open chunked: will be dask array -> file writing can be parallelized.
    ds = xr.open_dataset(file, chunks={"x": 50, "y": 50})

    for variable in ds.variables:
        if variable in var_reference_era5_to_zampy:
            var = str(variable)  # Cast to string to please mypy
            variable_name = var_reference_era5_to_zampy[var]
            ds = ds.rename({var: variable_name})
            # convert radiation to flux J/m2 to W/m2
            # https://confluence.ecmwf.int/pages/viewpage.action?pageId=155337784
            if variable_name in (
                "surface_solar_radiation_downwards",
                "surface_thermal_radiation_downwards",
            ):
                ds[variable_name] = ds[variable_name] / 3600
            # conversion precipitation kg/m2s to mm/s
            elif variable_name == "total_precipitation":
                ds[variable_name] = ds[variable_name] / WATER_DENSITY
                ds[variable_name].attrs["units"] = "meter_per_second"
                # convert from m/s to mm/s
                ds = converter._convert_var(
                    ds, variable_name, VARIABLE_REFERENCE_LOOKUP[variable_name].unit
                )

            ds[variable_name].attrs["units"] = str(
                VARIABLE_REFERENCE_LOOKUP[variable_name].unit
            )
            ds[variable_name].attrs["description"] = VARIABLE_REFERENCE_LOOKUP[
                variable_name
            ].desc

    # TODO: add dataset attributes.

    return ds
