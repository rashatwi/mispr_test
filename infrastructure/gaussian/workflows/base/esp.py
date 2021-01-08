# coding: utf-8


# Defines the electrostatic partial charges workflow.

import os
import logging

from fireworks import Firework, Workflow

from infrastructure.gaussian.utils.utils import get_job_name, \
    recursive_relative_to_absolute_path, handle_gaussian_inputs
from infrastructure.gaussian.fireworks.core import CalcFromRunsDBFW
from infrastructure.gaussian.firetasks.parse_outputs import ESPtoDB
from infrastructure.gaussian.workflows.base.core import common_fw, \
    WORKFLOW_KWARGS

__author__ = "Rasha Atwi"
__maintainer__ = "Rasha Atwi"
__email__ = "rasha.atwi@stonybrook.edu"
__status__ = "Development"
__date__ = "Jan 2021"
__version__ = 0.2


logger = logging.getLogger(__name__)


def get_esp_charges(mol_operation_type,
                    mol,
                    db=None,
                    name="esp_charges_calculation",
                    working_dir=None,
                    opt_gaussian_inputs=None,
                    freq_gaussian_inputs=None,
                    esp_gaussian_inputs=None,
                    solvent_gaussian_inputs=None,
                    solvent_properties=None,
                    cart_coords=True,
                    oxidation_states=None,
                    skip_opt_freq=False,
                    **kwargs):
    fws = []
    working_dir = working_dir or os.getcwd()
    mol = recursive_relative_to_absolute_path(mol, working_dir)
    gout_keys = ["mol", "mol_esp"]

    gaussian_inputs = handle_gaussian_inputs({"opt": opt_gaussian_inputs,
                                              "freq": freq_gaussian_inputs,
                                              "esp": esp_gaussian_inputs},
                                             solvent_gaussian_inputs,
                                             solvent_properties)
    opt_gaussian_inputs = gaussian_inputs["opt"]
    freq_gaussian_inputs = gaussian_inputs["freq"]
    esp_gaussian_inputs = gaussian_inputs["esp"]

    _, label, opt_freq_fws = common_fw(mol_operation_type=mol_operation_type,
                                       mol=mol,
                                       working_dir=working_dir,
                                       db=db,
                                       opt_gaussian_inputs=opt_gaussian_inputs,
                                       freq_gaussian_inputs=freq_gaussian_inputs,
                                       cart_coords=cart_coords,
                                       oxidation_states=oxidation_states,
                                       gout_keys=gout_keys[0],
                                       skip_opt_freq=skip_opt_freq,
                                       **kwargs)
    fws += opt_freq_fws

    # input_parameters from a previous run are overwritten
    if "input_parameters" not in esp_gaussian_inputs:
        mol_esp = os.path.join(
            working_dir, "{}_esp".format(
                os.path.join(working_dir, label, "ESP", label)))
        esp_gaussian_inputs.update({"input_parameters": {mol_esp: None}})

    spec = kwargs.pop("spec", {})
    if not skip_opt_freq:
        spec.update({"proceed": {"has_gaussian_completed": True,
                                 "stationary_type": "Minimum"}})
    else:
        spec.update({"proceed": {"has_gaussian_completed": True}})

    esp_fw = CalcFromRunsDBFW(db,
                              input_file="{}_esp.com".format(label),
                              output_file="{}_esp.out".format(label),
                              name=get_job_name(label, "esp"),
                              parents=fws[:],
                              gaussian_input_params=esp_gaussian_inputs,
                              working_dir=os.path.join(working_dir, label,
                                                       "ESP"),
                              cart_coords=cart_coords,
                              gout_key=gout_keys[1],
                              spec=spec,
                              **kwargs
                              )
    fws.append(esp_fw)

    fw_analysis = Firework(
        ESPtoDB(db=db,
                keys=gout_keys,
                solvent_gaussian_inputs=solvent_gaussian_inputs,
                solvent_properties=solvent_properties,
                **{i: j for i, j in kwargs.items()
                   if i in ESPtoDB.required_params +
                   ESPtoDB.optional_params}),
        parents=fws[:],
        name="{}-{}".format(label, "esp_analysis"),
        spec={"_launch_dir": os.path.join(working_dir, "analysis")})
    fws.append(fw_analysis)

    return Workflow(fws,
                    name=get_job_name(label, name),
                    **{i: j for i, j in kwargs.items()
                       if i in WORKFLOW_KWARGS})
