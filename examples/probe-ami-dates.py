"""Deep probe of the amiEnergyUsages API to find a working approach.

Tests:
1. GraphQL introspection to discover the actual schema types
2. Different date formats with $dateFrom: Date! variables
3. Inline date arguments (bypassing variable type system)
4. Raw HTTP to see full response details

Usage:
    python probe-ami-dates.py --username YOUR_EMAIL --password YOUR_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import aiohttp

from aionatgrid import NationalGridClient, NationalGridConfig
from aionatgrid.graphql import GraphQLRequest, GraphQLResponse, compose_query
from aionatgrid.helpers import create_cookie_jar
from aionatgrid.queries import ami_energy_usages_request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deep probe AMI date formats")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
    return parser.parse_args()


ENDPOINT = "https://myaccount.nationalgrid.com/api/energyusage-cu-uwp-gql"


async def introspect_schema(client: NationalGridClient) -> None:
    """Run introspection queries to discover the schema."""
    print("=== Schema Introspection ===")
    print()

    # Query 1: Get the amiEnergyUsages field definition
    introspection_query = GraphQLRequest(
        query="""
        {
            __type(name: "Query") {
                fields {
                    name
                    args {
                        name
                        type {
                            name
                            kind
                            ofType {
                                name
                                kind
                            }
                        }
                    }
                }
            }
        }
        """,
        variables=None,
        operation_name=None,
        endpoint=ENDPOINT,
    )

    try:
        response = await client.execute(introspection_query)
        if response.errors:
            print(f"  Introspection errors: {json.dumps(response.errors, indent=2)}")
        elif response.data:
            query_type = response.data.get("__type", {})
            fields = query_type.get("fields", [])
            for field in fields:
                if "ami" in field.get("name", "").lower():
                    print(f"  Field: {field['name']}")
                    for arg in field.get("args", []):
                        arg_type = arg.get("type", {})
                        type_name = arg_type.get("name") or (
                            arg_type.get("ofType", {}).get("name", "?")
                            + "!"
                        )
                        print(f"    Arg: {arg['name']}: {type_name}")
                    print()
    except Exception as e:
        print(f"  Introspection failed: {type(e).__name__}: {e}")

    # Query 2: Get the Date scalar type details
    print("--- Date scalar type ---")
    date_type_query = GraphQLRequest(
        query="""
        {
            __type(name: "Date") {
                name
                kind
                description
                specifiedByURL
            }
        }
        """,
        variables=None,
        operation_name=None,
        endpoint=ENDPOINT,
    )

    try:
        response = await client.execute(date_type_query)
        if response.data:
            type_info = response.data.get("__type")
            print(f"  {json.dumps(type_info, indent=2)}")
    except Exception as e:
        print(f"  Failed: {e}")

    # Query 3: Check if DateTime type exists
    print()
    print("--- DateTime scalar type ---")
    datetime_type_query = GraphQLRequest(
        query="""
        {
            __type(name: "DateTime") {
                name
                kind
                description
                specifiedByURL
            }
        }
        """,
        variables=None,
        operation_name=None,
        endpoint=ENDPOINT,
    )

    try:
        response = await client.execute(datetime_type_query)
        if response.data:
            type_info = response.data.get("__type")
            print(f"  {json.dumps(type_info, indent=2)}")
    except Exception as e:
        print(f"  Failed: {e}")

    # Query 4: Check if DateTimeOffset type exists
    print()
    print("--- DateTimeOffset scalar type ---")
    dto_type_query = GraphQLRequest(
        query="""
        {
            __type(name: "DateTimeOffset") {
                name
                kind
                description
                specifiedByURL
            }
        }
        """,
        variables=None,
        operation_name=None,
        endpoint=ENDPOINT,
    )

    try:
        response = await client.execute(dto_type_query)
        if response.data:
            type_info = response.data.get("__type")
            print(f"  {json.dumps(type_info, indent=2)}")
    except Exception as e:
        print(f"  Failed: {e}")

    print()


async def test_raw_http(
    session: aiohttp.ClientSession,
    access_token: str,
    meter_number: str,
    premise_number: str,
    sp: str,
    mp: str,
) -> None:
    """Send raw HTTP requests to see full response details."""
    print("=== Raw HTTP Test (plain date, full response) ===")

    payload = {
        "operationName": "NrtDailyUsage",
        "query": (
            "query NrtDailyUsage("
            "$meterNumber: String!, "
            "$premiseNumber: String!, "
            "$servicePointNumber: String!, "
            "$meterPointNumber: String!, "
            "$dateFrom: Date!, "
            "$dateTo: Date!"
            ") { amiEnergyUsages("
            "meterNumber: $meterNumber, "
            "premiseNumber: $premiseNumber, "
            "servicePointNumber: $servicePointNumber, "
            "meterPointNumber: $meterPointNumber, "
            "dateFrom: $dateFrom, "
            "dateTo: $dateTo"
            ") { nodes { date fuelType quantity } } }"
        ),
        "variables": {
            "meterNumber": meter_number,
            "premiseNumber": premise_number,
            "servicePointNumber": sp,
            "meterPointNumber": mp,
            "dateFrom": "2026-03-10",
            "dateTo": "2026-03-14",
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    async with session.post(ENDPOINT, json=payload, headers=headers) as resp:
        print(f"  Status: {resp.status}")
        print(f"  Headers: {dict(resp.headers)}")
        body = await resp.json(content_type=None)
        print(f"  Body: {json.dumps(body, indent=2)}")
    print()


async def test_energyusagecosts_for_comparison(
    client: NationalGridClient,
    account_number: str,
    region: str,
) -> None:
    """Test energyUsageCosts (which also uses Date!) to see if it works."""
    print("=== Comparison: energyUsageCosts (also uses $date: Date!) ===")
    try:
        from datetime import date
        costs = await client.get_energy_usage_costs(
            account_number=account_number,
            query_date=date(2026, 3, 14),
            company_code=region,
        )
        print(f"  SUCCESS! Got {len(costs)} cost records")
        if costs:
            print(f"  First: {json.dumps(costs[0])}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
    print()


async def main() -> None:
    args = parse_args()
    config = NationalGridConfig(username=args.username, password=args.password)

    cookie_jar = create_cookie_jar()
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with NationalGridClient(config=config, session=session) as client:
            # Discover account and meter info
            print("=== Discovering account info ===")
            accounts = await client.get_linked_accounts()
            if not accounts:
                print("No linked billing accounts found.")
                return

            account_number = accounts[0]["billingAccountId"]
            print(f"Account: {account_number}")

            billing_account = await client.get_billing_account(account_number)
            premise_number = str(billing_account["premiseNumber"])
            region = billing_account.get("region", "")
            print(f"Premise: {premise_number}")
            print(f"Region: {region}")

            meters = billing_account["meter"]["nodes"]
            ami_meter = None
            for m in meters:
                if m.get("hasAmiSmartMeter"):
                    ami_meter = m
                    break

            if not ami_meter:
                print("No AMI smart meter found!")
                return

            meter_number = str(ami_meter["meterNumber"])
            sp = str(ami_meter["servicePointNumber"])
            mp = str(ami_meter["meterPointNumber"])
            print(f"Meter: {meter_number}, SP: {sp}, MP: {mp}")
            print(f"Fuel type: {ami_meter.get('fuelType')}")
            print()

            # 1. Introspect the schema
            await introspect_schema(client)

            # 2. Test energyUsageCosts for comparison (also uses Date!)
            if region:
                await test_energyusagecosts_for_comparison(
                    client, account_number, region
                )

            # 3. Get access token for raw HTTP test
            inner_session = await client._ensure_session()
            access_token = await client._get_access_token(inner_session)

            # 4. Raw HTTP test
            if access_token:
                await test_raw_http(
                    session, access_token,
                    meter_number, premise_number, sp, mp,
                )

            # 5. Test the standard library call
            print("=== Standard library call ===")
            from datetime import date
            request = ami_energy_usages_request(
                variables={
                    "meterNumber": meter_number,
                    "premiseNumber": premise_number,
                    "servicePointNumber": sp,
                    "meterPointNumber": mp,
                    "dateFrom": "2026-03-10",
                    "dateTo": "2026-03-14",
                },
            )
            print(f"  Query: {request.query}")
            print(f"  Variables: {json.dumps(dict(request.variables))}")
            try:
                response = await client.execute(request)
                if response.errors:
                    print(f"  Errors: {json.dumps(response.errors, indent=2)}")
                else:
