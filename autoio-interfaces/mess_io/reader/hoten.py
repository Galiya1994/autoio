"""
    Read the HotEnergies distribution and store it
    Reads mess inp and log files
"""
import sys
import numpy as np
import pandas as pd
import autoparse.find as apf
from mess_io.reader._pes import pes
from mess_io.reader._label import name_label_dct
from automol.util.dict_ import invert


def get_hot_species(input_str):
    """ Reads the HotSpecies from the MESS input file string
        that were used in the master-equation calculation.
        returns dictionary with associated energies
        :param input_str: string of lines of MESS input file
        :type input_str: str
        :return hotspecies: dictionary of hotspecies energies
        :rtype: dct{hotspecies: en}
    """

    # Get the MESS input lines
    energy_dct, _, _, _ = pes(input_str)
    mess_lines = input_str.splitlines()
    hotsp_i = apf.where_in('HotEnergies', mess_lines)[0]
    num_hotsp = int(mess_lines[hotsp_i].strip().split()[1])
    #hotspecies = [None]*num_hotsp
    hotspecies_en = {}
    for line in mess_lines[hotsp_i+1:hotsp_i+1+num_hotsp]:
        hotname = line.strip().split()[0]
        hotspecies_en[hotname] = energy_dct[hotname]

    return hotspecies_en


def extract_hot_branching(hot_log_str, hotspecies_en, species_lst,
                          sp_labels='inp'):
    """ Extract hot branching fractions for a single species
        :param hot_log_str: string of mess log file
        :type hot_log_str: str
        :param hotspecies_en: dct of hotspecies and corresponding energy
        :type hotspecies_en: dct{hotspecies: en}
        :param species_lst: list of all species on the PES
        :type species_lst: list
        :param sp_labels: type of species labels: 'inp' is how you find them
                in mess input, 'out' is how they are labeled in the output
        :type sp_labels: str
        :return hoten_dct: hot branching fractions for hotspecies
        :rtype hoten_dct: dct{hotspecies: df[P][T]:df[allspecies][energies]}
    """
    # get label dictionary
    lbl_dct = name_label_dct(hot_log_str)
    inv_lbl_dct = invert(lbl_dct)

    lines = hot_log_str.splitlines()
    # for each species: dataframe of dataframes BF[Ti][pi]
    # each of them has BF[energy][species]
    # preallocations
    hotspecies_lst = list(hotspecies_en.keys())

    # 1. extract P, T and preallocate dictionary
    pt_i_array = apf.where_in(['Pressure', 'Temperature'], lines)
    pt_list = []
    for pt_i in pt_i_array:
        pt_list.append([
            float(var)
            for var in lines[pt_i].strip().split()[2:7:4]])
    pressures = list(set([pt[0] for pt in pt_list]))
    temps = list(set([pt[1] for pt in pt_list]))
    pressures.sort(), temps.sort()

    hoten_dct = {s: pd.DataFrame(index=temps, columns=pressures)
                 for s in hotspecies_lst}

    # variables limiting the blocks
    hot_i_array = apf.where_in(['Hot distribution branching ratios'], lines)
    end_hot_i_array = apf.where_in(
        ['prompt', 'isomerization', 'dissociation'], lines)

    # 2. find Hot distribution branching ratios:
    for i, hot_i in enumerate(hot_i_array):

        # extract block, PT, and species for which BF is assigned
        lines_block = lines[hot_i+2:end_hot_i_array[i]]
        _press, _temp = [
            float(var)
            for var in lines[pt_i_array[i]].strip().split()[2:7:4]]

        species_bf_i_messout = lines[hot_i+1].strip().split()[3:]

        # for each hotspecies: read BFs
        # rescale energy by the hotspecies energy on the PES!!
        # ref 0 energy is the ref for the PES, even for the hotspecies

        for hotspecies in hotspecies_lst:
            hot_e_lvl, branch_ratio = [], []
            ref_en = hotspecies_en[hotspecies]

            if sp_labels == 'inp':
                hotspecies_messout = inv_lbl_dct[hotspecies]
                species_bf_i = [lbl_dct[sp_i] for sp_i in species_bf_i_messout]
            elif sp_labels == 'out':
                hotspecies_messout = hotspecies
                species_bf_i = species_bf_i_messout
            else:
                print('*Error: sp_labels must be "inp" (as in mess input) \
                    or "out" (as in mess output)')
                sys.exit()

            sp_i = apf.where_in(hotspecies_messout, species_bf_i_messout)

            for line in lines_block:
                line = line.strip()
                if line.startswith(hotspecies_messout):
                    hot_e = float(line.split()[1]) - ref_en
                    # pick only values above 0
                    if hot_e not in hot_e_lvl and hot_e > 0:
                        branch_ratio_arr = np.array(
                            list(line.split()[2:]), dtype=float)

                        # check that value of reactant branching is between 0 and 1
                        # if any bf > 1: skip the line
                        if sp_i.size > 0:
                            if any(branch_ratio_arr > 1):
                                continue
                            elif branch_ratio_arr[sp_i] <= 1e-10:
                                continue

                        # remove negative values or values >1
                        _arr = [abs(x*int(1e-8 < x <= 1))
                                for x in branch_ratio_arr]
                        br_filter = np.array(_arr, dtype=float)

                        # if all invalid: do not save
                        if all(br_filter == 0):
                            continue
                        br_renorm = br_filter/np.sum(br_filter)
                        # append values
                        branch_ratio.append(br_renorm)
                        hot_e_lvl.append(hot_e)

            hot_e_lvl = np.array(hot_e_lvl)
            branch_ratio = np.array(branch_ratio)

            # 3. allocate in the dataframe

            bf_hotspecies = pd.DataFrame(
                0, index=hot_e_lvl, columns=species_lst)
            bf_hotspecies[species_bf_i] = branch_ratio
            hoten_dct[hotspecies][_press][_temp] = bf_hotspecies

    return hoten_dct


