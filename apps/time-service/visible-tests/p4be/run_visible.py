"""P4 visible check (BACKEND): a reminder created with priority HIGH returns it,
and GET /api/reminders?priority=HIGH lists it. The hidden exam checks more
behaviour derived from the request (defaults, editing, filters, errors)."""
import glob
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

jars = [j for j in glob.glob("apps/time-service/target/*.jar") if not j.endswith(".original")]
assert len(jars) == 1, ("JAR", jars)
s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
proc = subprocess.Popen(["java", "-jar", jars[0], "--server.port=%d" % port, "--app.time.zone=UTC"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=5) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ""


try:
    for _ in range(120):
        try:
            req("/api/time")
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise AssertionError("NO_START")
    st, b = req("/api/reminders", "POST", {"text": "Visible check", "at": "08:00:00", "priority": "HIGH"})
    assert st == 201 and json.loads(b).get("priority") == "HIGH", ("CREATE_HIGH", st, b)
    st, b = req("/api/reminders?priority=HIGH")
    assert st == 200 and [x["text"] for x in json.loads(b)] == ["Visible check"], ("FILTER_HIGH", st, b)
finally:
    proc.terminate()
    proc.wait(15)
print("P4_BE_VISIBLE_OK")
