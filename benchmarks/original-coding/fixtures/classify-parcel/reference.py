def parcel_band(mass_g, zone):
    if zone not in ("inner", "outer"):
        raise ValueError("unknown zone")
    if mass_g <= 0:
        raise ValueError("mass must be positive")
    prefix = "I" if zone == "inner" else "O"
    size = "S" if mass_g <= 100 else "M" if mass_g <= 1000 else "L"
    return f"{prefix}-{size}"
