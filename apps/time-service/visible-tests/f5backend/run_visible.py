"""F5 visible check: demo login returns a token; a wrong password returns 401 SBX-E-GENERIC;
the token opens /api/auth/session. The hidden exam checks lock, expiry, logs and hashing."""
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


def req(path, method="GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


try:
    for _ in range(120):
        try:
            req("/api/time")
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise AssertionError("NO_START")
    st, b = req("/api/auth/login", "POST", {"username": "demo", "password": "Sandbox-Demo-2026"})
    assert st == 200 and len(json.loads(b)["token"]) >= 16, ("LOGIN", st, b)
    token = json.loads(b)["token"]
    st, b = req("/api/auth/session", token=token)
    assert st == 200 and json.loads(b).get("username") == "demo", ("SESSION", st, b)
    st, b = req("/api/auth/login", "POST", {"username": "demo", "password": "wrong"})
    assert st == 401 and json.loads(b) == {"error": "SBX-E-GENERIC"}, ("WRONG", st, b)
finally:
    proc.terminate()
    proc.wait(15)
print("F5_VISIBLE_OK")
