import json
import os
import time
import requests

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TITLES_FILE = "titles.txt"

CATALOGS = [
    {"type": "movie", "id": "hr_disney_classic", "name": "Disney Klasici"},
    {"type": "movie", "id": "hr_disney_modern", "name": "Moderni Disney"},
    {"type": "movie", "id": "hr_pixar", "name": "Pixar"},
    {"type": "movie", "id": "hr_dreamworks", "name": "DreamWorks"},
    {"type": "movie", "id": "hr_illumination", "name": "Illumination"},
    {"type": "movie", "id": "hr_lego", "name": "LEGO"},
    {"type": "movie", "id": "hr_ostali_crtani", "name": "Ostali crtani"},
    {"type": "movie", "id": "hr_filmovi", "name": "Filmovi za djecu"},
]

VALID_ROWS = {c["id"] for c in CATALOGS}


def load_titles():
    entries = []
    seen = set()
    with open(TITLES_FILE, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            imdb_id = parts[0]
            override = parts[1] if len(parts) > 1 and parts[1] in VALID_ROWS else None
            if imdb_id.startswith("tt") and imdb_id not in seen:
                seen.add(imdb_id)
                entries.append((imdb_id, override))
    return entries


def fetch_tmdb_movie(imdb_id):
    find_resp = requests.get(
        f"https://api.themoviedb.org/3/find/{imdb_id}",
        params={"api_key": TMDB_API_KEY, "external_source": "imdb_id", "language": "hr-HR"},
        timeout=15,
    ).json()

    results = find_resp.get("movie_results") or []
    if not results:
        return None

    tmdb_id = results[0]["id"]
    d = requests.get(
        f"https://api.themoviedb.org/3/movie/{tmdb_id}",
        params={"api_key": TMDB_API_KEY, "language": "hr-HR"},
        timeout=15,
    ).json()

    poster_path = d.get("poster_path")
    backdrop_path = d.get("backdrop_path")
    overview = (d.get("overview") or "").strip()

    # Fallback to English if Croatian poster or overview is missing
    if not poster_path or not overview or not backdrop_path:
        d_en = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY, "language": "en-US"},
            timeout=15,
        ).json()
        poster_path = poster_path or d_en.get("poster_path")
        backdrop_path = backdrop_path or d_en.get("backdrop_path")
        overview = overview or (d_en.get("overview") or "").strip()

    release_date = d.get("release_date") or ""
    year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else 0
    companies = [c["name"] for c in d.get("production_companies", [])]
    genres = d.get("genres", [])
    genre_ids = {g["id"] for g in genres}
    genre_names = [g["name"] for g in genres]

    return {
        "id": imdb_id,
        "type": "movie",
        "name": d.get("title") or d.get("original_title") or imdb_id,
        "original_title": d.get("original_title") or "",
        "poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
        "background": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else "",
        "description": overview,
        "releaseInfo": str(year) if year else "",
        "genres": genre_names,
        "_year": year,
        "_companies": companies,
        "_is_animation": 16 in genre_ids,  # TMDB genre ID 16 = Animation
    }


def assign_row(movie, override):
    if override:
        return override

    companies_low = " | ".join(movie["_companies"]).lower()
    title_low = f"{movie['name']} {movie['original_title']}".lower()

    if not movie["_is_animation"]:
        return "hr_filmovi"
    if "lego" in title_low or "lego" in companies_low:
        return "hr_lego"
    if "pixar" in companies_low:
        return "hr_pixar"
    if "dreamworks" in companies_low:
        return "hr_dreamworks"
    if "illumination" in companies_low:
        return "hr_illumination"
    if "walt disney" in companies_low:
        return "hr_disney_classic" if movie["_year"] <= 2009 else "hr_disney_modern"

    return "hr_ostali_crtani"


def main():
    entries = load_titles()
    buckets = {c["id"]: [] for c in CATALOGS}

    for idx, (imdb_id, override) in enumerate(entries, 1):
        print(f"[{idx}/{len(entries)}] Fetching {imdb_id}...")
        movie = fetch_tmdb_movie(imdb_id)
        if not movie:
            print(f"  -> Skipped (not found on TMDB)")
            continue

        row_id = assign_row(movie, override)
        buckets[row_id].append({
            "id": movie["id"],
            "type": "movie",
            "name": movie["name"],
            "poster": movie["poster"],
            "background": movie["background"],
            "description": movie["description"],
            "releaseInfo": movie["releaseInfo"],
            "genres": movie["genres"],
        })
        time.sleep(0.25)

    # Sort each row alphabetically by Croatian title (or remove this line to keep titles.txt order)
    for row_id in buckets:
        buckets[row_id].sort(key=lambda m: m["name"].lower())

    manifest = {
        "id": "org.hrsink.catalog",
        "version": "1.0.0",
        "name": "HR Sinkronizirani Crtani",
        "description": "Katalog hrvatskih sinkroniziranih crtanih filmova i filmova za djecu",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": CATALOGS,
    }

    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    os.makedirs("catalog/movie", exist_ok=True)
    for row_id, metas in buckets.items():
        with open(f"catalog/movie/{row_id}.json", "w", encoding="utf-8") as f:
            json.dump({"metas": metas}, f, ensure_ascii=False, indent=2)

    print("Catalog build complete.")


if __name__ == "__main__":
    main()
