def seconds_to_ms(seconds: float) -> int:
    """
        converts seconds to whole milliseconds.
    """

    return int(round(seconds * 1000))


def build_cue_update(cartucho_id: int, start_ms: int, end_ms: int, content_type: int = 3) -> str:
    """
        returns the UPDATE query that sets the vocals start / end (TiempoEntrada / TiempoSalida, in ms) of a CARTUCHOS row.
    """

    # int() keeps the query free of anything that is not a number
    return (f"UPDATE CARTUCHOS SET TiempoEntrada = {int(start_ms)}, TiempoSalida = {int(end_ms)} "
            f"WHERE CartuchoId = {int(cartucho_id)} AND TipoContenido = {int(content_type)};")


if __name__ == "__main__":
    print(build_cue_update(39, seconds_to_ms(10.22), seconds_to_ms(194.068)))
