import threading, webview, queue
from time import sleep
from ast import literal_eval as d_from_s
from notifypy import Notify
import sqlite3 as sql
from api import *
from collections.abc import Callable


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


# Handling the database
# Set up the database
def set_up_database(con: sql.Connection) -> None:
    with con:
        if (
            con.execute(
                "SELECT name FROM sqlite_master WHERE name='creators'"
            ).fetchone()
            is None
        ):
            con.execute(
                "CREATE TABLE creators(service VARCHAR, id VARCHAR, name VARCHAR, searching BIT, latest VARCHAR)"
            )
            con.execute("CREATE TABLE timer(name VARCHAR, seconds INTEGER)")
            con.execute(
                "INSERT INTO timer VALUES(?, ?)",
                (
                    "timer",
                    TIMER,
                ),
            )


# Get database creators
def get_database_creators(con: sql.Connection) -> list[Creator]:
    with con:
        return [
            Creator(s, i, n, t_or_f, l)
            for s, i, n, t_or_f, l in con.execute(
                "SELECT service, id, name, searching, latest FROM creators"
            )
        ]


# Get one database creator
def get_one_creator(con: sql.Connection, service: str, creator_id: str) -> Creator:
    with con:
        return [
            Creator(s, i, n, t_or_f, l)
            for s, i, n, t_or_f, l in con.execute(
                "SELECT service, id, name, searching, latest FROM creators WHERE (service = ? AND id = ?)",
                (
                    service,
                    creator_id,
                ),
            )
        ][0]


# Insert creator into database
def insert_creator(con: sql.Connection, creator: Creator) -> None:
    with con:
        con.execute(
            "INSERT INTO creators VALUES(?, ?, ?, ?, ?)",
            (
                creator.service,
                creator.id,
                creator.name,
                creator.searching,
                str(creator.latest),
            ),
        )


# Get latest post on record
def get_latest_on_record(con: sql.Connection, creator: Creator) -> dict:
    return d_from_s(
        con.execute(
            "SELECT latest FROM creators WHERE (id = ? AND service = ?)",
            (
                creator.id,
                creator.service,
            ),
        )[0]
    )


# Set latest
def set_latest(con: sql.Connection, creator: Creator) -> None:
    con.execute(
        "UPDATE creators SET latest = ? WHERE (id = ? AND service = ?)",
        (
            str(creator.latest),
            creator.id,
            creator.service,
        ),
    )


# Get timer
def get_timer(con: sql.Connection) -> int:
    with con:
        return con.execute("SELECT seconds FROM timer WHERE name = 'timer'").fetchone()[
            0
        ]


# Set timer
def set_timer(con: sql.Connection, time: int) -> None:
    with con:
        con.execute("UPDATE timer SET seconds = ?", (time,))


# Toggle searching in database
def toggle_searching(con: sql.Connection, creator: Creator) -> None:
    with con:
        match con.execute(
            "SELECT searching FROM creators WHERE (id = ? AND service = ?)",
            (
                creator.id,
                creator.service,
            ),
        ).fetchone()[0]:
            case 0:
                con.execute(
                    "UPDATE creators SET searching = ? WHERE (id = ? AND service = ?)",
                    (
                        True,
                        creator.id,
                        creator.service,
                    ),
                )
            case 1:
                con.execute(
                    "UPDATE creators SET searching = ? WHERE (id = ? AND service = ?)",
                    (
                        False,
                        creator.id,
                        creator.service,
                    ),
                )


# Get a Creator object from a profile dict
def creator_from_dict(creator_dict: dict, latest: dict) -> Creator:
    return Creator(
        creator_dict["service"],
        creator_dict["id"],
        creator_dict["name"],
        0,
        str(latest),
    )


# Lookup logic
def lookup_handler(
    creator: Creator,
    kill_switch: queue.SimpleQueue,
    notification: Notify,
) -> None:
    con = sql.connect(DATABASE)
    while True:
        try:
            kill_switch.get(block=False)
            break
        except queue.Empty:
            pass

        latest = get_all_creator_posts(kemono, creator.service, creator.id)[0]
        if creator.latest == latest:
            pass
        else:
            creator.latest = latest
            with con:
                set_latest(con, creator)
            notification.title = f"New post from {creator.name}!"
            notification.message = latest["title"]
            notification.send()
        sleep(get_timer(con))


# Broker handler
def broker_handler(
    broker: queue.SimpleQueue,
    notification: Notify,
) -> None:
    active_threads = {}
    con = sql.connect(DATABASE)

    while True:
        creator = broker.get()
        service, creator_id = creator.split("-")

        creator_dict = creator_from_dict(
            get_creator_profile(kemono, service, creator_id), {}
        )

        if creator_dict.string() not in [
            creator.string() for creator in get_database_creators(con)
        ]:
            insert_creator(con, creator_dict)

        if creator in active_threads.keys():
            active_threads.pop(creator)[1].put(True)
        else:
            creator_obj: Creator = get_one_creator(con, service, creator_id)
            kill_switch = queue.SimpleQueue()
            active_threads[creator] = (
                threading.Thread(
                    daemon=True,
                    target=lookup_handler,
                    args=[creator_obj, kill_switch, notification],
                ),
                kill_switch,
            )
            active_threads[creator][0].start()

        toggle_searching(con, creator_obj)


# Handler for window closed event
def closed_handler(root: queue.SimpleQueue) -> Callable:
    def logic() -> None:
        root.put(Event(t="CLOSED"))

    return logic


