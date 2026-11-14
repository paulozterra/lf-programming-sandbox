#!/usr/bin/env python3
"""Read-only T9 verification, run from a trusted main checkout in CI."""
import os
import re
from issue_intake import API, Blocked, BOT, verify, REPO


def main():
    api = API(os.environ["GH_TOKEN"])
    number = int(os.environ["PR_NUMBER"])
    sha = os.environ["PR_SHA"]
    pr = api.call("GET", f"/pulls/{number}")
    branch = pr.get("head", {}).get("ref", "")
    if not re.fullmatch(r"lf/request/req-[1-9][0-9]*", branch):
        raise Blocked("PEDIDO_RAMA_INVALIDA")
    if (pr.get("user", {}).get("login") != BOT or
        pr.get("base", {}).get("ref") != "main" or
        pr.get("head", {}).get("repo", {}).get("full_name") != REPO or
        pr.get("head", {}).get("sha") != sha):
        raise Blocked("PEDIDO_PR_NO_CONFIABLE")
    files = api.call("GET", f"/pulls/{number}/files?per_page=100")
    if len(files) != 2 or any(x.get("status") != "added" for x in files):
        raise Blocked("PEDIDO_RUTAS_INVALIDAS")
    paths = [x["filename"] for x in files]
    if branch != "lf/request/req-" + str(int(branch.split("req-")[1])):
        raise Blocked("PEDIDO_RAMA_INVALIDA")
    verify(api, int(branch.split("req-")[1]), sha, paths)
    print("T9_REQUEST_BYTES_MATCH")


if __name__ == "__main__":
    main()
