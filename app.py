import os, time, sqlite3, requests
from datetime import datetime, timezone
from collections import defaultdict
import pandas as pd
import streamlit as st

API_BASE = "https://api.the-odds-api.com/v4"
DB_PATH = os.getenv("ODDS_DB", "odds_history.sqlite3")
API_KEY = os.getenv("ODDS_API_KEY", "")
REGIONS = os.getenv("ODDS_REGIONS", "eu")
MARKETS = os.getenv("ODDS_MARKETS", "h2h")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))
DROP_THRESHOLD = float(os.getenv("DROP_THRESHOLD", "7.0"))
MIN_BOOKMAKERS = int(os.getenv("MIN_BOOKMAKERS", "2"))

st.set_page_config(page_title="Scanner Dropping Odds", layout="wide")
st.title("Scanner multisports — Dropping odds")
st.caption("Outil d'observation des mouvements de marché. Aucun pari automatique, aucune garantie de gain.")

def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY, captured_at TEXT, sport TEXT, event_id TEXT,
        event TEXT, commence_time TEXT, market TEXT, outcome TEXT,
        bookmaker TEXT, bookmaker_key TEXT, odds REAL)""")
    con.commit()
    return con

def api_get(path, params=None):
    if not API_KEY:
        raise RuntimeError("Clé API absente. Renseigne ODDS_API_KEY dans le fichier .env ou l'environnement.")
    p = dict(params or {})
    p["apiKey"] = API_KEY
    r = requests.get(f"{API_BASE}{path}", params=p, timeout=25)
    r.raise_for_status()
    return r.json(), r.headers

def sports_list():
    data, _ = api_get("/sports/")
    return [s for s in data if s.get("active") and not s.get("has_outrights")]

def fetch_sport(sport_key):
    return api_get(f"/sports/{sport_key}/odds/", {
        "regions": REGIONS, "markets": MARKETS, "oddsFormat": "decimal",
        "dateFormat": "iso"
    })

def save_events(sport, events):
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for ev in events:
        event_name = f'{ev.get("away_team","")} - {ev.get("home_team","")}'
        for book in ev.get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    try: price = float(outcome["price"])
                    except (KeyError, TypeError, ValueError): continue
                    if price <= 1: continue
                    rows.append((now, sport, ev.get("id"), event_name,
                        ev.get("commence_time"), market.get("key"),
                        outcome.get("name"), book.get("title"),
                        book.get("key"), price))
    if rows:
        con = db()
        con.executemany("""INSERT INTO snapshots
          (captured_at,sport,event_id,event,commence_time,market,outcome,bookmaker,bookmaker_key,odds)
          VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)
        con.commit()
        con.close()
    return len(rows)

def load_history(hours=48):
    con = db()
    df = pd.read_sql_query(
        "SELECT * FROM snapshots WHERE captured_at >= datetime('now', ?) ORDER BY captured_at",
        con, params=(f"-{int(hours)} hours",))
    con.close()
    if not df.empty:
        df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True)
    return df

def make_signals(df):
    if df.empty: return pd.DataFrame()
    key = ["sport","event_id","market","outcome","bookmaker_key"]
    latest = df.sort_values("captured_at").groupby(key, as_index=False).tail(1)
    # Compare with first recorded price in the selected history window.
    first = df.sort_values("captured_at").groupby(key, as_index=False).head(1)
    merged = latest.merge(first[key+["odds","captured_at"]], on=key, suffixes=("_now","_first"))
    merged = merged[merged["captured_at_now"] > merged["captured_at_first"]].copy()
    merged["drop_pct"] = (merged["odds_first"] - merged["odds_now"]) / merged["odds_first"] * 100
    # Group same event/market/selection; consensus means multiple separate books moved down.
    gcols = ["sport","event_id","event_now","commence_time_now","market","outcome"]
    out = merged.groupby(gcols).agg(
        books_down=("drop_pct", lambda s: int((s >= DROP_THRESHOLD).sum())),
        median_drop=("drop_pct","median"),
        max_drop=("drop_pct","max"),
        current_best_odds=("odds_now","max"),
        last_seen=("captured_at_now","max")
    ).reset_index()
    out = out[out["books_down"] >= MIN_BOOKMAKERS]
    out["signal"] = out.apply(
        lambda r: "Mouvement confirmé à surveiller" if r["median_drop"] >= DROP_THRESHOLD
        else "Baisse dispersée — prudence", axis=1)
    return out.sort_values(["books_down","median_drop"], ascending=False)

