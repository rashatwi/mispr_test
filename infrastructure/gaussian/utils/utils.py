# coding: utf-8


# Contains utility functions useful in many of the infrastructure levels.

import os
import json
import logging
import random

import pybel as pb

from copy import deepcopy

from bson.objectid import ObjectId

from openbabel import OBMolBondIter

from pymatgen.core.structure import Molecule
from pymatgen.io.gaussian import GaussianInput, GaussianOutput
from pymatgen.io.babel import BabelMolAdaptor

from fireworks.utilities.fw_utilities import get_slug
from fireworks.fw_config import CONFIG_FILE_DIR
from fireworks import FileWriteTask

__author__ = "Rasha Atwi"
__maintainer__ = "Rasha Atwi"
__email__ = "rasha.atwi@stonybrook.edu"
__status__ = "Development"
__date__ = "Jan 2021"
__version__ = 0.2

logger = logging.getLogger(__name__)

JOB_TYPES = {"sp", "opt", "freq", "irc", "ircmax", "scan", "polar", "admp",
             "bomd", "eet", "force", "stable", "volume", "density", "guess",
             "pop", "scrf", "cphf", "prop", "nmr", "cis", "zindo", "td", "eom",
             "sac-ci"}
SCRF_MODELS = {"pcm", "iefpcm", "cpcm", "dipole", "ipcm", "isodensity",
               "scipcm", "smd"}

STANDARD_OPT_GUASSIAN_INPUT = {"functional": "B3LYP",
                               "basis_set": "6-31G(d)",
                               "route_parameters": {"Opt": None},
                               "link0_parameters": {"%chk": "checkpoint.chk",
                                                    "%mem": "45GB",
                                                    "%NProcShared": "24"}}


