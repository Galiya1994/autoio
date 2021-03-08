""" Runner
"""


def direct(script_str, run_dir, input_str, pot_str):
    """ Lazy runner polyrate
    """
    
    aux_dct = {'input.fu40': pot_str}
    input_name = 'input.dat'
    output_name = 'poly.fu6'
    output_str = from_input_string(
        script_str, run_dir, input_str,
        aux_dct=aux_dct,
        output_name=output_name)

    return input_str, output_str