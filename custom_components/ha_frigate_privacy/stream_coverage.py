"""Best-effort stream topology; never return Frigate configuration or aliases."""
from urllib.parse import urlsplit


def _endpoint(go2rtc):
    """Return the configured local RTSP listener, or None for invalid data."""
    rtsp = go2rtc.get("rtsp", {})
    if not isinstance(rtsp, dict):
        return None
    listen = rtsp.get("listen", ":8554")
    if not isinstance(listen, str):
        return None
    try:
        parsed = urlsplit(listen if "://" in listen else "rtsp://" + listen)
        port = parsed.port
        host = parsed.hostname
        if parsed.scheme != "rtsp" or port is None or parsed.path not in ("", "/"):
            return None
    except ValueError:
        return None
    hosts = {"127.0.0.1", "localhost", "::1"}
    if host and host not in ("0.0.0.0", "::"):
        hosts.add(host.lower())
    return hosts, port


def _reference(value, aliases, endpoint, *, bare=False):
    if not isinstance(value, str):
        return None
    if bare and value in aliases:
        return value
    try:
        url = urlsplit(value)
        if (url.scheme.lower() != "rtsp" or not url.hostname
                or url.hostname.lower() not in endpoint[0] or url.port != endpoint[1]):
            return None
        alias = url.path.lstrip("/")
        return alias if alias in aliases else None
    except ValueError:
        return None


def stream_coverage(config, camera_name):
    unknown = {"status": "unknown"}
    if not isinstance(config, dict) or not isinstance(camera_name, str):
        return unknown
    cameras = config.get("cameras")
    go2rtc = config.get("go2rtc")
    streams = go2rtc.get("streams") if isinstance(go2rtc, dict) else None
    if not isinstance(cameras, dict) or not isinstance(streams, dict) or camera_name not in cameras:
        return unknown
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in cameras.items()):
        return unknown
    if any(not isinstance(k, str) for k in streams):
        return unknown
    endpoint = _endpoint(go2rtc)
    if endpoint is None:
        return unknown
    names, aliases = set(cameras), set(streams)
    explicit = {name: set() for name in names}
    for name, camera in cameras.items():
        live = camera.get("live", {})
        if not isinstance(live, dict) or not isinstance(live.get("streams", {}), dict):
            return unknown
        for alias in live.get("streams", {}).values():
            if not isinstance(alias, str):
                return unknown
            if alias in aliases:
                explicit[name].add(alias)
        ffmpeg = camera.get("ffmpeg", {})
        if not isinstance(ffmpeg, dict) or not isinstance(ffmpeg.get("inputs", []), list):
            return unknown
        for item in ffmpeg.get("inputs", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                return unknown
            roles = item.get("roles", [])
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                return unknown
            alias = _reference(item["path"], aliases, endpoint)
            if alias:
                explicit[name].add(alias)

    # Follow a nested reference only when it has one parent. Shared sources do
    # not establish which camera owns the underlying stream.
    children = {alias: set() for alias in aliases}
    parents = {alias: set() for alias in aliases}
    for alias, source in streams.items():
        sources = source if isinstance(source, list) else [source]
        for item in sources:
            target = _reference(item, aliases, endpoint, bare=True)
            if target and target != alias:
                children[alias].add(target)
                parents[target].add(alias)
    owners = {alias: {name for name in names if alias in explicit[name]} for alias in aliases}
    changed = True
    while changed:
        changed = False
        for alias in aliases:
            for child in children[alias]:
                if len(parents[child]) == 1 and owners[alias] and not owners[child].issuperset(owners[alias]):
                    owners[child].update(owners[alias])
                    changed = True
    assigned = set()
    for alias in aliases:
        alias_owners = owners[alias]
        if not alias_owners and len(parents[alias]) <= 1:
            matches = [name for name in names if alias == name or alias.startswith(name + "_")]
            if matches:
                alias_owners = {max(matches, key=len)}
        if alias_owners == {camera_name}:
            assigned.add(alias)
    return {"status": "best_effort", "count": len(assigned)}