def process_mol(operation_type, mol, local_opt=False, **kwargs):
    # TODO: seems like it is not taking kwargs correctly, if None, correct?
    working_dir = kwargs["working_dir"] if "working_dir" in kwargs \
        else os.getcwd()
    db = get_db(kwargs["db"]) if "db" in kwargs else get_db()

    if operation_type == "get_from_mol":
        if not isinstance(mol, Molecule):
            raise Exception("mol is not a Molecule object; either "
                            "provide a Molecule object or use another "
                            "operation type with its corresponding inputs")
        output_mol = mol

    elif operation_type == "get_from_file":
        if not os.path.isabs(mol):
            file_path = os.path.join(working_dir, mol)
        else:
            file_path = mol
        if not os.path.exists(file_path):
            raise Exception("mol is not a valid path; either provide a valid "
                            "path or use another operation type with its "
                            "corresponding inputs")

        output_mol = Molecule.from_file(file_path)

    elif operation_type == "get_from_str":
        str_type = kwargs.get("str_type")
        if str_type is None:
            raise ValueError("a mol string format must be specified to process "
                             "the input string")
        output_mol = Molecule.from_str(mol, str_type)

    elif operation_type == "get_from_mol_db":
        # mol = mol_inchi
        mol_dict = db.retrieve_molecule(mol)
        if not mol_dict:
            raise Exception(
                "mol is not found in the database")
        output_mol = Molecule.from_dict(mol_dict)

    elif operation_type == "get_from_gout":
        if not isinstance(mol, GaussianOutput):
            raise Exception("mol is not a GaussianOutput object; either "
                            "provide a GaussianOutput object or use another "
                            "operation type with its corresponding inputs")
        output_run = mol.as_dict()
        output_mol = Molecule.from_dict(output_run["output"]["molecule"])

    elif operation_type == "get_from_run_dict":
        if not isinstance(mol, dict) and "output" not in mol:
            raise Exception("mol is not a GaussianOutput dictionary; either "
                            "provide a GaussianOutput dictionary or use "
                            "another operation type with its corresponding "
                            "inputs")
        output_mol = Molecule.from_dict(mol["output"]["output"]["molecule"])

    elif operation_type == "get_from_run_id":
        # mol = run_id
        run = db.runs.find_one({"_id": ObjectId(mol)})
        if not run:
            raise Exception("Gaussian run is not in the database")
        mol_dict = run["output"]["output"]["molecule"]
        output_mol = Molecule.from_dict(mol_dict)

    elif operation_type == "get_from_run_query":
        # mol = {"inchi": inchi, "type": type, "functional": func,
        #        "basis": basis, "phase": phase, ...}
        logger.info("If the query criteria satisfy more than "
                    "one document, the last updated one will "
                    "be used. To perform a more specific "
                    "search, provide the document id using "
                    "gout_id")
        run = db.retrieve_run(**mol)
        if not run:
            raise Exception("Gaussian run is not in the database")
        run = max(run, key=lambda i: i["last_updated"])
        mol_dict = run["output"]["output"]["molecule"]
        output_mol = Molecule.from_dict(mol_dict)

    elif operation_type == "derive_molecule":
        # mol = {"operation_type": "get_from_file", "mol": file_path,
        #        "func_grp": func_group_name, ....}

        func_grp_name = mol.get("func_grp")
        if not func_grp_name:
            raise Exception("No FG provided; Provide the name of the FG "
                            "to be retrieved from the database")
        fg_dict = db.retrieve_fg(func_grp_name)
        if not fg_dict:
            raise Exception("FG is not found in the database")
        fg = Molecule(fg_dict["species"], fg_dict["coords"])

        output_mol = process_mol(operation_type=mol["operation_type"],
                                 mol=mol["mol"], **kwargs)
        output_mol.substitute(mol["index"], fg, mol["bond_order"])

    elif operation_type == "link_molecules":
        # TODO: add a checking step in the original molecule to make sure no
        #  overlapping happens
        # mol = {"operation_type": ["get_from_file", "get_from_mol_db"],
        #        "mol": ["kes/rasa/defe.xyz", "mol_inchi"],
        #        "index": [3, 5],
        #        "bond_order": 2}

        # mol = {"operation_type": ["get_from_file", "derive_molecule"],
        #        "mol": ["kes/rasa/defe.xyz", {"operation_type":
        #        "get_from_mol_db, "mol": inchi}],
        #        "index": [3, 5],
        #        "bond_order": 2}
        linking_mol = process_mol(operation_type=mol["operation_type"][0],
                                  mol=mol["mol"][0], **kwargs)
        linked_mol = process_mol(operation_type=mol["operation_type"][1],
                                 mol=mol["mol"][1], **kwargs)
        output_mol = linking_mol.link(linked_mol, mol["index"][0],
                                      mol["index"][1], mol["bond_order"])

    else:
        raise ValueError(f"operation type {operation_type} is not supported")

    if local_opt:
        force_field = kwargs.get("force_field", "mmff94")
        steps = kwargs.get("steps", 500)
        output_mol = perform_local_opt(output_mol, force_field, steps)

    charge = kwargs.get("charge")
    charge = charge if charge is not None else output_mol.charge
    output_mol.set_charge_and_spin(charge)
    return output_mol


def process_run(operation_type, run, input_file=None, **kwargs):
    working_dir = kwargs.get("working_dir", os.getcwd())
    db = get_db(kwargs["db"]) if "db" in kwargs else get_db()

    if operation_type == "get_from_gout":
        if not isinstance(run, GaussianOutput):
            raise Exception("run is not a GaussianOutput object; either "
                            "provide a GaussianOutput object or use another "
                            "operation type with its corresponding inputs")
        gout = run.as_dict()
        gout_dict = _cleanup_gout(gout, working_dir, input_file)

    elif operation_type == "get_from_file":
        if not os.path.isabs(run):
            file_path = os.path.join(working_dir, run)
        else:
            file_path = run
        if not os.path.exists(file_path):
            raise Exception("run is not a valid path; either provide a valid "
                            "path or use another operation type with its "
                            "corresponding inputs")
        try:
            gout = GaussianOutput(file_path).as_dict()
            gout_dict = _cleanup_gout(gout, working_dir, input_file)
        except IndexError:
            raise ValueError("run is not a Gaussian output file; either "
                             "provide a valid Gaussian output file or use "
                             "another operation type with its corresponding "
                             "inputs")

    elif operation_type == "get_from_run_dict":
        if not isinstance(run, dict) and "output" not in run:
            raise Exception("run is not a GaussianOutput dictionary; either"
                            "provide a GaussianOutput dictionary or use another"
                            "operation type with its corresponding inputs")
        gout_dict = run

    elif operation_type == "get_from_run_id":
        # run = run_id
        run = db.runs.find_one({"_id": ObjectId(run)})
        if not run:
            raise Exception("Gaussian run is not in the database")
        gout_dict = run

    elif operation_type == "get_from_run_query":
        # run = {"inchi": inchi, "smiles": smiles, "type": type,
        #        "functional": func, "basis": basis, "phase": phase, ...}
        logger.info("If the query criteria satisfy more than "
                    "one document, the last updated one will "
                    "be used. To perform a more specific "
                    "search, provide the document id using "
                    "gout_id")
        run = db.retrieve_run(**run)
        if not run:
            raise Exception("Gaussian run is not in the database")
        run = max(run, key=lambda i: i["last_updated"])
        gout_dict = run

    else:
        raise ValueError(f"operation type {operation_type} is not supported")
    # TODO: find a better way; seems hacky!
    if "_id" in gout_dict:
        gout_dict["_id"] = str(gout_dict["_id"])
    if "last_updated" in gout_dict:
        del gout_dict["last_updated"]
    gout_dict = json.loads(json.dumps(gout_dict))
    gout_dict = recursive_signature_remove(gout_dict)

    return gout_dict


