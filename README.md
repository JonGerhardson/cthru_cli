# CTHRU CLI

A command-line tool for querying Massachusetts state financial data from the [CTHRU Spending Portal](https://cthruspending.mass.gov).

## Overview

CTHRU CLI provides programmatic access to Massachusetts state spending, payroll, settlements, and revenue data through the Socrata SODA API. It supports filtering, multiple output formats, and automatic JSON export with source URLs.

## Setup

### Requirements
- Python 3.6+
- No external dependencies (uses only standard library)

### API Credentials

1. Create an account at [cthru.data.socrata.com](https://cthru.data.socrata.com)
2. Generate an API key from your profile settings
3. Save credentials to `cthru_api` in the same directory as the script:

```
ID: your_app_token_here
secret: your_secret_here
```

## Available Commands

| Command | Description | Dataset ID |
|---------|-------------|------------|
| `spending` | Vendor payments, department expenditures | `pegc-naaa` |
| `payroll` | State employee salaries | `9ttk-7vz6` |
| `settlements` | Legal settlements and judgments | `gpqz-7ppn` |
| `revenue` | Tax and non-tax revenue | `kcy7-ivxi` |
| `datasets` | List available datasets and fields | — |

## Query Options

### Common Options (all commands)

| Option | Description |
|--------|-------------|
| `-n, --limit N` | Number of records to return (default: 100) |
| `--offset N` | Skip first N records (for pagination) |
| `-f, --format` | Output format: `table`, `json`, or `csv` |
| `-o, --output FILE` | Save output to file |
| `-s, --search TEXT` | Search vendor/department names |
| `--sort FIELD` | Sort by field (e.g., `amount DESC`) |
| `--url` | Show link to view data in browser |
| `--save-json` | Save raw JSON with metadata to timestamped file |

### Spending-Specific Options

| Option | Description |
|--------|-------------|
| `-y, --year YEAR` | Filter by fiscal year (e.g., 2025) |
| `-d, --dept NAME` | Filter by department name |
| `-v, --vendor NAME` | Filter by vendor name |
| `--fund NAME` | Filter by fund name (recommended over appropriation code) |
| `--min-amount N` | Minimum dollar amount |
| `--max-amount N` | Maximum dollar amount |

### Payroll-Specific Options

| Option | Description |
|--------|-------------|
| `-y, --year YEAR` | Filter by year |
| `-d, --dept NAME` | Filter by department/division |
| `--name NAME` | Filter by employee name |
| `--min-amount N` | Minimum total pay |
| `--max-amount N` | Maximum total pay |

## Examples

### Basic Queries

```bash
# Search spending by vendor
python3 cthru.py spending --vendor "Acme Corp" --year 2025

# Get top state salaries
python3 cthru.py payroll --year 2025 --sort "pay_total_actual DESC" --limit 20

# Search by fund name
python3 cthru.py spending --fund "General" --year 2025 --limit 1000

# View settlements
python3 cthru.py settlements --limit 50
```

### Export Data

```bash
# Save as CSV
python3 cthru.py spending --vendor "Acme Corp" --year 2025 --format csv -o acme_2025.csv

# Save JSON with metadata (includes source URLs)
python3 cthru.py spending --fund "highway" --year 2025 --save-json
# Creates: spending_fy2025_highway_20260105_143012.json

# Get browser-viewable URL
python3 cthru.py spending --vendor "Acme Corp" --year 2025 --url
```

### Complex Queries

```bash
# Large payments from a specific fund
python3 cthru.py spending --fund "transportation" --year 2025 --min-amount 100000

# Department spending in fiscal year
python3 cthru.py spending --dept "Public Health" --year 2025 --limit 500

# Find employee by name
python3 cthru.py payroll --name "Smith" --year 2025 --sort "pay_total_actual DESC"
```

### Discovering Data Structure

```bash
# List all available datasets
python3 cthru.py datasets

# View columns for a specific dataset
python3 cthru.py datasets --info spending
python3 cthru.py datasets --info payroll
```

## JSON Output Format

When using `--save-json`, the output includes metadata:

```json
{
  "api_url": "https://cthru.data.socrata.com/resource/pegc-naaa.json?...",
  "portal_url": "https://cthru.data.socrata.com/d/pegc-naaa",
  "query_timestamp": "2026-01-05T21:47:49.495779",
  "record_count": 1301,
  "data": [
    { ... record 1 ... },
    { ... record 2 ... }
  ]
}
```

## Tips

### Use Fund Name, Not Appropriation Code

Some records have `appropriation_code = "UNASSIGNED"` but still have valid `fund` names. Always use `--fund` for reliable filtering:

```bash
# Good - catches all records
python3 cthru.py spending --fund "highway" --year 2025

# Less reliable - may miss UNASSIGNED records
# (appropriation_code filtering not exposed in CLI)
```

### Pagination for Large Result Sets

```bash
# First 1000 records
python3 cthru.py spending --fund "General" --year 2025 --limit 1000

# Next 1000 records
python3 cthru.py spending --fund "General" --year 2025 --limit 1000 --offset 1000
```

### Sorting Results

```bash
# Highest amounts first
python3 cthru.py spending --vendor "Acme Corp" --sort "amount DESC"

# Most recent first
python3 cthru.py spending --vendor "Acme Corp" --sort "date DESC"

# Top salaries
python3 cthru.py payroll --year 2025 --sort "pay_total_actual DESC" --limit 10
```

## Data Sources

Data comes from the Massachusetts Comptroller's CTHRU transparency portal:

- **Portal**: https://cthruspending.mass.gov
- **API Base**: https://cthru.data.socrata.com
- **API Docs**: https://dev.socrata.com

The tool uses the Socrata SODA API with HTTP Basic Authentication.

## Troubleshooting

### "Invalid app_token" Error
Check that `cthru_api` file exists and has valid credentials.

### Timeout Errors
Try reducing `--limit` or adding more specific filters.

### No Results Found
- Check spelling of vendor/fund/department names
- Try partial matches (the tool uses `LIKE '%term%'` matching)
- Verify the fiscal year has data

## License

MIT
