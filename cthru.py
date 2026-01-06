#!/usr/bin/env python3
"""
CTHRU CLI - Query Massachusetts state financial data from the CTHRU portal.

Usage:
    cthru spending [options]    Query vendor/department spending
    cthru payroll [options]     Query state employee compensation  
    cthru settlements [options] Query legal settlements
    cthru revenue [options]     Query revenue collections
    cthru datasets [--info ID]  List datasets or show fields
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# API Configuration
API_BASE = "https://cthru.data.socrata.com/resource"

DATASETS = {
    "spending": {
        "id": "pegc-naaa",
        "name": "Comptroller Spending",
        "description": "Vendor payments and department expenditures",
        "key_fields": ["vendor", "department", "amount", "budget_fiscal_year", "date"],
    },
    "payroll": {
        "id": "9ttk-7vz6",
        "name": "Commonwealth Payroll",
        "description": "State employee salaries and compensation",
        "key_fields": ["name_first", "name_last", "department_division", "position_title", "pay_total_actual", "year"],
    },
    "settlements": {
        "id": "gpqz-7ppn",
        "name": "Settlements & Judgments",
        "description": "Legal settlement payments",
        "key_fields": [],
    },
    "revenue": {
        "id": "kcy7-ivxi",
        "name": "Revenue Collections",
        "description": "Tax and non-tax revenue",
        "key_fields": [],
    },
    "retirement": {
        "id": "pni4-392n",
        "name": "Retirement Benefits",
        "description": "Pension and retirement data",
        "key_fields": [],
    },
    "quasi_payroll": {
        "id": "tc5d-8ckm",
        "name": "Quasi-Government Payroll",
        "description": "MBTA, Massport, etc. payroll",
        "key_fields": [],
    },
    "quasi_financials": {
        "id": "j7hg-9qyq",
        "name": "Quasi-Government Financials",
        "description": "Quasi-government spending",
        "key_fields": [],
    },
    "new_hires": {
        "id": "pnz5-htzq",
        "name": "New Hires",
        "description": "New state employee data",
        "key_fields": [],
    },
    "stabilization": {
        "id": "5v4s-nq74",
        "name": "Stabilization Fund",
        "description": "Rainy day fund activity",
        "key_fields": [],
    },
}


def load_credentials():
    """Load API credentials from cthru_api file."""
    script_dir = Path(__file__).parent
    token_file = script_dir / "cthru_api"
    
    if not token_file.exists():
        return None, None
    
    app_token = None
    secret = None
    
    try:
        content = token_file.read_text()
        for line in content.strip().split("\n"):
            if line.startswith("ID:"):
                app_token = line.split(":", 1)[1].strip()
            elif line.startswith("secret:"):
                secret = line.split(":", 1)[1].strip()
    except Exception:
        pass
    
    return app_token, secret


def build_query(args, dataset_key):
    """Build SoQL query parameters from command line args."""
    params = {}
    where_clauses = []
    
    # Limit and offset
    params["$limit"] = str(args.limit)
    if args.offset:
        params["$offset"] = str(args.offset)
    
    # Year filter
    if args.year:
        if dataset_key == "spending":
            where_clauses.append(f"budget_fiscal_year = '{args.year}'")
        elif dataset_key == "payroll":
            where_clauses.append(f"year = {args.year}")
    
    # Department filter
    if args.dept:
        if dataset_key == "spending":
            where_clauses.append(f"upper(department) like upper('%{args.dept}%')")
        elif dataset_key == "payroll":
            where_clauses.append(f"upper(department_division) like upper('%{args.dept}%')")
    
    # Vendor filter (spending only)
    if hasattr(args, 'vendor') and args.vendor:
        where_clauses.append(f"upper(vendor) like upper('%{args.vendor}%')")
    
    # Fund filter (spending only) - uses fund name for reliability
    if hasattr(args, 'fund') and args.fund:
        where_clauses.append(f"upper(fund) like upper('%{args.fund}%')")
    
    # Amount filters
    if hasattr(args, 'min_amount') and args.min_amount is not None:
        if dataset_key == "spending":
            where_clauses.append(f"amount >= {args.min_amount}")
        elif dataset_key == "payroll":
            where_clauses.append(f"pay_total_actual >= {args.min_amount}")
    
    if hasattr(args, 'max_amount') and args.max_amount is not None:
        if dataset_key == "spending":
            where_clauses.append(f"amount <= {args.max_amount}")
        elif dataset_key == "payroll":
            where_clauses.append(f"pay_total_actual <= {args.max_amount}")
    
    # Name filter (payroll only)
    if hasattr(args, 'name') and args.name:
        where_clauses.append(f"(upper(name_first) like upper('%{args.name}%') OR upper(name_last) like upper('%{args.name}%'))")
    
    # Search filter (generic text search)
    if args.search:
        if dataset_key == "spending":
            where_clauses.append(f"(upper(vendor) like upper('%{args.search}%') OR upper(department) like upper('%{args.search}%'))")
        elif dataset_key == "payroll":
            where_clauses.append(f"(upper(name_first) like upper('%{args.search}%') OR upper(name_last) like upper('%{args.search}%') OR upper(department_division) like upper('%{args.search}%'))")
    
    # Combine where clauses
    if where_clauses:
        params["$where"] = " AND ".join(where_clauses)
    
    # Order by
    if args.sort:
        params["$order"] = args.sort
    
    return params


def generate_socrata_url(dataset_id, params):
    """Generate a Socrata portal URL for viewing the same query in a browser."""
    # Direct API URL returns JSON - viewable in browser
    api_url = f"https://cthru.data.socrata.com/resource/{dataset_id}.json"
    
    if params:
        # Build query string, but remove limit for full results
        url_params = {k: v for k, v in params.items() if k != "$limit"}
        if url_params:
            query_string = urllib.parse.urlencode(url_params)
            api_url = f"{api_url}?{query_string}"
    
    # Also provide the portal link
    portal_url = f"https://cthru.data.socrata.com/d/{dataset_id}"
    
    return f"{api_url}\n               Portal: {portal_url}"


def fetch_data(dataset_id, params, app_token=None, secret=None):
    """Fetch data from the Socrata API."""
    import base64
    
    url = f"{API_BASE}/{dataset_id}.json"
    
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}"
    
    headers = {"Accept": "application/json"}
    
    # Use HTTP Basic Auth if we have both app_token and secret
    if app_token and secret:
        credentials = f"{app_token}:{secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif app_token:
        headers["X-App-Token"] = app_token
    
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"Error: HTTP {e.code} - {e.reason}", file=sys.stderr)
        if error_body:
            try:
                error_json = json.loads(error_body)
                print(f"  {error_json.get('message', error_body)}", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"  {error_body[:200]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Connection failed - {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_metadata(dataset_id, app_token=None):
    """Fetch dataset metadata to get column information."""
    url = f"https://cthru.data.socrata.com/api/views/{dataset_id}.json"
    
    headers = {"Accept": "application/json"}
    if app_token:
        headers["X-App-Token"] = app_token
    
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching metadata: {e}", file=sys.stderr)
        return None


def format_table(data, columns=None):
    """Format data as a readable table."""
    if not data:
        return "No results found."
    
    # Determine columns to show
    if columns:
        cols = [c for c in columns if c in data[0]]
    else:
        cols = list(data[0].keys())[:8]  # Limit to 8 columns for readability
    
    # Calculate column widths
    widths = {}
    for col in cols:
        max_len = len(col)
        for row in data[:50]:  # Sample first 50 rows
            val = str(row.get(col, ""))[:40]  # Truncate long values
            max_len = max(max_len, len(val))
        widths[col] = min(max_len, 40)
    
    # Build header
    header = " | ".join(col.ljust(widths[col])[:widths[col]] for col in cols)
    separator = "-+-".join("-" * widths[col] for col in cols)
    
    lines = [header, separator]
    
    # Build rows
    for row in data:
        cells = []
        for col in cols:
            val = str(row.get(col, ""))[:widths[col]]
            cells.append(val.ljust(widths[col]))
        lines.append(" | ".join(cells))
    
    return "\n".join(lines)


def format_csv(data):
    """Format data as CSV."""
    if not data:
        return ""
    
    output = []
    cols = list(data[0].keys())
    output.append(",".join(cols))
    
    for row in data:
        values = []
        for col in cols:
            val = str(row.get(col, "")).replace('"', '""')
            if "," in val or '"' in val or "\n" in val:
                val = f'"{val}"'
            values.append(val)
        output.append(",".join(values))
    
    return "\n".join(output)


def output_results(data, args, default_columns=None, url=None, dataset_id=None, params=None):
    """Output results in the specified format."""
    if not data:
        print("No results found.")
        return
    
    # Handle --save-json flag: save JSON and display table
    if hasattr(args, 'save_json') and args.save_json:
        import re
        from datetime import datetime
        
        # Build filename parts from query filters
        parts = [args.command]
        
        if hasattr(args, 'year') and args.year:
            parts.append(f"fy{args.year}")
        if hasattr(args, 'vendor') and args.vendor:
            # Sanitize vendor name for filename
            vendor_clean = re.sub(r'[^\w]', '_', args.vendor)[:20].strip('_')
            parts.append(vendor_clean)
        if hasattr(args, 'fund') and args.fund:
            fund_clean = re.sub(r'[^\w]', '_', args.fund)[:20].strip('_')
            parts.append(fund_clean)
        if hasattr(args, 'dept') and args.dept:
            dept_clean = re.sub(r'[^\w]', '_', args.dept)[:20].strip('_')
            parts.append(dept_clean)
        if hasattr(args, 'name') and args.name:
            name_clean = re.sub(r'[^\w]', '_', args.name)[:20].strip('_')
            parts.append(name_clean)
        if hasattr(args, 'search') and args.search:
            search_clean = re.sub(r'[^\w]', '_', args.search)[:20].strip('_')
            parts.append(search_clean)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts.append(timestamp)
        
        json_file = "_".join(parts) + ".json"
        
        # Build metadata wrapper with URLs
        api_url = f"https://cthru.data.socrata.com/resource/{dataset_id}.json"
        if params:
            url_params = {k: v for k, v in params.items() if k != "$limit"}
            if url_params:
                api_url = f"{api_url}?{urllib.parse.urlencode(url_params)}"
        
        portal_url = f"https://cthru.data.socrata.com/d/{dataset_id}" if dataset_id else None
        
        wrapped_data = {
            "api_url": api_url,
            "portal_url": portal_url,
            "query_timestamp": datetime.now().isoformat(),
            "record_count": len(data),
            "data": data
        }
        
        Path(json_file).write_text(json.dumps(wrapped_data, indent=2))
        print(f"JSON saved to {json_file}")
    
    if args.format == "json":
        output = json.dumps(data, indent=2)
    elif args.format == "csv":
        output = format_csv(data)
    else:  # table
        output = format_table(data, default_columns)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Results saved to {args.output} ({len(data)} records)")
    else:
        print(output)
        print(f"\n--- {len(data)} records ---")
    
    # Show URL if requested
    if hasattr(args, 'url') and args.url and url:
        print(f"\nView in browser: {url}")


def cmd_spending(args):
    """Query spending data."""
    app_token, secret = load_credentials()
    params = build_query(args, "spending")
    dataset_id = DATASETS["spending"]["id"]
    data = fetch_data(dataset_id, params, app_token, secret)
    
    url = generate_socrata_url(dataset_id, params) if hasattr(args, 'url') and args.url else None
    default_cols = ["vendor", "department", "amount", "date", "budget_fiscal_year", "object_class"]
    output_results(data, args, default_cols, url, dataset_id, params)


def cmd_payroll(args):
    """Query payroll data."""
    app_token, secret = load_credentials()
    params = build_query(args, "payroll")
    dataset_id = DATASETS["payroll"]["id"]
    data = fetch_data(dataset_id, params, app_token, secret)
    
    url = generate_socrata_url(dataset_id, params) if hasattr(args, 'url') and args.url else None
    default_cols = ["name_first", "name_last", "department_division", "position_title", "pay_total_actual", "year"]
    output_results(data, args, default_cols, url, dataset_id, params)


def cmd_settlements(args):
    """Query settlements data."""
    app_token, secret = load_credentials()
    params = {"$limit": str(args.limit)}
    if args.offset:
        params["$offset"] = str(args.offset)
    if args.search:
        params["$q"] = args.search
    
    data = fetch_data(DATASETS["settlements"]["id"], params, app_token, secret)
    output_results(data, args)


def cmd_revenue(args):
    """Query revenue data."""
    app_token, secret = load_credentials()
    params = {"$limit": str(args.limit)}
    if args.offset:
        params["$offset"] = str(args.offset)
    if args.search:
        params["$q"] = args.search
    
    data = fetch_data(DATASETS["revenue"]["id"], params, app_token, secret)
    output_results(data, args)


def cmd_datasets(args):
    """List datasets or show dataset info."""
    app_token, secret = load_credentials()
    
    if args.info:
        # Show info for specific dataset
        if args.info not in DATASETS:
            print(f"Unknown dataset: {args.info}")
            print(f"Available: {', '.join(DATASETS.keys())}")
            sys.exit(1)
        
        ds = DATASETS[args.info]
        print(f"\n{ds['name']} ({args.info})")
        print(f"  ID: {ds['id']}")
        print(f"  Description: {ds['description']}")
        
        # Fetch column metadata
        metadata = fetch_metadata(ds['id'], app_token)
        if metadata and 'columns' in metadata:
            print(f"\n  Columns ({len(metadata['columns'])}):")
            for col in metadata['columns']:
                field_name = col.get('fieldName', '')
                data_type = col.get('dataTypeName', '')
                description = col.get('description', '')
                print(f"    - {field_name} ({data_type})")
                if description:
                    print(f"        {description[:80]}")
    else:
        # List all datasets
        print("\nAvailable Datasets:\n")
        for key, ds in DATASETS.items():
            print(f"  {key:18} {ds['name']}")
            print(f"                     {ds['description']}")
            print()
        print("Use 'cthru datasets --info <name>' to see columns for a dataset.")


def main():
    parser = argparse.ArgumentParser(
        description="Query Massachusetts state financial data from CTHRU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cthru spending --vendor "W. B MASON" --year 2024
  cthru payroll --dept "Police" --year 2025 --sort "pay_total_actual:desc"
  cthru spending --search "construction" --min-amount 100000 --format csv
  cthru datasets --info spending
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Common arguments for data commands
    def add_common_args(p):
        p.add_argument("-n", "--limit", type=int, default=100, help="Number of records (default: 100)")
        p.add_argument("--offset", type=int, help="Starting record offset for pagination")
        p.add_argument("-f", "--format", choices=["table", "json", "csv"], default="table", help="Output format")
        p.add_argument("-o", "--output", help="Save output to file")
        p.add_argument("-s", "--search", help="General text search")
        p.add_argument("--sort", help="Sort by field (e.g., 'amount:desc')")
        p.add_argument("--url", action="store_true", help="Show link to view data in web browser")
        p.add_argument("--save-json", action="store_true", help="Save raw JSON response to timestamped file")
    
    # Spending command
    spending_parser = subparsers.add_parser("spending", help="Query vendor/department spending")
    add_common_args(spending_parser)
    spending_parser.add_argument("-y", "--year", help="Filter by fiscal year (e.g., 2024)")
    spending_parser.add_argument("-d", "--dept", help="Filter by department name")
    spending_parser.add_argument("-v", "--vendor", help="Filter by vendor name")
    spending_parser.add_argument("--fund", help="Filter by fund name (e.g., 'opioid')")
    spending_parser.add_argument("--min-amount", type=float, help="Minimum dollar amount")
    spending_parser.add_argument("--max-amount", type=float, help="Maximum dollar amount")
    spending_parser.set_defaults(func=cmd_spending)
    
    # Payroll command
    payroll_parser = subparsers.add_parser("payroll", help="Query state employee compensation")
    add_common_args(payroll_parser)
    payroll_parser.add_argument("-y", "--year", type=int, help="Filter by year")
    payroll_parser.add_argument("-d", "--dept", help="Filter by department/division")
    payroll_parser.add_argument("--name", help="Filter by employee name")
    payroll_parser.add_argument("--min-amount", type=float, help="Minimum total pay")
    payroll_parser.add_argument("--max-amount", type=float, help="Maximum total pay")
    payroll_parser.set_defaults(func=cmd_payroll)
    
    # Settlements command
    settlements_parser = subparsers.add_parser("settlements", help="Query legal settlements")
    add_common_args(settlements_parser)
    settlements_parser.set_defaults(func=cmd_settlements)
    
    # Revenue command
    revenue_parser = subparsers.add_parser("revenue", help="Query revenue collections")
    add_common_args(revenue_parser)
    revenue_parser.set_defaults(func=cmd_revenue)
    
    # Datasets command
    datasets_parser = subparsers.add_parser("datasets", help="List available datasets")
    datasets_parser.add_argument("--info", metavar="NAME", help="Show detailed info for a dataset")
    datasets_parser.set_defaults(func=cmd_datasets)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
