import os
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Constants
GRAPH_URL = "https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
API_KEY = "691257c3d250f6e64f1ec96fc6ff6c85" #Tell Matt/Carlos/Niklas they can use my API key

# Token pair and fee
TOKEN0 = "WETH" # Can be optimised later, quick and dirty way to test ccy pair
TOKEN1 = "USDT"
FEE_CHOICES = {"1": [100], "2": [500], "3": [3000], "4": [10000], "5": [100, 500, 3000, 10000]}
FEE_INPUT = "2"
FEE_TIERS = FEE_CHOICES[FEE_INPUT]


def graphql_query(query):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.post(GRAPH_URL, json={"query": query}, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def get_pools(token0, token1, fee_tiers):
    all_pools = []
    last_id = ""

    while True:
        query = f"""
        {{
          pools(first: 1000, where: {{ id_gt: "{last_id}" }}) {{
            id
            token0 {{ symbol }}
            token1 {{ symbol }}
            feeTier
          }}
        }}
        """
        data = graphql_query(query)
        batch = data["data"]["pools"]
        if not batch:
            break
        all_pools.extend(batch)
        last_id = batch[-1]["id"]
        print(f"O Retrieved {len(all_pools)} pools so far...")

    # Filter matches
    matches = []
    for pool in all_pools:
        symbols = {pool["token0"]["symbol"].upper(), pool["token1"]["symbol"].upper()}
        if {token0, token1} == symbols and int(pool["feeTier"]) in fee_tiers:
            matches.append(pool)

    print(f"(Y) Found {len(matches)} matching pools for {token0}/{token1} with fee tier(s) {fee_tiers}")
    return matches


def fetch_ticks(pool_id):
    ticks = []
    last_id = ""
    while True:
        query = f"""
        {{
          ticks(first: 1000, where: {{ poolAddress: "{pool_id}", id_gt: "{last_id}" }}) {{
            id
            tickIdx
            liquidityNet
            liquidityGross
          }}
        }}
        """
        result = graphql_query(query)
        batch = result["data"]["ticks"]
        if not batch:
            break
        ticks.extend(batch)
        last_id = batch[-1]["id"]
    return pd.DataFrame(ticks)

def plot_liquidity_scatter(pools_data):
    plt.figure(figsize=(18, 6))
    for pool in pools_data:
        df = pool["df"]
        plt.scatter(df["tick"], df["liquidity"], label=pool["label"], s=2, alpha=0.6)

    plt.xlabel("Tick Index")
    plt.yscale("log")
    plt.ylabel("Liquidity (Billions)")
    plt.title("Liquidity Distribution by Tick Index")
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.3)
    plt.tight_layout()
    plt.show()


# ---- Main Logic ----
pools = get_pools(TOKEN0, TOKEN1, FEE_TIERS)
if not pools:
    print("No matching pools found.")
    exit()

liquidity_curves = []

for pool in pools:
    print(f"Processing pool {pool['id'][-6:]} (Fee: {int(pool['feeTier']) / 1000000:.2%})")
    ticks_df = fetch_ticks(pool["id"])
    if ticks_df.empty:
        print(f"Skipping pool {pool['id']} — no tick data found.")
        continue

    ticks_df["tick"] = pd.to_numeric(ticks_df["tickIdx"], errors="coerce")
    ticks_df["liquidityGross"] = ticks_df["liquidityGross"].astype(float)
    ticks_df["liquidity"] = ticks_df["liquidityGross"] / 1e9  # Convert to billions for plotting

    liquidity_curves.append({
        "df": ticks_df[["tick", "liquidity"]],
        "label": f"Fee: {int(pool['feeTier']) / 1000000:.2%} - {pool['id'][-6:]}"
    })


plot_liquidity_scatter(liquidity_curves)