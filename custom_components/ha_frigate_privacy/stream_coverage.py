"""Best-effort stream topology; never return Frigate configuration or aliases."""
from urllib.parse import urlsplit


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
    names = set(cameras)
    aliases = set(streams)
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
            if not isinstance(item, dict):
                return unknown
            path = item.get("path")
            if not isinstance(path, str):
                continue
            try:
                url = urlsplit(path)
                if url.scheme.lower() != "rtsp" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.port != 8554:
                    continue
                alias = url.path.lstrip("/")
                if alias in aliases:
                    explicit[name].add(alias)
            except ValueError:
                continue
    assigned = set()
    for alias in aliases:
        owners = {name for name in names if alias in explicit[name]}
        if not owners:
            matches = [name for name in names if alias == name or alias.startswith(name + "_")]
            if matches:
                owners = {max(matches, key=len)}
        if owners == {camera_name}:
            assigned.add(alias)
    return {"status": "best_effort", "count": len(assigned)}
