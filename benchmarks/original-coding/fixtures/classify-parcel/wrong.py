def parcel_band(mass_g, zone):
    # Behaviour-preserving, but keeps the original deeply nested ladder that the
    # refactor was supposed to remove -> violates the depth constraint.
    if zone == "inner":
        if mass_g <= 0:
            raise ValueError("mass must be positive")
        else:
            if mass_g <= 100:
                return "I-S"
            else:
                if mass_g <= 1000:
                    return "I-M"
                else:
                    return "I-L"
    elif zone == "outer":
        if mass_g <= 0:
            raise ValueError("mass must be positive")
        else:
            if mass_g <= 100:
                return "O-S"
            else:
                if mass_g <= 1000:
                    return "O-M"
                else:
                    return "O-L"
    else:
        raise ValueError("unknown zone")