def extract_fne(log_str, sp_labels='inp'):
    """ Extract fne from log file
        :param log_str: string of mess log file
        :type log_str: str
        :param sp_labels: type of species labels: 'inp' is how you find them
                in mess input, 'out' is how they are labeled in the output
        :type sp_labels: str
        :return dct_bf_tp_df: branching fractions at T,P
            for each product for the selected species
        :rtype: dct{sp: dataframe of series df[P][T]:series[species]},
                dct{str: dataframe(series(float))}
                made so that you can extract bf_tp_df from here to
                use it with bf_tp_df_todct
    """
    # get label dictionary and count N of wells
    lbl_dct = name_label_dct(log_str)
    n_wells = sum(np.array(['W' in key for key in lbl_dct.keys()], dtype=int))
    if sp_labels == 'inp':
        species = list(lbl_dct.values())
    elif sp_labels == 'out':
        species = list(lbl_dct.keys())
    else:
        print('*Error: sp_labels must be "inp" (as in mess input) \
            or "out" (as in mess output)')
        sys.exit()

    wells = species[:n_wells]

    lines = log_str.splitlines()

    # 1. extract P, T and preallocate dictionary
    pt_i_array = apf.where_in(['Pressure', 'Temperature'], lines)
    pt_list = []
    for pt_i in pt_i_array:
        pt_list.append([
            float(var)
            for var in lines[pt_i].strip().split()[2:7:4]])
    pressures = list(set([pt[0] for pt in pt_list]))
    temps = list(set([pt[1] for pt in pt_list]))
    pressures.sort(), temps.sort()

    # variables limiting the blocks
    fne_i_array = apf.where_in(
        ['prompt', 'isomerization', 'dissociation'], lines) + 2

    dct_bf_tp_df = dict.fromkeys(wells)

    # 2. find prompt isomerization/dissociation branching ratios:
    for i, line_in in enumerate(fne_i_array):
        line_fin = line_in + n_wells
        # extract block and PT
        lines_block = lines[line_in:line_fin]
        _press, _temp = pt_list[i]

        # for each well: read BFs
        for j, well in enumerate(wells):
            # generate df - cannot do it above otherwise overwrites
            if dct_bf_tp_df[well] is None:
                dct_bf_tp_df[well] = pd.DataFrame(
                    index=temps, columns=pressures, dtype=object)

            # read BFs
            bf_raw = lines_block[j].strip().split()[1:]
            # if pdiss=1, well values do not appear

            if len(bf_raw) == len(species) + 1:
                bf_fne = np.array(bf_raw[:n_wells] +
                                  bf_raw[n_wells+1:], dtype=float)

            elif len(bf_raw) == len(species) - n_wells + 1:
                bf_fne = np.array([0]*len(wells) +
                                  bf_raw[1:], dtype=float)
            else:
                print('I had not forseen this :C check mess log and ask Yuri')
                sys.exit()

            # remove negative values and renormalize
            bf_fne = abs(bf_fne * np.array(bf_fne > 0, dtype=int))
            bf_fne_renorm = bf_fne/np.sum(bf_fne)

            # put in dct
            dct_bf_tp_df[well][_press][_temp] = pd.Series(
                bf_fne_renorm, index=species, dtype=float)

    return dct_bf_tp_df
