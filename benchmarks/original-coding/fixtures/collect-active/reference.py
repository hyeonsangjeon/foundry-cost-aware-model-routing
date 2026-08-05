def collect_active(records):
    return [record["id"] for record in records if record["state"] == "on"]
