import os
import pathlib
import numpy as np
from collections import OrderedDict

from fireworks import LaunchPad, Firework, FiretaskBase, FWAction, Workflow, FileWriteTask, FileTransferTask, explicit_serialize
from fireworks.core.rocket_launcher import rapidfire, launch_rocket
from infrastructure.lammps.fireworks.core_custom import AmbertoolsTasks
from pymatgen.core.structure import Molecule
from pymatgen.io.gaussian import GaussianOutput
from pymatgen.io.ambertools import PrmtopParser
from infrastructure.lammps.firetasks.write_inputs import WriteDataFile, WriteControlFile, WriteTleapScript,\
    TLEAP_SETTING_DEFAULTS
from infrastructure.lammps.firetasks.run import RunLammps, RunAntechamber, RunParmchk, RunTleap
from infrastructure.lammps.firetasks.parse_outputs import ProcessPrmtop
from infrastructure.gaussian.utils.utils import get_mol_formula

@explicit_serialize
class PrintFW(FiretaskBase):
    '''Firetask for confirming that modspec works as intended in ProcessPrmtop firetask'''
    def run_task(self, fw_spec):
        print(str(fw_spec['system_force_field_dict']))


if __name__ == "__main__":

    # set up the LaunchPad and reset it
    launchpad = LaunchPad(host="mongodb://superuser:idlewide@localhost:27017/fireworks?authSource=admin", uri_mode=True)
    launchpad.reset('', require_password=False)

    working_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_files", "data")
    # print(working_dir)



    # Preparing inputs for ambertools for species not using existing ff models
    # # Phen_type parameter prep
    Phen_type = 'dhps'
    Phen_type_gaussian_output = GaussianOutput(os.path.join(working_dir,Phen_type + '.out'))
    Phen_type_molecule = Phen_type_gaussian_output.structures[-1]
    Phen_type_molecule.set_charge_and_spin(Phen_type_gaussian_output.charge,
                                           Phen_type_gaussian_output.spin_multiplicity)
    Phen_type_label = get_mol_formula(Phen_type_molecule)
    # print([Phen_type_label])
    Phen_type_param_dict = PrmtopParser(os.path.join(working_dir, Phen_type_label + '.prmtop'),
                                        Phen_type_molecule,
                                        "").to_dict()

    # # Oh parameter prep
    Oh_gaussian_output = GaussianOutput(os.path.join(working_dir, 'oh.out'))
    Oh_molecule = Oh_gaussian_output.structures[-1]
    Oh_molecule.set_charge_and_spin(Oh_gaussian_output.charge,
                                    Oh_gaussian_output.spin_multiplicity)
    Oh_label = get_mol_formula(Oh_molecule)
    Oh_param_dict = PrmtopParser(os.path.join(working_dir, Oh_label + '.prmtop'),
                                 Oh_molecule,
                                 "").to_dict()

    # Preparing initial ff dict for species using existing ff models
    # # Spce parameter prep
    Spce_molecule = Molecule.from_file(os.path.join(working_dir,'SPC_E.pdb'))
    Spce_label = get_mol_formula(Spce_molecule)
    # print([Spce_label])
    # Spce_param_dict = {'Molecule': Spce_molecule,
    #                    'Labels': ['ow' + Spce_label, 'hw' + Spce_label, 'hw' + Spce_label],
    #                    'Masses': OrderedDict({'ow' + Spce_label: 16.000, 'hw' + Spce_label: 1.008}),
    #                    'Nonbond': [[0.155394259, 3.16555789], [0.0, 0.0]],
    #                    'Bonds': [{'coeffs': [553.0, 1], 'types': [('ow' + Spce_label, 'hw' + Spce_label)]}],
    #                    'Angles': [{'coeffs': [100.0, 109.47],
    #                                'types': [('hw' + Spce_label, 'ow' + Spce_label, 'hw' + Spce_label)]}],
    #                    'Dihedrals': [],
    #                    'Impropers': [],
    #                    'Improper Topologies': None,
    #                    'Charges': [-0.8476, 0.4238, 0.4238]}

    Spce_param_dict = {'Molecule': Spce_molecule,
                       'Labels': ['ow', 'hw', 'hw'],
                       'Masses': OrderedDict({'ow': 16.000, 'hw': 1.008}),
                       'Nonbond': [[0.155394259, 3.16555789], [0.0, 0.0]],
                       'Bonds': [{'coeffs': [553.0, 1], 'types': [('ow', 'hw')]}],
                       'Angles': [{'coeffs': [100.0, 109.47],
                                   'types': [('hw', 'ow', 'hw')]}],
                       'Dihedrals': [],
                       'Impropers': [],
                       'Improper Topologies': None,
                       'Charges': [-0.8476, 0.4238, 0.4238]}

    # # Na parameter prep
    Na_molecule = Molecule.from_file(os.path.join(working_dir,'Na.pdb'))
    Na_molecule.set_charge_and_spin(1)
    Na_label = get_mol_formula(Na_molecule)
    # print([Na_label])
