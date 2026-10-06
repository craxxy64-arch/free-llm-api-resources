#!/usr/bin/env python3

import argparse

import db


def latest(conn, provider):
    sql = """
        SELECT m.provider, m.name, m.limits FROM models m
        JOIN (SELECT provider, MAX(pull_id) AS pull_id FROM models GROUP BY provider)
        USING (provider, pull_id)
    """
    params = ()
    if provider:
        sql += " WHERE m.provider = ?"
        params = (provider,)
    for row in conn.execute(sql + " ORDER BY m.provider, m.name", params):
        print(f"{row['provider']:<12} {row['name']:<45} {row['limits']}")


def changes(conn):
    providers = [r[0] for r in conn.execute("SELECT DISTINCT provider FROM models ORDER BY provider")]
    for provider in providers:
        # Compared per provider so a run that crashed partway doesn't look like mass removals.
        pull_ids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT pull_id FROM models WHERE provider = ? ORDER BY pull_id DESC LIMIT 2",
                (provider,),
            )
        ]
        if len(pull_ids) < 2:
            continue
        new, old = (
            {
                r["model_id"]: r
                for r in conn.execute(
                    "SELECT * FROM models WHERE provider = ? AND pull_id = ?", (provider, pid)
                )
            }
            for pid in pull_ids
        )
        for model_id in sorted(new.keys() - old.keys()):
            print(f"+ {provider}: {new[model_id]['name']}")
        for model_id in sorted(old.keys() - new.keys()):
            print(f"- {provider}: {old[model_id]['name']}")
        for model_id in sorted(new.keys() & old.keys()):
            if new[model_id]["limits"] != old[model_id]["limits"]:
                print(
                    f"~ {provider}: {new[model_id]['name']} "
                    f"{old[model_id]['limits']} -> {new[model_id]['limits']}"
                )


def main():
    parser = argparse.ArgumentParser(description="Query the local models database.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_latest = sub.add_parser("latest", help="Show models from each provider's most recent pull")
    p_latest.add_argument("provider", nargs="?")
    sub.add_parser("changes", help="Show what changed between each provider's last two pulls")
    args = parser.parse_args()

    conn = db.connect()
    if args.command == "latest":
        latest(conn, args.provider)
    else:
        changes(conn)


if __name__ == "__main__":
    main()