# Handler for text input
def input_handler(root: queue.SimpleQueue, debounce: queue.SimpleQueue) -> Callable:
    def logic(e: dict) -> None:
        t = threading.Timer(
            0.2,
            lambda event: root.put(
                Event("SEARCH", event.get("target", {}).get("value", ""))
            ),
            args=[e],
        )

        try:
            debounce.get(timeout=0.1).cancel()
            t.start()
            debounce.put(t)

        except queue.Empty:
            t.start()
            debounce.put(t)

    return logic


# Favourites button event
def fav_handler(root: queue.SimpleQueue) -> Callable:
    def logic(e: dict) -> None:
        root.put(Event("FAVOURITES"))

    return logic


# Click toggle handler
def toggle_handler(root: queue.SimpleQueue) -> Callable:
    def logic(e: dict) -> None:
        if e["pointerId"] != 1:
            service, creator_id = e["currentTarget"]["id"].split("-")
            root.put(Event("TOGGLE", e=(service, creator_id)))

    return logic


# Settings handler
def settings_handler(root: queue.SimpleQueue) -> Callable:
    def logic(e: dict) -> None:
        root.put(Event("SETTINGS", e=e["currentTarget"]["id"]))

    return logic


# Root handler
def root_handler(window: webview.window.Window) -> int:
    # Relevant data
    clist = [
        Creator(creator["service"], creator["id"], creator["name"], 0, "{}")
        for creator in sorted(  # Sorted by most favourites, as per Kemono default
            get_creators_list(kemono),
            key=lambda creator: creator["favorited"],
            reverse=True,
        )
    ]
    notification = Notify()  # Notification object
    notification.icon = NOTIFICATION_ICON
    con = sql.connect(DATABASE)  # Database connection
    ctemplate = window.dom.get_element("#ctemplate")  # Creator section template
    favourites = False  # Favourites mode toggle
    settings = False  # Settings mode toggle

    # Thread queues
    root = queue.SimpleQueue()  # Main
    broker = queue.SimpleQueue()  # Spawn and kill lookup threads
    debounce = queue.SimpleQueue()  # Used for debouncing input

    # Input elements
    input_field = window.dom.get_element("#input_field")  # Primary input field
    fav_button = window.dom.get_element("#fav_button")  # Switch favourites button
    settings_button = window.dom.get_element("#settings_button")  # Open settings menu

    # Thread handlers
    threading.Thread(  # Broker handler thread
        daemon=True,
        target=broker_handler,
        args=[
            broker,
            notification,
        ],
    ).start()

    # Input handlers
    window.events.closed += closed_handler(root)
    input_field.events.input += input_handler(root, debounce)
    fav_button.events.click += fav_handler(root)
    settings_button.events.click += settings_handler(root)

    # Generate UI function
    def generate_ui(search: str) -> None:
        [
            c.remove()
            for c in ctemplate.parent.children
            if c.attributes["id"] != ctemplate.attributes["id"]
        ]

        database_creators = get_database_creators(con)

        if favourites:
            csource = sorted(
                [creator for creator in database_creators if creator.searching == True],
                key=lambda creator: creator.name,
            )
        else:
            csource = clist

        for c in [
            creator for creator in csource if search.lower() in creator.name.lower()
        ][
            :50
        ]:  # 50 is the Kemono page size
            t = ctemplate.copy()
            del t.attributes["hidden"]
            t.children[0].attributes[
                "href"
            ] = f"https://kemono.su/{c.service}/user/{c.id}"
            t.children[0].children[0].attributes[
                "src"
            ] = f"{kemono_icon_link}/{c.service}/{c.id}"
            t.children[1].attributes["id"] = c.string()
            if not t.children[1]._event_handlers:
                t.children[1].events.click += toggle_handler(
                    root
                )  # Uses the toggle_handler
            for creator in database_creators:
                if creator.searching is True and creator.string() == c.string():
                    t.children[1].children[0].attributes["checked"] = True

            t.children[0].children[1].children[0].text = c.name
            t.children[0].children[1].children[1].text = c.service

    # Generate settings
    def generate_settings(settings: bool):
        if settings:
            for t in settings_button.parent.children[1:]:
                del t.attributes["hidden"]
        else:
            for t in settings_button.parent.children[1:]:
                t.attributes["hidden"] = True

    # Setup actions
    set_up_database(con)
    [
        (broker.put(f"{creator.service}-{creator.id}"), toggle_searching(con, creator))
        for creator in get_database_creators(con)
        if creator.searching is True
    ]
    for t in settings_button.parent.children[1:]:
        t.events.click += settings_handler(root)
    generate_ui("")

    # Root handler loop
    while True:
        match root.get():
            case closed if closed.type == "CLOSED":
                exit()
                return 0
            case search if search.type == "SEARCH":
                generate_ui(search.event)
            case fav if fav.type == "FAVOURITES":
                favourites = not favourites
                input_field.value = ""
                generate_ui("")
            case toggle if toggle.type == "TOGGLE":
                service, creator_id = toggle.event
                broker.put(f"{service}-{creator_id}")
            case toggle if toggle.type == "SETTINGS":
                settings = not settings
                generate_settings(settings)
                if toggle.event is not None:
                    match toggle.event:
                        case "s30":
                            set_timer(con, 30)
                        case "m30":
                            set_timer(con, 1800)
                        case "h1":
                            set_timer(con, 3600)


# Setup and initialization
if __name__ == "__main__":
    window = webview.create_window(
        "KC",
        UI,
        text_select=True,
        resizable=False,
        width=400,
    )
    webview.start(root_handler, args=[window], gui="qt", icon=ICON)
