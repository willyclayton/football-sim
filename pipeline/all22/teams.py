"""Team names and uniform colors. No logos or wordmarks: the app draws
generic uniforms in team colors."""

from __future__ import annotations

TEAMS = {
    "ARI": ("Arizona Cardinals", "#97233F", "#FFB612"),
    "ATL": ("Atlanta Falcons", "#A71930", "#000000"),
    "BAL": ("Baltimore Ravens", "#241773", "#9E7C0C"),
    "BUF": ("Buffalo Bills", "#00338D", "#C60C30"),
    "CAR": ("Carolina Panthers", "#0085CA", "#101820"),
    "CHI": ("Chicago Bears", "#0B162A", "#C83803"),
    "CIN": ("Cincinnati Bengals", "#FB4F14", "#000000"),
    "CLE": ("Cleveland Browns", "#311D00", "#FF3C00"),
    "DAL": ("Dallas Cowboys", "#003594", "#869397"),
    "DEN": ("Denver Broncos", "#FB4F14", "#002244"),
    "DET": ("Detroit Lions", "#0076B6", "#B0B7BC"),
    "GB": ("Green Bay Packers", "#203731", "#FFB612"),
    "HOU": ("Houston Texans", "#03202F", "#A71930"),
    "IND": ("Indianapolis Colts", "#002C5F", "#A2AAAD"),
    "JAX": ("Jacksonville Jaguars", "#006778", "#D7A22A"),
    "KC": ("Kansas City Chiefs", "#E31837", "#FFB81C"),
    "LAC": ("Los Angeles Chargers", "#0080C6", "#FFC20E"),
    "LA": ("Los Angeles Rams", "#003594", "#FFA300"),
    "LV": ("Las Vegas Raiders", "#000000", "#A5ACAF"),
    "MIA": ("Miami Dolphins", "#008E97", "#FC4C02"),
    "MIN": ("Minnesota Vikings", "#4F2683", "#FFC62F"),
    "NE": ("New England Patriots", "#002244", "#C60C30"),
    "NO": ("New Orleans Saints", "#D3BC8D", "#101820"),
    "NYG": ("New York Giants", "#0B2265", "#A71930"),
    "NYJ": ("New York Jets", "#125740", "#000000"),
    "PHI": ("Philadelphia Eagles", "#004C54", "#A5ACAF"),
    "PIT": ("Pittsburgh Steelers", "#FFB612", "#101820"),
    "SF": ("San Francisco 49ers", "#AA0000", "#B3995D"),
    "SEA": ("Seattle Seahawks", "#002244", "#69BE28"),
    "TB": ("Tampa Bay Buccaneers", "#D50A0A", "#34302B"),
    "TEN": ("Tennessee Titans", "#0C2340", "#4B92DB"),
    "WAS": ("Washington", "#5A1414", "#FFB612"),
    # Older codes that appear in 2017-2020 data.
    "OAK": ("Oakland Raiders", "#000000", "#A5ACAF"),
    "SD": ("San Diego Chargers", "#002A5E", "#FFC20E"),
    "STL": ("St. Louis Rams", "#002244", "#B3995D"),
}
ALIASES = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def team_info(abbr: str, display_name: str | None = None) -> dict:
    """Name and colors for a team code. Unknown codes get neutral colors."""
    code = ALIASES.get(abbr, abbr)
    name, primary, secondary = TEAMS.get(code, (abbr, "#555555", "#BBBBBB"))
    if display_name:
        name = display_name
    text = "#000000" if _luminance(primary) > 0.35 else "#FFFFFF"
    return {
        "abbr": abbr,
        "name": name,
        "primaryColor": primary,
        "secondaryColor": secondary,
        "textColor": text,
    }