def scan_once():
    sports = sports_list()
    status = []
    remaining = None
    for s in sports:
        try:
            events, headers = fetch_sport(s["key"])
            n = save_events(s["key"], events)
            remaining = headers.get("x-requests-remaining", remaining)
            status.append((s["title"], len(events), n, "OK"))
        except Exception as e:
            status.append((s["title"], 0, 0, str(e)[:120]))
    return pd.DataFrame(status, columns=["Sport","Événements","Cotes enregistrées","État"]), remaining

with st.sidebar:
    st.subheader("Réglages")
    st.write(f"Régions API : `{REGIONS}`")
    st.write(f"Marchés : `{MARKETS}`")
    st.write(f"Intervalle conseillé : {POLL_SECONDS} s")
    st.write(f"Seuil de baisse : {DROP_THRESHOLD:.1f} %")
    st.write(f"Minimum de bookmakers : {MIN_BOOKMAKERS}")
    st.warning("Chaque sport/zone/marché consomme des crédits API. Vérifie ton forfait avant un scan global.")
    st.markdown("[Documentation API](https://the-odds-api.com/liveapi/guides/v4/)")

if not API_KEY:
    st.error("Clé API manquante.")
    st.markdown("1. Crée une clé sur [The Odds API](https://the-odds-api.com/).")
    st.markdown("2. Copie `.env.example` vers `.env` et renseigne `ODDS_API_KEY`.")
    st.markdown("3. Relance l'application.")
    st.stop()

col1, col2 = st.columns([1,3])
with col1:
    if st.button("Scanner maintenant", type="primary"):
        with st.spinner("Collecte des cotes pour les sports actifs..."):
            status, remaining = scan_once()
        st.session_state["last_status"] = status
        st.session_state["remaining"] = remaining
with col2:
    st.info("Le scan est déclenché manuellement dans cette version. Pour une surveillance continue, lance le scan périodiquement sur un serveur fiable.")

if "last_status" in st.session_state:
    st.subheader("Dernier scan")
    st.dataframe(st.session_state["last_status"], use_container_width=True, hide_index=True)
    st.caption(f"Crédits API restants annoncés : {st.session_state.get('remaining') or 'non communiqué'}")

hours = st.selectbox("Fenêtre d'analyse", [6,12,24,48,168], index=2, format_func=lambda x: f"{x} heures" if x < 168 else "7 jours")
history = load_history(hours)
signals = make_signals(history)
st.subheader("Signaux détectés")
if signals.empty:
    st.write("Pas encore de signal confirmé. Il faut plusieurs relevés espacés pour mesurer une évolution.")
else:
    st.dataframe(signals, use_container_width=True, hide_index=True,
                 column_config={"median_drop": st.column_config.NumberColumn("Baisse médiane (%)", format="%.2f%%"),
                                 "max_drop": st.column_config.NumberColumn("Baisse max (%)", format="%.2f%%"),
                                 "current_best_odds": st.column_config.NumberColumn("Meilleure cote actuelle", format="%.2f")})
    st.caption("Le signal décrit une variation observée, pas une preuve de sharp money ni une recommandation de pari.")

st.subheader("Historique collecté")
st.metric("Enregistrements de cotes", f"{len(history):,}")
if not history.empty:
    st.dataframe(history.sort_values("captured_at", ascending=False).head(100),
                 use_container_width=True, hide_index=True)
