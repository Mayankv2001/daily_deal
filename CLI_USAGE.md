# CLI Usage Examples

The `daily_combined_report.py` script now supports flexible CLI arguments:

## Basic Usage

```bash
# Default: Generate combined report and send email
python3 daily_combined_report.py

# Generate only stack report (Top 5) and send email
python3 daily_combined_report.py --mode stack

# Generate only daily feed report and send email
python3 daily_combined_report.py --mode daily

# Print combined report to stdout (no email)
python3 daily_combined_report.py --print

# Print stack report to stdout
python3 daily_combined_report.py --mode stack --print

# Generate report without sending email
python3 daily_combined_report.py --no-email

# Generate stack report, print to stdout, and skip email
python3 daily_combined_report.py --mode stack --print --no-email
```

## CLI Arguments

- `--print`: Print report to stdout instead of sending email
- `--mode {stack|daily|combined}`: Choose report type (default: combined)
  - `stack`: Top 5 stackable deals only
  - `daily`: Full deal feed across all sources
  - `combined`: Both reports in one email
- `--no-email`: Skip email sending (useful for testing or local output)

## Common Workflows

**Local testing:**
```bash
python3 daily_combined_report.py --print --no-email
```

**Debug specific report type:**
```bash
python3 daily_combined_report.py --mode stack --print
```

**Generate without sending (check for errors):**
```bash
python3 daily_combined_report.py --no-email
```