def perform_local_opt(mol, force_field="uff", steps=200):
    a = BabelMolAdaptor(mol)
    a.localopt(forcefield=force_field, steps=steps)
    mol_opt = a.pymatgen_mol
    return mol_opt


def pass_gout_dict(fw_spec, key):
    # TODO: check this again
    gout_dict = fw_spec.get("gaussian_output", {}).get(key)
    proceed_keys = fw_spec.get("proceed", {})
    for k, v in proceed_keys.items():
        if gout_dict["output"].get(k,
                                   gout_dict["output"]["output"].get(k)) != v:
            raise ValueError(
                f"The condition for {k} is not met, Terminating"
            )
    return gout_dict


def get_chem_schema(mol):
    mol_dict = mol.as_dict()
    comp = mol.composition
    a = BabelMolAdaptor(mol)
    pm = pb.Molecule(a.openbabel_mol)
    # svg = pm.write("svg")
    mol_dict.update({"smiles": pm.write("smi").strip(),
                     "inchi": pm.write("inchi").strip("\n"),
                     "formula": comp.formula,
                     "formula_pretty": comp.reduced_formula,
                     "formula_anonymous": comp.anonymized_formula,
                     "formula_alphabetical": comp.alphabetical_formula,
                     "chemsys": comp.chemical_system,
                     "nsites": mol.num_sites,
                     "nelements":
                         len(comp.chemical_system.replace("-", " ").split(" ")),
                     "is_ordered": mol.is_ordered,
                     "is_valid": mol.is_valid()})
    return mol_dict


def get_mol_formula(mol):
    mol_schema = get_chem_schema(mol)
    return mol_schema["formula_alphabetical"].replace(" ", "")


def get_job_name(mol, name):
    if not isinstance(mol, Molecule):
        job_name = "{}_{}".format(mol, name)
    else:
        mol_formula = get_mol_formula(mol)
        job_name = "{}_{}".format(mol_formula, name)
    return job_name


def get_bond_order_str(mol):
    """
    Finds bond order as a string by iterating over bonds of a molecule. First
    converts pymatgen mol to openbabel mol to use openbabel in finding bond
    order.
    """
    bond_order = {}
    a = BabelMolAdaptor(mol).openbabel_mol
    for bond in OBMolBondIter(a):
        atom_indices = \
            tuple(sorted([bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]))
        order = bond.GetBondOrder()
        if order == 0:
            bond_order[atom_indices] = "U"
        elif order == 1:
            bond_order[atom_indices] = "S"
        elif order == 2:
            bond_order[atom_indices] = "D"
        elif order == 3:
            bond_order[atom_indices] = "T"
        elif order == 5:
            bond_order[atom_indices] = "A"
        else:
            raise TypeError(
                "Bond order number {} is not understood".format(order))
    return bond_order


