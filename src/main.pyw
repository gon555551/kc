import threading, webview, queue
from time import sleep
import sqlite3 as sql
from api import *
from constants import *
from mem import *
from collections.abc import Callable
import os
import pystray
from PIL import Image
import chime


# Scroll handler
class JSAPI:
    def __init__(self, root: queue.SimpleQueue):
        self.root = root

    def scroll_handler(self):
        root.put(Event("SCROLLED"))


# Lookup logic
def lookup_handler(
    creator: Creator, kill_switch: queue.SimpleQueue, root: queue.SimpleQueue()
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

            root.put(Event("NOTIFICATION", [creator, latest]))

        sleep(get_timer(con))


# Broker handler
def broker_handler(
    broker: queue.SimpleQueue,
    root: queue.SimpleQueue,
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
                    args=[creator_obj, kill_switch, root],
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


# Icon handler
def icon_handler(icon: pystray.Icon) -> None:
    icon.run()


# Tray handler
def tray_click_handler(root: queue.SimpleQueue) -> Callable:
    def logic(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        root.put(Event("REOPEN"))

    return logic


# Root handler
def root_handler(window: webview.window.Window, root: queue.SimpleQueue) -> int:
    # Thread queues
    broker = queue.SimpleQueue()  # Spawn and kill lookup threads
    debounce = queue.SimpleQueue()  # Used for debouncing input
    page = queue.SimpleQueue()  # Page counter
    page.put(0)  # Starts at 0

    # Input elements
    input_field = window.dom.get_element("#input_field")  # Primary input field
    fav_button = window.dom.get_element("#fav_button")  # Switch favourites button
    settings_button = window.dom.get_element("#settings_button")  # Open settings menu

    # Relevant data
    clist = [
        Creator(creator["service"], creator["id"], creator["name"], 0, "{}")
        for creator in sorted(  # Sorted by most favourites, as per Kemono default
            get_creators_list(kemono),
            key=lambda creator: creator["favorited"],
            reverse=True,
        )
    ]
    if not os.path.exists(PATH + "/data"):  # Check data folder
        os.makedirs(PATH + "/data")
    con = sql.connect(DATABASE)  # Database connection
    ctemplate = window.dom.get_element("#ctemplate")  # Creator section template
    favourites = False  # Favourites mode toggle
    settings = False  # Settings mode toggle
    tray_icon = pystray.Icon(  # Set up tray icon
        "KC",
        icon=Image.open(ICON),
        menu=pystray.Menu(
            pystray.MenuItem(
                "Open KC", tray_click_handler(root), default=True, visible=False
            )
        ),
    )
    last_search = ""  # Last search holder

    # Thread handlers
    threading.Thread(  # Broker handler thread
        daemon=True,
        target=broker_handler,
        args=[
            broker,
            root,
        ],
    ).start()
    threading.Thread(daemon=True, target=icon_handler, args=[tray_icon]).start()

    # Input handlers
    window.events.closed += closed_handler(root)
    window.events.minimized += lambda: window.hide()
    input_field.events.input += input_handler(root, debounce)
    fav_button.events.click += fav_handler(root)
    settings_button.events.click += settings_handler(root)

    # Generate UI function
    def generate_ui(search: str, reset: bool = True) -> None:
        if reset:
            page.get()
            page.put(0)
            p = 0
            [
                c.remove()
                for c in ctemplate.parent.children
                if c.attributes["id"] != ctemplate.attributes["id"]
            ]
        else:
            p = page.get()
            page.put(p)

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
            p * 50 : (p + 1) * 50
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
                last_search = search.event
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
            case reopen if reopen.type == "REOPEN":
                window.restore()
                window.show()
            case scroll if scroll.type == "SCROLLED":
                page.put(page.get() + 1)
                generate_ui(last_search, False)
            case notif if notif.type == "NOTIFICATION":
                creator, latest = notif.event

                screen = webview.screens[0]
                notif_window = webview.create_window(
                    "Notification",
                    url=PATH + "/ui/notification.html",
                    frameless=True,
                    transparent=True,
                    width=500,
                    height=100,
                    x=screen.width - 500,
                    y=0,
                    draggable=False,
                    resizable=False,
                    easy_drag=False,
                    on_top=True,
                )
                threading.Timer(10, lambda w=notif_window: w.destroy()).start()

                close_button = notif_window.dom.get_element("#close_button")
                close_button.events.click += lambda e, w=notif_window: w.destroy()
                notif_window.dom.get_element("#title").text = (
                    f"New post from {creator.name}!"
                )
                notif_window.dom.get_element("#message").text = latest["title"]
                notif_window.dom.get_element("#notification_link").attributes[
                    "href"
                ] = f"https://kemono.su/{creator.service}/user/{creator.id}"
                notif_window.dom.get_element(
                    "#notification_link"
                ).events.click += lambda e, w=notif_window: [sleep(0.1), w.destroy()]

                chime.info()


# Setup and initialization
if __name__ == "__main__":
    root = queue.SimpleQueue()
    jsapi = JSAPI(root)
    window = webview.create_window(
        "KC",
        UI,
        text_select=True,
        resizable=False,
        width=400,
        js_api=jsapi,
    )
    webview.start(root_handler, args=[window, root], gui="qt", icon=ICON)
