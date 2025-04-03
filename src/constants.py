from ast import literal_eval as d_from_s


# Some constants
NAME: str = "KC"
UI: str = "ui/index.html"
ICON: str = "ui/kemono.png"
NOTIFICATION_ICON: str = "./src/ui/kemono.png"
DATABASE: str = "data/kc.db"
TIMER: int = 1800  # 1800 seconds => 30 minutes


# Event enum
class Event:
    type: str
    event: str

    def __init__(self, t: str, e=None) -> None:
        self.type = t
        self.event = e


# Creator class
class Creator:
    service: str
    id: str
    name: str
    searching: bool
    latest: dict

    def __init__(self, s: str, i: str, n: str, t_or_f: int, l: str) -> None:
        self.service = s
        self.id = i
        self.name = n
        self.searching = bool(t_or_f)
        self.latest = d_from_s(l)

    def string(self) -> str:
        return f"{self.service}-{self.id}"
