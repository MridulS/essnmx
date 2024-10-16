# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
import pytest
import sciline as sl
import scipp as sc

from ess.nmx import default_parameters
from ess.nmx.const import DETECTOR_SHAPE, PIXEL_DIM, TOF_DIM
from ess.nmx.data import small_mcstas_2_sample, small_mcstas_3_sample
from ess.nmx.mcstas_loader import providers as load_providers
from ess.nmx.reduction import bin_time_of_arrival
from ess.nmx.types import DetectorIndex, FilePath, TimeBinSteps


@pytest.fixture(params=[small_mcstas_2_sample, small_mcstas_3_sample])
def mcstas_file_path(
    request: pytest.FixtureRequest, mcstas_2_deprecation_warning_context
) -> str:
    if request.param == small_mcstas_2_sample:
        with mcstas_2_deprecation_warning_context():
            return request.param()

    return request.param()


@pytest.fixture
def mcstas_workflow(mcstas_file_path: str) -> sl.Pipeline:
    pl = sl.Pipeline(
        [*load_providers, bin_time_of_arrival],
        params={
            FilePath: mcstas_file_path,
            TimeBinSteps: 50,
            **default_parameters,
        },
    )
    pl.set_param_series(DetectorIndex, range(3))
    return pl


def test_pipeline_builder(mcstas_workflow: sl.Pipeline, mcstas_file_path: str) -> None:
    assert mcstas_workflow.get(FilePath).compute() == mcstas_file_path


def test_pipeline_mcstas_loader(mcstas_workflow: sl.Pipeline) -> None:
    """Test if the loader graph is complete."""
    from ess.nmx.mcstas_loader import NMXData

    mcstas_workflow[DetectorIndex] = 0
    nmx_data = mcstas_workflow.compute(NMXData)
    assert isinstance(nmx_data, sc.DataGroup)
    assert nmx_data.sizes[PIXEL_DIM] == DETECTOR_SHAPE[0] * DETECTOR_SHAPE[1]


def test_pipeline_mcstas_reduction(mcstas_workflow: sl.Pipeline) -> None:
    """Test if the loader graph is complete."""
    from ess.nmx.reduction import NMXReducedData

    nmx_reduced_data = mcstas_workflow.compute(NMXReducedData)
    assert isinstance(nmx_reduced_data, sc.DataGroup)
    assert nmx_reduced_data.sizes[TOF_DIM] == 50
