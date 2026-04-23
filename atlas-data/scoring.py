def news_risk_level(events):
    """Devuelve (nivel, penalizacion_pts) basado en el evento mas proximo."""
    if not events:
        return ("LOW", 0)
    upcoming = [e for e in events if 0 <= e["minutes_until"] <= 60]
    if not upcoming:
        return ("LOW", 0)

    nearest = upcoming[0]
    impact = (nearest.get("impact") or "").lower()
    minutes = nearest["minutes_until"]

    if impact == "high" and minutes <= 30:
        return ("HIGH", 25)
    if impact == "high" and minutes <= 60:
        return ("HIGH", 12)
    if impact == "medium" and minutes <= 30:
        return ("MEDIUM", 8)
    if impact == "medium" and minutes <= 60:
        return ("MEDIUM", 4)
    return ("LOW", 0)
