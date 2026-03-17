"""Final deep probe - test edge cases and isolate which parameter fails.

Usage:
    python probe-ami-dates.py --username YOUR_EMAIL --password YOUR_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import json

import aiohttp

from aionatgrid import NationalGridClient, NationalGridConfig
from aionatgrid.graphql import GraphQLRequest
from aionatgrid.helpers import create_cookie_jar
from aionatgrid.queries import ami_energy_usages_request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Final deep probe")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
    return parser.parse_args()


ENDPOINT = "https://myaccount.nationalgrid.com/api/energyusage-cu-uwp-gql"


async def test_query(client, label, payload):
    """Execute a raw GraphQL payload and print results."""
    print(f"--- {label} ---")
    request = GraphQLRequest(
        query=payload["query"],
        variables=payload.get("variables"),
        operation_name=payload.get("operationName"),
        endpoint=ENDPOINT,
    )
    try:
        response = await client.execute(request)
        if response.errors:
            for err in response.errors:
                msg = err.get("message", "?")
                code = err.get("extensions", {}).get("code", "")
                path = err.get("path", [])
                print(f"  ERROR [{code}] {path}: {msg}")
        elif response.data:
            ami = response.data.get("amiEnergyUsages")
            if ami:
                nodes = ami.get("nodes", [])
                print(f"  SUCCESS! {len(nodes)} records")
                if nodes and len(nodes) > 0:
                    print(f"  First: {json.dumps(nodes[0])}")
            else:
                print(f"  Data returned but amiEnergyUsages is: {ami}")
                print(f"  Full data: {json.dumps(response.data)}")
        else:
            print(f"  Raw response: {response.raw}")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
    print()


async def main() -> None:
    args = parse_args()
    config = NationalGridConfig(username=args.username, password=args.password)

    cookie_jar = create_cookie_jar()
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with NationalGridClient(config=config, session=session) as client:
            print("=== Discovering account info ===")
            accounts = await client.get_linked_accounts()
            if not accounts:
                print("No linked billing accounts found.")
                return

            account_number = accounts[0]["billingAccountId"]
            billing_account = await client.get_billing_account(account_number)
            premise_number = str(billing_account["premiseNumber"])

            meters = billing_account["meter"]["nodes"]
            ami_meter = None
            for m in meters:
                if m.get("hasAmiSmartMeter"):
                    ami_meter = m
                    break

            if not ami_meter:
                print("No AMI smart meter found!")
                return

            mn = str(ami_meter["meterNumber"])
            sp = str(ami_meter["servicePointNumber"])
            mp = str(ami_meter["meterPointNumber"])
            ft = ami_meter.get("fuelType", "?")
            print(f"Meter: {mn}, SP: {sp}, MP: {mp}, Fuel: {ft}")
            print(f"Premise: {premise_number}")
            print()

            base_vars = {
                "meterNumber": mn,
                "premiseNumber": premise_number,
                "servicePointNumber": sp,
                "meterPointNumber": mp,
            }

            # Test 1: Standard query (confirm the error)
            print("=== Test 1: Standard query (confirm error) ===")
            await test_query(client, "Standard Date! with YYYY-MM-DD", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: Date!, $dateTo: Date!) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom, dateTo: $dateTo) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": "2026-03-10", "dateTo": "2026-03-14"},
            })

            # Test 2: Try with nullable Date (Date instead of Date!)
            print("=== Test 2: Nullable Date (without !) ===")
            await test_query(client, "Nullable $dateFrom: Date, $dateTo: Date", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: Date, $dateTo: Date) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom, dateTo: $dateTo) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": "2026-03-10", "dateTo": "2026-03-14"},
            })

            # Test 3: Try with null dates
            print("=== Test 3: Null dates ===")
            await test_query(client, "Null dateFrom and dateTo", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: Date, $dateTo: Date) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom, dateTo: $dateTo) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": None, "dateTo": None},
            })

            # Test 4: Try without dateFrom/dateTo entirely
            print("=== Test 4: Omit dateFrom/dateTo from variables ===")
            await test_query(client, "No date variables at all", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": base_vars,
            })

            # Test 5: Try with only dateFrom (no dateTo)
            print("=== Test 5: Only dateFrom, no dateTo ===")
            await test_query(client, "Only dateFrom", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: Date!) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": "2026-03-10"},
            })

            # Test 6: Try with String type for dates (bypass Date scalar entirely)
            print("=== Test 6: String! type for dates ===")
            await test_query(client, "String! type for dateFrom/dateTo", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: String!, $dateTo: String!) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom, dateTo: $dateTo) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": "2026-03-10", "dateTo": "2026-03-14"},
            })

            # Test 7: Try querying just __typename (no date args at all)
            print("=== Test 7: Just __typename (minimal query) ===")
            await test_query(client, "Minimal - just __typename", {
                "operationName": "NrtDailyUsage",
                "query": """query NrtDailyUsage($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!) {
  amiEnergyUsages(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber) {
    __typename
  }
}""",
                "variables": base_vars,
            })

            # Test 8: Try the 15-minute variant (amiEnergyUsages15Min)
            print("=== Test 8: amiEnergyUsages15Min (different endpoint) ===")
            await test_query(client, "15-min variant", {
                "operationName": "NrtDailyUsage15Min",
                "query": """query NrtDailyUsage15Min($meterNumber: String!, $premiseNumber: String!, $servicePointNumber: String!, $meterPointNumber: String!, $dateFrom: Date!, $dateTo: Date!) {
  amiEnergyUsages15Min(meterNumber: $meterNumber, premiseNumber: $premiseNumber, servicePointNumber: $servicePointNumber, meterPointNumber: $meterPointNumber, dateFrom: $dateFrom, dateTo: $dateTo) {
    nodes { date fuelType quantity }
  }
}""",
                "variables": {**base_vars, "dateFrom": "2026-03-10", "dateTo": "2026-03-14"},
            })


if __name__ == "__main__":
    asyncio.run(main())