#     Na_param_dict = {'Molecule': Na_molecule,
#                      'Labels': ['na' + Na_label],
#                      'Masses': OrderedDict({'na' + Na_label: 22.99}),
#                      'Nonbond': [[0.02639002, 2.590733472]],  # from frcmod.ions1lm_126_spce (2015)
# #                     'Nonbond': [[0.3526418, 2.159538]], # from frcmod.ionsjc_tip3p (2008)
#                      'Bonds': [],
#                      'Angles': [],
#                      'Dihedrals': [],
#                      'Impropers': [],
#                      'Improper Topologies': None,
#                      'Charges': [1.0]}

    Na_param_dict = {'Molecule': Na_molecule,
                     'Labels': ['na'],
                     'Masses': OrderedDict({'na': 22.99}),
                     'Nonbond': [[0.02639002, 2.590733472]],  # from frcmod.ions1lm_126_spce (2015)
                     #                     'Nonbond': [[0.3526418, 2.159538]], # from frcmod.ionsjc_tip3p (2008)
                     'Bonds': [],
                     'Angles': [],
                     'Dihedrals': [],
                     'Impropers': [],
                     'Improper Topologies': None,
                     'Charges': [1.0]}


    sys_ff_dict = {Phen_type_label: Phen_type_param_dict,
                   Oh_label: Oh_param_dict,
                   Na_label: Na_param_dict,
                   Spce_label: Spce_param_dict}

    spec = {"system_force_field_dict": sys_ff_dict}
    spec = {}

    # setting other inputs for creating the data file
    x = 1.0 # Phen_type concentration

    system_mixture_data_type = 'concentration'
    system_mixture_data = {'Solutes': {Phen_type_label: {'Initial Molarity': x, 'Final Molarity': x,
                                                         'Density': 1.25, 'Molar Weight': 180.21},
                                       Oh_label: {'Initial Molarity': 3 * x + 1, 'Final Molarity': 1,
                                                  'Density': 2.13, 'Molar Weight': 17.007},
                                       Na_label: {'Initial Molarity': 3 * x + 1, 'Final Molarity': 3 * x + 1,
                                                  'Density': 2.13, 'Molar Weight': 22.990}},
                           'Solvents': {Spce_label: {'Density': 0.99705, 'Molar Weight': 18.015}}}

    # # # other option for system_mixture_data
    # system_mixture_data_type = 'number of molecules'
    # system_mixture_data = {Phen_type_label: 9,
    #                        Spce_label: 438,
    #                        Oh_label: 9,
    #                        Na_label: 38}

    system_box_side_length = 25.0

    position_seed = 512454235

    data_filename = f'complex_from_{system_mixture_data_type}.data'


    # # From this point on, there shouldn't be any need to alter the script for
    # # getting gaff parameters using default methods
    #
    # t = []
    #
    # # Check that ff parameters for all molecular species are in "system_force_field_dict"
    # # t.append(PrintFW())
    #
    #
    # t.append(WriteDataFile(working_dir = working_dir,
    #                        data_filename = data_filename,
    #                        system_force_field_dict = sys_ff_dict,
    #                        system_mixture_data = system_mixture_data,
    #                        system_box_side_length = system_box_side_length,
    #                        system_mixture_data_type = system_mixture_data_type,
    #                        position_seed = position_seed))
    #
    # # assemble FireWork from tasks and give the FireWork a unique id
    # fire_work1 = Firework(t, spec = spec, name='MultMolFFDict', fw_id=1)
    #
    # # assemble Workflow from FireWorks and their connections by id
    # wf = Workflow([fire_work1])
    #
    # # store workflow and launch it
    # launchpad.add_wf(wf)
    # rapidfire(launchpad)

    sys_mix_type = "concentration"
    # sys_mix_type = "number of molecules"
    sys_species_data = {
        Phen_type_label: {
            "molecule": Phen_type_molecule,
            "ff_param_method": "get_from_dict",
            "ff_param_data": Phen_type_param_dict,
            "mol_mixture_type": "Solutes",
            "mixture_data": {'Initial Molarity': x,
                             'Final Molarity': x,
                             'Density': 1.25,
                             'Molar Weight': 180.21} if sys_mix_type == 'concentration' else 8},
        Spce_label: {
            "molecule": Spce_molecule,
            "ff_param_method": "get_from_dict",
            "ff_param_data": Spce_param_dict,
            "mol_mixture_type": "Solvents",
            "mixture_data": {'Density': 0.99705,
                             'Molar Weight': 18.015} if sys_mix_type == 'concentration' else 438},
        Oh_label: {
            "molecule": Oh_molecule,
            "ff_param_method": "get_from_dict",
            "ff_param_data": Oh_param_dict,
            "mol_mixture_type": "Solutes",
            "mixture_data": {'Initial Molarity': 3 * x + 1,
                             'Final Molarity': 1,
                             'Density': 2.13,
                             'Molar Weight': 17.007} if sys_mix_type == 'concentration' else 9},
        Na_label: {
            "molecule": Na_molecule,
            "ff_param_method": "get_from_dict",
            "ff_param_data": Na_param_dict,
            "mol_mixture_type": "Solutes",
            "mixture_data": {'Initial Molarity': 3 * x + 1,
                             'Final Molarity': 3 * x + 1,
                             'Density': 2.13,
                             'Molar Weight': 22.990} if sys_mix_type == 'concentration' else 38}
    }

    from infrastructure.lammps.workflows.base_standard import lammps_data_fws
    fws, links_dict = lammps_data_fws(sys_species_data,
                                      sys_mix_type,
                                      system_box_side_length,
                                      data_filename="test_complex.data",
                                      working_dir=working_dir)
    print(links_dict)
    # print(fws[0].keys())
    for firework in fws:
        print(firework)

    # launchpad.add_wf(Workflow(fws, links_dict))
    # rapidfire(launchpad)