def get_rdkit_mol(mol, sanitize=True, remove_h=False):
    """
    Converts a pymatgen mol object to RDKit rdmol object. Uses RDKit to perform
    the conversion <http://rdkit.org>. Accounts for aromaticity.
    """
    try:
        import rdkit
        from rdkit import Chem
        from rdkit.Geometry import Point3D
    except ModuleNotFoundError:
        raise ImportError("This function requires RDKit to be installed.")

    mol_species = [str(s) for s in mol.species]
    mol_coords = mol.cart_coords

    rdkit_mol = Chem.rdchem.EditableMol(Chem.rdchem.Mol())
    conformer = Chem.Conformer(len(mol_species))

    for index, (specie, coord) in enumerate(zip(mol_species, mol_coords)):
        rdkit_atom = Chem.rdchem.Atom(specie)
        rdkit_mol.AddAtom(rdkit_atom)
        conformer.SetAtomPosition(index, Point3D(*coord))

    rdkit_bonds = Chem.rdchem.BondType
    bond_order_mapping = {"U": rdkit_bonds.UNSPECIFIED, "S": rdkit_bonds.SINGLE,
                          "D": rdkit_bonds.DOUBLE, "T": rdkit_bonds.TRIPLE,
                          "A": rdkit_bonds.AROMATIC}
    bond_orders = get_bond_order_str(mol)

    for bond, bond_order in bond_orders.items():
        order = bond_order_mapping[bond_order]
        rdkit_mol.AddBond(bond[0] - 1, bond[1] - 1, order)

    rdkit_mol = rdkit_mol.GetMol()
    if sanitize:
        # if sanitization fails, inform the user and proceed normally
        try:
            Chem.SanitizeMol(rdkit_mol)
        except Exception as e:
            logger.info("Could not sanitize rdkit mol: {}".format(e))
    rdkit_mol.AddConformer(conformer, assignId=False)
    if remove_h:
        rdkit_mol = Chem.RemoveHs(rdkit_mol, sanitize=sanitize)

    return rdkit_mol


def draw_rdkit_mol(rdkit_mol, filename="mol.png", working_dir=None):
    from rdkit.Chem import Draw, AllChem
    working_dir = working_dir or os.getcwd()
    AllChem.Compute2DCoords(rdkit_mol)
    Draw.MolToFile(rdkit_mol, os.path.join(working_dir, filename))


def draw_rdkit_mol_with_highlighted_bonds(rdkit_mol, bonds,
                                          filename="mol.png",
                                          colors=None,
                                          working_dir=None):
    def _generate_color():
        bond_color = (random.random(), random.random(), random.random())
        # prevent the generation of a white color
        if bond_color == (1.0, 1.0, 1.0):
            bond_color = _generate_color()
        return bond_color

    from rdkit.Chem.Draw import rdMolDraw2D
    from rdkit import Chem, Geometry
    from rdkit.Chem import rdDepictor

    working_dir = working_dir or os.getcwd()
    rdDepictor.SetPreferCoordGen(True)
    d = rdMolDraw2D.MolDraw2DCairo(500, 500)
    rdkit_mol_copy = Chem.Mol(rdkit_mol.ToBinary())
    # optimize 2D depiction
    rdDepictor.Compute2DCoords(rdkit_mol_copy, bondLength=1.5)
    d.SetFontSize(0.6 * d.FontSize())  # reduce font size of bond number

    highlighted_bonds = []
    for i, bond in enumerate(bonds):
        ind = rdkit_mol_copy.GetBondBetweenAtoms(*bond).GetIdx()
        rdkit_mol_copy.GetBondWithIdx(ind).SetProp("bondNote", str(i))
        highlighted_bonds.append(ind)

    # use randomly generated colors if no or wrong number of colors are provided
    if not colors or len(colors) < len(bonds):
        colors = []
        for i in range(len(bonds)):
            colors.append(_generate_color())

    bond_colors = {}
    for i, bond in enumerate(highlighted_bonds):
        bond_colors[bond] = colors[i]

    rdMolDraw2D.PrepareAndDrawMolecule(d, rdkit_mol_copy,
                                       highlightBonds=highlighted_bonds,
                                       highlightBondColors=bond_colors)

    d.DrawMolecule(rdkit_mol_copy)
    d.FinishDrawing()
    d.WriteDrawingText(os.path.join(working_dir, filename))
    return colors


