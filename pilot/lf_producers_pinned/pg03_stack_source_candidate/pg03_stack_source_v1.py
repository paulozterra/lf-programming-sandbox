"""PG-03_C1: offline, exact-Git-object stack evidence. Qualification only."""
import hashlib
import json
import xml.etree.ElementTree as ET
import re
import subprocess
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
ALLOWED = {"pom.xml": "MAVEN", "package.json": "NODE", "package-lock.json": "NODE_LOCK",
           "pnpm-lock.yaml": "PNPM_LOCK", "yarn.lock": "YARN_LOCK",
           "build.gradle": "GRADLE", "build.gradle.kts": "GRADLE"}
class StackSourceBlocked(ValueError):
    pass

def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if p.returncode: raise StackSourceBlocked("EXACT_GIT_OBJECT_UNAVAILABLE")
    return p.stdout

def resolve_stack(repo, repo_full_name, commit_sha, paths):
    if not isinstance(repo_full_name, str) or "/" not in repo_full_name:
        raise StackSourceBlocked("TARGET_REPO_BINDING_INVALID")
    if not isinstance(commit_sha, str) or not SHA40.fullmatch(commit_sha):
        raise StackSourceBlocked("TARGET_COMMIT_INVALID")
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise StackSourceBlocked("SOURCE_MANIFEST_INVALID")
    root=Path(repo)
    # No working-tree files, mutable refs, or Git network operation.
    resolved = _git(root, "rev-parse", "--verify", commit_sha+"^{commit}").decode().strip()
    if resolved != commit_sha: raise StackSourceBlocked("COMMIT_IDENTITY_MISMATCH")
    evidence=[]
    for path in sorted(paths):
        if not isinstance(path,str) or path not in ALLOWED:
            raise StackSourceBlocked("UNSUPPORTED_STACK_SOURCE_PATH")
        raw = _git(root, "show", commit_sha+":"+path)
        if not raw.strip(): raise StackSourceBlocked("EMPTY_STACK_SOURCE")
        evidence.append({"path":path,"kind":ALLOWED[path],
                         "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
    return {"status":"CANDIDATE_NOT_ADMITTED","authority":False,
            "repo_full_name":repo_full_name,"commit_sha":commit_sha,
            "sources":evidence,"stack_profile_verified":False,
            "reason":"SOURCE_OBJECTS_PINNED_STACK_SEMANTICS_UNVERIFIED"}

def resolve_stack_semantics(repo, repo_full_name, commit_sha, paths):
    """Parse pinned Maven/Node declarations; not independently authenticated."""
    result = resolve_stack(repo, repo_full_name, commit_sha, paths)
    profiles=[]
    for source in result["sources"]:
        path=source["path"]
        raw=_git(Path(repo), "show", commit_sha+":"+path)
        if path == "pom.xml":
            try:
                root=ET.fromstring(raw)
                if root.tag.rsplit("}",1)[-1] != "project":
                    raise ValueError("root")
                def val(name):
                    for child in root:
                        if child.tag.rsplit("}",1)[-1]==name:
                            return (child.text or "").strip()
                    return ""
                version=val("modelVersion")
                if version!="4.0.0":
                    raise ValueError("modelVersion")
            except (ET.ParseError, ValueError):
                raise StackSourceBlocked("MAVEN_MODEL_INVALID")
            profiles.append({"path":path,"ecosystem":"MAVEN","model_version":version})
        elif path == "package.json":
            try:
                data=json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise StackSourceBlocked("NODE_PACKAGE_INVALID")
            if not isinstance(data,dict) or not isinstance(data.get("name"),str) or not data["name"].strip():
                raise StackSourceBlocked("NODE_PACKAGE_INVALID")
            for field in ("dependencies","devDependencies"):
                if field in data and (not isinstance(data[field],dict) or any(
                    not isinstance(k,str) or not k or not isinstance(v,str) or not v.strip()
                    for k,v in data[field].items())):
                    raise StackSourceBlocked("NODE_DEPENDENCIES_INVALID")
            profiles.append({"path":path,"ecosystem":"NODE",
                             "name":data["name"],"declared_dependencies":{
                                 k:data.get(k,{}) for k in ("dependencies","devDependencies")}})
        elif path == "package-lock.json":
            try:
                data=json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise StackSourceBlocked("NODE_LOCK_INVALID")
            if not isinstance(data,dict) or type(data.get("lockfileVersion")) is not int or data["lockfileVersion"] not in (2,3):
                raise StackSourceBlocked("NODE_LOCK_INVALID")
            if not isinstance(data.get("name"),str) or not data["name"].strip() or not isinstance(data.get("packages"),dict):
                raise StackSourceBlocked("NODE_LOCK_INVALID")
            root_pkg=data["packages"].get("")
            if not isinstance(root_pkg,dict) or any(not isinstance(root_pkg.get(k,{}),dict) for k in ("dependencies","devDependencies")):
                raise StackSourceBlocked("NODE_LOCK_INVALID")
            profiles.append({"path":path,"ecosystem":"NODE_LOCK","name":data["name"],
                             "lockfile_version":data["lockfileVersion"],
                             "root_declared_dependencies":{k:root_pkg.get(k,{}) for k in ("dependencies","devDependencies")}})
        else:
            raise StackSourceBlocked("SEMANTIC_PARSER_NOT_IMPLEMENTED:"+path)
    node=next((p for p in profiles if p["ecosystem"]=="NODE"),None)
    lock=next((p for p in profiles if p["ecosystem"]=="NODE_LOCK"),None)
    if node and lock:
        if node["name"]!=lock["name"] or node["declared_dependencies"]!=lock["root_declared_dependencies"]:
            raise StackSourceBlocked("NODE_LOCK_DECLARATION_DRIFT")
    result["parsed_profiles"]=profiles
    result["stack_profile_verified"]=False
    result["reason"]="STACK_DECLARATIONS_PARSED_NO_AUTHENTICATED_PROFILE"
    return result
