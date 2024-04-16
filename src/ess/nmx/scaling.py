# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 Scipp contributors (https://github.com/scipp)
from typing import Any, Callable, NewType, Sequence

import scipp as sc

from .mtz_io import DEFAULT_WAVELENGTH_COLUMN_NAME, NMXMtzDataArray

# User defined or configurable types
WavelengthBinSize = NewType("WavelengthBinSize", int)
"""The size of the wavelength(LAMBDA) bins."""


# Computed types
WavelengthBinned = NewType("WavelengthBinned", sc.DataArray)
"""Binned mtz dataframe by wavelength(LAMBDA) with derived columns."""
ReferenceWavelengthBin = NewType("ReferenceWavelengthBin", sc.DataArray)
"""The reference bin in the binned dataset."""
ScaleFactorIntensity = NewType("ScaleFactorIntensity", float)
"""The scale factor for intensity."""
ScaleFactorSigmaIntensity = NewType("ScaleFactorSigmaIntensity", float)
"""The scale factor for the standard uncertainty of intensity."""
WavelengthScaled = NewType("WavelengthScaled", sc.DataArray)
"""Scaled wavelength by the reference bin."""


def get_lambda_binned(
    mtz_da: NMXMtzDataArray,
    wavelength_bin_size: WavelengthBinSize,
) -> WavelengthBinned:
    """Bin the whole dataset by wavelength(LAMBDA).

    Notes
    -----
        Wavelength(LAMBDA) binning should always be done on the merged dataset.

    """

    return WavelengthBinned(
        mtz_da.bin({DEFAULT_WAVELENGTH_COLUMN_NAME: wavelength_bin_size})
    )


def _is_bin_empty(binned: sc.DataArray, idx: int) -> bool:
    return binned[idx].values.size == 0


def _apply_elem_wise(func: Callable, var: sc.Variable) -> sc.Variable:
    """Apply a function element-wise to the variable values.

    This helper is only for vector-dtype variables.
    Use ``numpy.vectorize`` for other types.

    """

    def apply_func(val: Sequence, _cur_depth: int = 0) -> list:
        if _cur_depth == len(var.dims):
            return func(val)
        return [apply_func(v, _cur_depth + 1) for v in val]

    return sc.Variable(
        dims=var.dims,
        values=apply_func(var.values),
    )


def hash_variable(var: sc.Variable) -> sc.Variable:
    """Hash the coordinate values."""

    def _hash_repr(val: Any) -> int:
        return hash(str(val))

    return _apply_elem_wise(_hash_repr, var)


def get_reference_bin(
    binned: WavelengthBinned,
) -> ReferenceWavelengthBin:
    """Find the reference group in the binned dataset.

    The reference group is the group in the middle of the binned dataset.
    If the middle group is empty, the function will search for the nearest.

    Parameters
    ----------
    binned:
        The wavelength binned data.

    Raises
    ------
    ValueError:
        If no reference group is found.

    """
    middle_number, offset = len(binned) // 2, 0

    while 0 < (cur_idx := middle_number + offset) < len(binned) and _is_bin_empty(
        binned, cur_idx
    ):
        offset = -offset + 1 if offset <= 0 else -offset

    if _is_bin_empty(binned, cur_idx):
        raise ValueError("No reference group found.")

    ref: sc.DataArray = binned[cur_idx].values.copy(deep=False)
    ref.coords["hkl_eq_hash"] = hash_variable(ref.coords["hkl_eq"])
    grouped: sc.DataArray = ref.group("hkl_eq_hash")
    scale_factor_coords = ("I", "SIGI")
    for coord_name in scale_factor_coords:
        grouped.coords[f"scale_factor_{coord_name}"] = sc.concat(
            [sc.mean(1 / gr.values.coords[coord_name]) for gr in grouped],
            dim=grouped.dim,
        )

    return ReferenceWavelengthBin(grouped)


# Providers and default parameters
scaling_providers = (get_lambda_binned,)
"""Providers for scaling data."""
