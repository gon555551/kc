from constants import *
import sqlite3 as sql


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