def calc_energy(rdkit_mol, maxIters=200):
    from rdkit.Chem import AllChem
    AllChem.UFFOptimizeMolecule(rdkit_mol, maxIters)
    ff = AllChem.UFFGetMoleculeForceField(rdkit_mol)
    ff.Minimize(maxIts=maxIters)
    E = ff.CalcEnergy()
    return E


def add_namefile(original_wf, use_slug=True):
    for idx, fw in enumerate(original_wf.fws):
        fname = "FW--{}".format(fw.name)
        if use_slug:
            fname = get_slug(fname)

        t = FileWriteTask(files_to_write=[{"filename": fname, "contents": ""}])
        original_wf.fws[idx].tasks.insert(0, t)
    return original_wf


def get_list_fireworks_and_tasks(workflow):
    # TODO: put a constraint on what fireworks to return
    list_fireworks_and_tasks = []
    for i_firework, firework in enumerate(workflow.fws):
        for i_task, task in enumerate(firework.tasks):
            list_fireworks_and_tasks.append((i_firework, i_task))
    return list_fireworks_and_tasks


def modify_queue_parameters(workflow, ntasks_per_node=None, walltime=None,
                            queue=None, pre_rocket=None, other_parameters=None):
    queue_parameters = {}
    if ntasks_per_node:
        queue_parameters.update({"ntasks_per_node": ntasks_per_node})
    if walltime:
        queue_parameters.update({"walltime": walltime})
    if queue:
        queue_parameters.update({"queue": queue})
    if pre_rocket:
        queue_parameters.update({"pre_rocket": pre_rocket})
    if other_parameters:
        queue_parameters.update(other_parameters)

    list_fireworks_and_tasks = get_list_fireworks_and_tasks(workflow)
    for i_firework, i_task in list_fireworks_and_tasks:
        workflow.fws[i_firework].spec.update({"_queueadapter":
                                                  queue_parameters})
    return workflow


def control_worker(workflow, fworker=None, category=None):
    list_fireworks_and_tasks = get_list_fireworks_and_tasks(workflow)
    for i_firework, i_task in list_fireworks_and_tasks:
        if fworker:
            workflow.fws[i_firework].spec["_fworker"] = fworker
        if category:
            workflow.fws[i_firework].spec["_category"] = category
    return workflow


def get_db(input_db=None):
    from infrastructure.gaussian.database import GaussianCalcDb
    if not input_db:
        input_db = f"{CONFIG_FILE_DIR}/db.json"
        if not os.path.isfile(input_db):
            raise FileNotFoundError(
                "Please provide the database configurations")
    if isinstance(input_db, dict):
        db = GaussianCalcDb(**input_db)
    else:
        db = GaussianCalcDb.from_db_file(input_db)

    return db


def label_atoms(mol):
    # supports all atom types and molecules as large as 999 atoms; does not
    # support clusters
    a = BabelMolAdaptor(mol)
    pm = pb.Molecule(a.openbabel_mol)
    mol_smiles = pm.write("smi").strip()
    mol_smiles_copy = mol_smiles.lower()
    counter = 0
    count_1 = ""
    count_2 = ""
    count_3 = ""
    smiles = mol_smiles.lower()
    atoms = [str(i).lower() for i in mol.species]
    sorted_atoms = sorted(atoms, key=lambda x: len(x), reverse=True)
    index_atom_map = {}
    h_index = [i for i, j in enumerate(mol_smiles_copy) if j == "h"]
    for atom in sorted_atoms:
        if atom == "h":
            smiles = smiles.replace(atom, "!", 1)
            continue
        index = smiles.find(atom)
        if index != -1:
            smiles = smiles.replace(atom, "!", 1)
            index_atom_map[index] = atom
    existing_atoms = [index_atom_map[i] for i in sorted(index_atom_map)]
    for ch in smiles:
        if ch == "!":
            flag = 0
            if len(count_1) in h_index:
                atom = "h"
                flag = 1
            else:
                atom = atoms[counter]
                while atom not in existing_atoms:
                    counter += 1
                    atom = atoms[counter]
            if atom.lower() == "h":
                i = 0
            else:
                i = counter
            if i < 10:
                count_1 += f"{i: >{len(atom)}}"
                count_2 += " " * len(atom)
                count_3 += " " * len(atom)
            elif i < 100:
                count_1 += f"{i // 10: >{len(atom)}}"
                count_2 += f"{i % 10: >{len(atom)}}"
                count_3 += " " * len(atom)
            else:
                count_1 += f"{i // 10 // 10: >{len(atom)}}"
                count_2 += f"{i % 100 // 10: >{len(atom)}}"
                count_3 += f"{i % 10: >{len(atom)}}"
            if flag == 0:
                counter += 1
        else:
            count_1 += " "
            count_2 += " "
            count_3 += " "
    print(f"{mol_smiles}\n{count_1}\n{count_2}\n{count_3}")


