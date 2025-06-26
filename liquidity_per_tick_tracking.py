import os
import requests
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.ticker as mtick
import json
import time

# Load environment variables
load_dotenv()

# Constants
UNISWAP_V3_SUBGRAPH_URL = "https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
API_KEY = "691257c3d250f6e64f1ec96fc6ff6c85" # Can hide in env variables later
CACHE_FILE = Path("/mnt/data/pool_cache.json")

# GraphQL with retry logic
def graphql_query_with_retries(query, max_retries=5, delay=2):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    for attempt in range(max_retries):
        try:
            response = requests.post(UNISWAP_V3_SUBGRAPH_URL,json={"query": query}, headers=headers, timeout=10 )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(delay)
    raise Exception("All GraphQL retries failed.")

# Get token input from user
def get_user_token_pair_and_fee():
    print("Enter token symbols (e.g., USDT WETH):")
    token0 = input("Token 0: ").strip().upper()
    token1 = input("Token 1: ").strip().upper()

    print("Select fee tier:")
    print("1) 0.01%")
    print("2) 0.05%")
    print("3) 0.3%")
    print("4) All tiers")
    choice = input("Choose 1, 2, 3 or 4").strip()

    fee_options = {"1": [100], "2": [500], "3": [3000], "4": [100, 500, 3000]}

    return token0, token1, fee_options.get(choice, [3000])

# Search for pool with tokens and fee tier
def find_pool_address(token0_sym, token1_sym, fee_tiers):
    print("Searching for pools...")
    query = """
    {
      pools(first: 1000) {
        id
        token0 { symbol id }
        token1 { symbol id }
        feeTier
      }
    }
    """
    result = graphql_query_with_retries(query)
    all_pools = result["data"]["pools"]

    matching_pools = []
    for pool in all_pools:
        t0, t1 = pool["token0"]["symbol"].upper(), pool["token1"]["symbol"].upper()
        if {t0, t1} == {token0_sym, token1_sym} and int(pool["feeTier"]) in fee_tiers:
            matching_pools.append(pool)

    return matching_pools

# Fetch paginated tick data
def fetch_all_ticks(pool_id):
    print("Fetching tick data...")
    ticks = []
    last_id = ""
    while True:
        query = f"""
        {{
          ticks(first: 1000, where: {{ poolAddress: "{pool_id}", id_gt: "{last_id}" }}) {{
            id
            tickIdx
            liquidityGross
            liquidityNet
          }}
        }}
        """
        result = graphql_query_with_retries(query)
        batch = result["data"]["ticks"]
        if not batch:
            break
        ticks.extend(batch)
        last_id = batch[-1]["id"]
    return ticks


# Process multiple pools and annotate fee tier
def get_combined_tick_data(pools):
    combined_df = pd.DataFrame()
    for pool in pools:
        fee = int(pool["feeTier"]) / 10000
        print(f"Fetching ticks for pool {pool['id']} with fee tier {fee:.2%}")
        ticks = fetch_all_ticks(pool["id"])
        df = pd.DataFrame(ticks)
        df["tickIdx"] = df["tickIdx"].astype(int)
        df["liquidityGross"] = df["liquidityGross"].astype(float)
        df["liquidityNet"] = df["liquidityNet"].astype(float)
        df["feeTier"] = f"{fee:.2%}"
        df["pool_id"] = pool["id"]
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    return combined_df.sort_values(["feeTier", "tickIdx"])

def tick_to_price(tick_idx):
    return 1.0001 ** tick_idx


def plot_liquidity_per_tick(df):
    if df.empty:
        print("DataFrame is empty. Nothing to plot.")
        return

    plt.figure(figsize=(14, 6))
    grouped = df.groupby("pool_id")

    for i, (pool_id, subset) in enumerate(grouped):
        subset = subset.copy()
        subset["liquidityGross"] = pd.to_numeric(subset["liquidityGross"], errors="coerce")
        subset = subset.dropna(subset=["liquidityGross"])
        subset = subset[subset["liquidityGross"] > 0]

        print(f"Pool: {pool_id[-6:]}, Points: {len(subset)}")

        if subset.empty:
            print(f"Skipping pool {pool_id} — no positive liquidity.")
            continue

        label = f"Fee: {subset['feeTier'].iloc[0]} - {pool_id[-12:]}"
        x_vals = tick_to_price(subset["tickIdx"])

        plt.scatter(x_vals, subset["liquidityGross"], alpha=0.7, label=label)

    if not plt.gca().has_data():
        print("No data was plotted.")
        return

    plt.title("Liquidity per Price Range by Pool and Fee Tier")
    plt.xlabel("Price (from Tick Index)")
    plt.ylabel("Liquidity Gross")
    plt.grid(True, axis="y")

    try:
        ymax = df["liquidityGross"].max()
        if ymax > 0:
            plt.ylim(0, ymax * 1.1)
    except:
        pass

    plt.legend()
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()

# Main logic
def main():
    token0, token1, fees = get_user_token_pair_and_fee()
    pools = find_pool_address(token0, token1, fees)
    if not pools:
        print("No matching pools found.")
        return
    tick_data = get_combined_tick_data(pools)
    plot_liquidity_per_tick(tick_data)

main()