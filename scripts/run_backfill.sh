#!/bin/bash
# Backfill receipts 24 months in 14-day chunks
# Run: nohup bash scripts/run_backfill.sh > logs/backfill_24m.log 2>&1 &

set -euo pipefail
cd /root/projects/SalesForecast/sales_forecast

source .env.prod 2>/dev/null || source .env 2>/dev/null
BASE="http://localhost:8002"
CHUNK_DAYS=14
SLEEP=5

mkdir -p logs

echo "=== Backfill started at $(date) ==="
echo "Range: 2024-06-01 .. 2026-05-25"
echo ""

start_date="2024-06-01"
end_date="2026-05-25"
cursor="$start_date"
chunk_num=0
total_chunks=51  # ~24 months / 14 days

while [[ "$cursor" < "$end_date" || "$cursor" == "$end_date" ]]; do
    chunk_end=$(date -d "$cursor + $((CHUNK_DAYS - 1)) days" +%Y-%m-%d)
    if [[ "$chunk_end" > "$end_date" ]]; then
        chunk_end="$end_date"
    fi
    chunk_num=$((chunk_num + 1))

    echo -n "[$chunk_num/$total_chunks] $cursor .. $chunk_end — "

    response=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $API_TOKEN" \
        -X POST "$BASE/api/receipts/sync?from_date=$cursor&to_date=$chunk_end" \
        --max-time 600 2>&1) || {
        echo "CURL FAILED"
        cursor=$(date -d "$chunk_end + 1 day" +%Y-%m-%d)
        sleep $SLEEP
        continue
    }

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [[ "$http_code" == "200" ]]; then
        receipts=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_receipts',0))" 2>/dev/null || echo "?")
        items=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_items',0))" 2>/dev/null || echo "?")
        echo "OK | $receipts receipts, $items items"
    else
        echo "HTTP $http_code | $body"
    fi

    cursor=$(date -d "$chunk_end + 1 day" +%Y-%m-%d)
    if [[ "$cursor" < "$end_date" || "$cursor" == "$end_date" ]]; then
        sleep $SLEEP
    fi
done

echo ""
echo "=== Backfill finished at $(date) ==="
echo "Run SKU aggregation: curl -X POST '$BASE/api/forecast/sku/aggregate/backfill' -H 'Authorization: Bearer ...'"
