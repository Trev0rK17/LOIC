import re
from typing import Optional, Tuple

import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import us

CDC_CANDIDATE_URLS = [
    "https://www.cdc.gov/parasites/naegleria/",
    "https://www.cdc.gov/naegleria/",
]

WIKI_CANDIDATE_URLS = [
    "https://en.wikipedia.org/wiki/Primary_amoebic_meningoencephalitis",
    "https://en.wikipedia.org/wiki/Naegleria_fowleri",
]

STATE_NAME_TO_ABBR = {s.name: s.abbr for s in us.states.STATES}
STATE_NAME_TO_ABBR.update({"District of Columbia": "DC"})


def _extract_state_table_from_html(html: str) -> Optional[pd.DataFrame]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if not headers:
            continue
        header_join = "|".join(h.lower() for h in headers)
        if ("state" in header_join) and ("case" in header_join or "death" in header_join):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"]) ]
                if len(cells) < 2:
                    continue
                rows.append(cells)
            df = pd.DataFrame(rows)
            df.columns = df.iloc[0]
            df = df[1:]
            df.columns = [str(c).strip().lower() for c in df.columns]
            state_col = next((c for c in df.columns if "state" in c), None)
            if state_col is None:
                continue
            value_col = next((c for c in df.columns if ("death" in c) or ("case" in c)), None)
            if value_col is None:
                continue
            out = df[[state_col, value_col]].copy()
            out.columns = ["state", "value"]
            def to_int(x):
                x = re.sub(r"[^0-9]", "", str(x))
                return int(x) if x else 0
            out["value"] = out["value"].map(to_int)
            return out
    return None


def try_fetch_from_cdc() -> Optional[pd.DataFrame]:
    for url in CDC_CANDIDATE_URLS:
        try:
            r = requests.get(url, timeout=15)
            if r.ok and r.text:
                df = _extract_state_table_from_html(r.text)
                if df is not None and len(df) >= 10:
                    df["source"] = url
                    return df
        except Exception:
            pass
    try:
        for url in CDC_CANDIDATE_URLS:
            r = requests.get(url, timeout=15)
            if not (r.ok and r.text):
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a")
            for a in links:
                href = a.get("href") or ""
                text = (a.get_text(" ", strip=True) or "").lower()
                if ("state" in text and "case" in text) or ("state" in href and "case" in href):
                    link = href if href.startswith("http") else ("https://www.cdc.gov" + href)
                    rr = requests.get(link, timeout=15)
                    if rr.ok and rr.text:
                        df = _extract_state_table_from_html(rr.text)
                        if df is not None and len(df) >= 10:
                            df["source"] = link
                            return df
    except Exception:
        pass
    return None


def try_fetch_from_wikipedia() -> Optional[pd.DataFrame]:
    for url in WIKI_CANDIDATE_URLS:
        try:
            r = requests.get(url, timeout=20)
            if r.ok and r.text:
                df = _extract_state_table_from_html(r.text)
                if df is not None and len(df) >= 10:
                    df["source"] = url
                    return df
        except Exception:
            pass
    return None


def build_dataset() -> Tuple[pd.DataFrame, str]:
    df = try_fetch_from_cdc()
    if df is not None:
        df = df.copy()
        df["state"] = df["state"].str.replace(r"\s*\(.*?\)", "", regex=True).str.strip()
        df["state_code"] = df["state"].map(STATE_NAME_TO_ABBR)
        df = df[df["state_code"].notna()].copy()
        df.rename(columns={"value": "deaths_or_cases"}, inplace=True)
        return df, "CDC"
    df = try_fetch_from_wikipedia()
    if df is not None:
        df = df.copy()
        df["state"] = df["state"].str.replace(r"\s*\(.*?\)", "", regex=True).str.strip()
        df["state_code"] = df["state"].map(STATE_NAME_TO_ABBR)
        df = df[df["state_code"].notna()].copy()
        df.rename(columns={"value": "deaths_or_cases"}, inplace=True)
        return df, "Wikipedia"
    sample = pd.DataFrame({
        "state": ["Florida", "Texas", "Arizona", "Louisiana"],
        "deaths_or_cases": [10, 10, 5, 5],
    })
    sample["state_code"] = sample["state"].map(STATE_NAME_TO_ABBR)
    return sample, "Embedded sample (please replace with authoritative data)"


def main():
    df, source_label = build_dataset()
    print(f"Data source: {source_label}")
    print(df.head())
    fig = px.choropleth(
        df,
        locations="state_code",
        locationmode="USA-states",
        color="deaths_or_cases",
        hover_name="state",
        scope="usa",
        color_continuous_scale="Reds",
        labels={"deaths_or_cases": "Deaths (or cases)"},
        title=f"Naegleria fowleri deaths (or cases if deaths unavailable) by U.S. state\nSource: {source_label}",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=60, b=0))
    out_path = "/workspace/naegleria_map.html"
    fig.write_html(out_path)
    print(f"Saved interactive map to {out_path}")


if __name__ == "__main__":
    main()