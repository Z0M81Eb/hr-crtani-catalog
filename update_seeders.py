import json
import os
import random
import socket
import struct
from urllib.parse import parse_qs, urlparse

DB_FILE = "db.json"

DEFAULT_UDP_TRACKERS = [
    ("tracker.opentrackr.org", 1337),
    ("open.stealth.si", 80),
    ("tracker.torrent.eu.org", 451),
    ("exodus.desync.com", 6969),
    ("tracker.tiny-vps.com", 6969),
    ("tracker.moeking.me", 6969),
    ("explodie.org", 6969),
    ("opentor.org", 2710),
]

def extract_udp_trackers(db):
    trackers = set(DEFAULT_UDP_TRACKERS)
    for item in db.values():
        magnet = item.get("magnet", "")
        if not magnet:
            continue
        qs = parse_qs(urlparse(magnet).query)
        for tr in qs.get("tr", []):
            parsed = urlparse(tr)
            if parsed.scheme == "udp" and parsed.hostname and parsed.port:
                trackers.add((parsed.hostname, parsed.port))
    return list(trackers)

def udp_scrape_tracker(host, port, hashes):
    results = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(4.0)
    try:
        ip = socket.gethostbyname(host)
        tx_id = random.randint(1, 0x7FFFFFFF)
        # BEP 15 Connect
        connect_req = struct.pack("!QII", 0x41727101980, 0, tx_id)
        sock.sendto(connect_req, (ip, port))
        resp, _ = sock.recvfrom(16)
        if len(resp) < 16:
            return results
        action, res_tx, conn_id = struct.unpack("!IIQ", resp[:16])
        if action != 0 or res_tx != tx_id:
            return results

        # BEP 15 Scrape (paketi po 50 hasheva)
        for i in range(0, len(hashes), 50):
            chunk = hashes[i : i + 50]
            tx_id = random.randint(1, 0x7FFFFFFF)
            payload = struct.pack("!QII", conn_id, 2, tx_id)
            for h in chunk:
                payload += bytes.fromhex(h)
            sock.sendto(payload, (ip, port))
            resp, _ = sock.recvfrom(8 + 12 * len(chunk))
            if len(resp) < 8:
                continue
            action, res_tx = struct.unpack("!II", resp[:8])
            if action != 2 or res_tx != tx_id:
                continue
            for idx, h in enumerate(chunk):
                offset = 8 + idx * 12
                if offset + 12 <= len(resp):
                    seeders, completed, leechers = struct.unpack(
                        "!III", resp[offset : offset + 12]
                    )
                    results[h] = seeders
    except Exception:
        pass
    finally:
        sock.close()
    return results

def main():
    if not os.path.exists(DB_FILE):
        print("Nema db.json datoteke.")
        return

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    hashes = list(
        {
            item["infoHash"].lower()
            for item in db.values()
            if item.get("infoHash") and len(item["infoHash"]) == 40
        }
    )

    trackers = extract_udp_trackers(db)
    print(f"Provjeravam {len(hashes)} filmova na {len(trackers)} UDP trackera...")

    best_seeders = {h: 0 for h in hashes}
    working_trackers = 0

    for host, port in trackers:
        res = udp_scrape_tracker(host, port, hashes)
        if res:
            working_trackers += 1
            for h, s in res.items():
                if s > best_seeders[h]:
                    best_seeders[h] = s

    print(f"Odgovorilo trackera: {working_trackers}/{len(trackers)}")

    if working_trackers == 0:
        print("Nijedan tracker nije odgovorio — ne mijenjam db.json.")
        return

    active_count = 0
    for item in db.values():
        h = (item.get("infoHash") or "").lower()
        seeders = best_seeders.get(h, 0)
        item["seeders"] = seeders
        if seeders > 0:
            active_count += 1

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"Gotovo! Filmova sa seederima > 0: {active_count}/{len(db)}")

if __name__ == "__main__":
    main()
