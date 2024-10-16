# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
import re
from typing import Dict, List

import scipp as sc
import scippnexus as snx

from .const import PIXEL_DIM, TOF_DIM
from .mcstas_xml import McStasInstrument, read_mcstas_geometry_xml
from .reduction import NMXData
from .types import (
    CrystalRotation,
    DetectorBankPrefix,
    DetectorIndex,
    DetectorName,
    EventData,
    FilePath,
    MaximumProbability,
    ProtonCharge,
    RawEventData,
)


def detector_name_from_index(index: DetectorIndex) -> DetectorName:
    return f'nD_Mantid_{index}'


def event_data_bank_name(
    detector_name: DetectorName, file_path: FilePath
) -> DetectorBankPrefix:
    '''Finds the filename associated with a detector'''
    for bank_name, det_names in read_bank_names_to_detector_names(file_path).items():
        if detector_name in det_names:
            return bank_name.partition('.')[0]


def raw_event_data(
    file_path: FilePath,
    bank_prefix: DetectorBankPrefix,
    detector_name: DetectorName,
    instrument: McStasInstrument,
) -> RawEventData:
    """Retrieve events from the nexus file."""
    coords = instrument.to_coords(detector_name)
    bank_name = f'{bank_prefix}_dat_list_p_x_y_n_id_t'
    with snx.File(file_path, 'r') as f:
        root = f["entry1/data"]
        (bank_name,) = (name for name in root.keys() if bank_name in name)
        data = root[bank_name]["events"][()].rename_dims({'dim_0': 'event'})
        return sc.DataArray(
            coords={
                PIXEL_DIM: sc.array(
                    dims=['event'],
                    values=data['dim_1', 4].values,
                    dtype='int64',
                    unit=None,
                ),
                TOF_DIM: sc.array(
                    dims=['event'], values=data['dim_1', 5].values, unit='s'
                ),
            },
            data=sc.array(
                dims=['event'], values=data['dim_1', 0].values, unit='counts'
            ),
        ).group(coords.pop('pixel_id'))


def crystal_rotation(
    file_path: FilePath, instrument: McStasInstrument
) -> CrystalRotation:
    """Retrieve crystal rotation from the file."""
    with snx.File(file_path, 'r') as file:
        return sc.vector(
            value=[file[f"entry1/simulation/Param/XtalPhi{key}"][...] for key in "XYZ"],
            unit=instrument.simulation_settings.angle_unit,
        )


def event_weights_from_probability(
    da: RawEventData,
    max_probability: MaximumProbability,
) -> EventData:
    """Create event weights by scaling probability data.

    event_weights = max_probability * (probabilities / max(probabilities))

    Parameters
    ----------
    da:
        The probabilities of the events

    max_probability:
        The maximum probability to scale the weights.

    """
    return sc.scalar(max_probability, unit='counts') * da / da.max()


def proton_charge_from_event_data(da: EventData) -> ProtonCharge:
    """Make up the proton charge from the event data array.

    Proton charge is proportional to the number of neutrons,
    which is proportional to the number of events.
    The scale factor is manually chosen based on previous results
    to be convenient for data manipulation in the next steps.
    It is derived this way since
    the protons are not part of McStas simulation,
    and the number of neutrons is not included in the result.

    Parameters
    ----------
    event_da:
        The event data

    """
    # Arbitrary number to scale the proton charge
    return ProtonCharge(sc.scalar(1 / 10_000, unit=None) * da.bins.size().sum().data)


def read_bank_names_to_detector_names(file_path: str) -> Dict[str, List[str]]:
    with snx.File(file_path) as file:
        description = file['entry1/instrument/description'][()]
    return bank_names_to_detector_names(description)


def bank_names_to_detector_names(description: str) -> Dict[str, List[str]]:
    """Associates event data names with the names of the detectors
    where the events were detected"""

    detector_component_regex = (
        # Start of the detector component definition, contains the detector name.
        r'^COMPONENT (?P<detector_name>.*) = Monitor_nD\(\n'
        # Some uninteresting lines, we're looking for 'filename'.
        # Make sure no new component begins.
        r'(?:(?!COMPONENT)(?!filename)(?:.|\s))*'
        # The line that defines the filename of the file that stores the
        # events associated with the detector.
        r'(?:filename = \"(?P<bank_name>[^\"]*)\")?'
    )
    matches = re.finditer(detector_component_regex, description, re.MULTILINE)
    bank_names_to_detector_names = {}
    for m in matches:
        bank_names_to_detector_names.setdefault(
            # If filename was not set for the detector the filename for the
            # event data defaults to the name of the detector.
            m.group('bank_name') or m.group('detector_name'),
            [],
        ).append(m.group('detector_name'))
    return bank_names_to_detector_names


def load_mcstas(
    *,
    da: EventData,
    proton_charge: ProtonCharge,
    crystal_rotation: CrystalRotation,
    detector_name: DetectorName,
    instrument: McStasInstrument,
) -> NMXData:
    coords = instrument.to_coords(detector_name)
    coords.pop('pixel_id')
    return NMXData(
        weights=da,
        proton_charge=proton_charge,
        crystal_rotation=crystal_rotation,
        **coords,
    )


providers = (
    read_mcstas_geometry_xml,
    detector_name_from_index,
    event_data_bank_name,
    raw_event_data,
    event_weights_from_probability,
    proton_charge_from_event_data,
    crystal_rotation,
    load_mcstas,
)