def _update_gaussian_inputs(opt_gaussian_inputs, other_gaussian_inputs,
                            main_keyword):
    gaussian_inputs = {**opt_gaussian_inputs, **other_gaussian_inputs}
    if list(main_keyword.keys())[0].lower() not in \
            [i.lower() for i in gaussian_inputs["route_parameters"]]:
        gaussian_inputs["route_parameters"].update(main_keyword)
    for i in gaussian_inputs["route_parameters"]:
        if i.lower() == "opt":
            del gaussian_inputs["route_parameters"][i]
            break
    return gaussian_inputs


def _get_gaussian_inputs(gaussian_inputs, supported_jobs=None):
    # gaussian_inputs is a dict of dicts: {"opt": {}, "freq": {}, "nmr": {},
    # "esp": {}, "sp": {}}; this function is meant to be used in workflows in
    # which multiple Gaussian jobs are performed and the jobs share similar
    # Gaussian keywords; used to handle situations in which the user is not
    # explicitly defining every single job input dictionary
    supported_jobs = supported_jobs or {}
    supported_jobs = {**{"freq": {"Freq": None}, "nmr": {"NMR": "GIAO"},
                         "esp": {"pop": "MK", "iop(6/50=1)": None},
                         "sp": {"SP": None}},
                      **{k.lower(): v for k, v in supported_jobs.items()}}

    gaussian_inputs = {k.lower(): v if v is not None else {} for k, v in
                       gaussian_inputs.items()}

    if "opt" not in gaussian_inputs:
        gaussian_inputs["opt"] = {}
    gaussian_inputs["opt"] = {**STANDARD_OPT_GUASSIAN_INPUT,
                              **gaussian_inputs["opt"]}
    if "opt" not in [i.lower() for i in
                     gaussian_inputs["opt"]["route_parameters"]]:
        gaussian_inputs["opt"]["route_parameters"].update({"Opt": None})

    for job in gaussian_inputs:
        if job in supported_jobs and job != "opt":
            gaussian_inputs[job] = \
                _update_gaussian_inputs(deepcopy(gaussian_inputs["opt"]),
                                        gaussian_inputs[job],
                                        supported_jobs[job])
        elif job == "opt":
            pass
        else:
            logger.error("keyword for {} is not known. Please add keyword to "
                         "the supported_jobs dict.".format(job))
    return gaussian_inputs


def _check_solvent_inputs(gaussian_inputs):
    # gaussian_inputs is a list of dicts
    route_params = {}
    for key, value in gaussian_inputs.items():
        if value:
            route_params.update(value.get("route_parameters", {}))
    assert "scrf" not in [i.lower() for i in route_params], \
        "solvent inputs should be provided as separate inputs via " \
        "solvent_gaussian_inputs and solvent_properties"


def _add_solvent_inputs(gaussian_inputs, solvent_gaussian_inputs,
                        solvent_properties=None):
    if "generic" in solvent_gaussian_inputs.lower() \
            and not solvent_properties:
        raise Exception(
            "A generic solvent is provided as an input without "
            "specifying its parameters.")
    for key, value in gaussian_inputs.items():
        if "route_parameters" not in value:
            gaussian_inputs[key]["route_parameters"] = {}
        gaussian_inputs[key]["route_parameters"]["SCRF"] = \
            solvent_gaussian_inputs
        if solvent_properties:
            if "input_parameters" not in gaussian_inputs[key]:
                gaussian_inputs[key]["input_parameters"] = {}
            gaussian_inputs[key]["input_parameters"].update(solvent_properties)
    return gaussian_inputs


