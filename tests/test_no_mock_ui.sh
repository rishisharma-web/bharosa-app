#!/usr/bin/env bash
# Spec §14: frontend code may contain no literal names or ₹ amounts; only static/overview/ may match.
cd "$(dirname "$0")/.."
bad=$(grep -rlnE "₹ ?[0-9]|Ramesh|Priya|Vikram|Anita|Lakshmi|Sharma" static --include=*.js --include=*.html | grep -v '^static/overview/')
if [ -n "$bad" ]; then echo "Mock data found in:"; echo "$bad"; exit 1; fi
echo "OK: no mock data outside static/overview/"