def handle_gaussian_inputs(gaussian_inputs, solvent_gaussian_inputs=None,
                           solvent_properties=None):
    gaussian_inputs = _get_gaussian_inputs(gaussian_inputs)
    _check_solvent_inputs(gaussian_inputs)
    if solvent_gaussian_inputs:
        gaussian_inputs = _add_solvent_inputs(gaussian_inputs,
                                              solvent_gaussian_inputs,
                                              solvent_properties)
    return gaussian_inputs


def add_solvent_to_prop_dict(prop_dict, solvent_gaussian_inputs,
                             solvent_properties):
    if not solvent_gaussian_inputs:
        solvent = "water"
        solvent_model = "pcm"
    else:
        solvent_inputs = [
            i.lower() for i in solvent_gaussian_inputs.strip("()").split(",")]
        solvent = [string.split("=")[1] for string in solvent_inputs
                   if "solvent" in string] or ["water"]
        solvent_model = \
            list(filter(lambda x: x in {i for i in solvent_inputs},
                        SCRF_MODELS)) or ["pcm"]
    prop_dict["solvent"] = "".join(solvent)
    prop_dict["solvent_model"] = "".join(solvent_model)
    prop_dict["solvent_properties"] = solvent_properties
    return prop_dict


def _modify_gout(gout):
    gout["input"]["charge"] = gout["charge"]
    gout["input"]["spin_multiplicity"] = gout["spin_multiplicity"]
    del_keys_out = ("nsites", "unit_cell_formula",
                    "reduced_cell_formula", "pretty_formula",
                    "elements", "nelements", "charge",
                    "spin_multiplicity")
    [gout.pop(k, None) for k in del_keys_out]
    return gout


def _create_gin(gout, working_dir, input_file):
    if input_file:
        if not os.path.isabs(input_file):
            input_path = os.path.join(working_dir, input_file)
        else:
            input_path = input_file
        gin = GaussianInput.from_file(input_path).as_dict()
        gin["nbasisfunctions"] = gout["input"]["nbasisfunctions"]
        gin["pcm_parameters"] = gout["input"]["pcm_parameters"]
        return gin
    else:
        gin = gout["input"]
        gin["input_parameters"] = None
        gin["@class"] = "GaussianInput"
        gin["@module"] = "pymatgen.io.gaussian"
        logger.info("input parameters at the end of the Gaussian input "
                    "section will not be saved to the database due to "
                    "a missing input file")
        return gin


def _job_types(gin):
    return sorted(list(filter(lambda x: x in {k.lower(): v for k, v in
                                       gin["route_parameters"].items()},
                       JOB_TYPES)))


def _cleanup_gout(gout, working_dir, input_file):
    gout = _modify_gout(gout)
    gin = _create_gin(gout, working_dir, input_file)
    del gout["input"]
    job_types = _job_types(gin)
    mol = Molecule.from_dict(gout["output"]["molecule"])
    # TODO: check if other solvation models are supported
    gout_dict = {"input": gin, "output": gout,
                 "functional": gin["functional"],
                 "basis": gin["basis_set"],
                 "phase": "solution" if gout["is_pcm"] else "gas",
                 "type": ";".join(job_types),
                 **get_chem_schema(mol)}
    gout_dict = {i: j for i, j in gout_dict.items() if i not in
                 ["sites", "@module", "@class", "charge",
                  "spin_multiplicity"]}
    return gout_dict


def recursive_signature_remove(d):
    if isinstance(d, dict):
        return {i: recursive_signature_remove(j)
                for i, j in d.items() if not i.startswith("@")}
    else:
        return d


def recursive_relative_to_absolute_path(operand, working_dir):
    if isinstance(operand, str):
        if os.path.isabs(operand):
            return operand
        elif os.path.exists(operand):
            return os.path.join(os.getcwd(), operand)
        else:
            full_path = os.path.join(working_dir, operand)
            if os.path.exists(full_path):
                return full_path
            else:
                return operand
    elif isinstance(operand, dict):
        return {i: recursive_relative_to_absolute_path(j, working_dir)
                for i, j in operand.items()}
    elif isinstance(operand, list):
        return [recursive_relative_to_absolute_path(i, working_dir)
                for i in operand]
    else:
        return operand
