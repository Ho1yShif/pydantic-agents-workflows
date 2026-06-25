"""API endpoint for fetching Logfire logs."""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
import logfire

from backend.config import settings

# How far back to scope the query. The trace_id WHERE clause already pins the
# results to one trace; this window just needs to comfortably contain it.
LOGFIRE_QUERY_WINDOW_DAYS = 7


async def fetch_logfire_logs(trace_id: str) -> dict:
    """
    Fetch logs from Logfire API for a specific trace ID.
    
    Args:
        trace_id: The OpenTelemetry trace ID (32-char hex string)
        
    Returns:
        Dictionary containing the logs data from Logfire
        
    Raises:
        HTTPException: If the API request fails or auth is missing
    """
    if not settings.logfire_read_token:
        raise HTTPException(
            status_code=501,
            detail="Logfire read token not configured. Set LOGFIRE_READ_TOKEN environment variable."
        )
    
    # SQL query to fetch all records for this trace.
    # Logfire stores spans and logs in the 'records' table.
    # See: https://pydantic.dev/docs/logfire/manage/query-api/
    query = f"""
        SELECT
            start_timestamp,
            message,
            level,
            span_name,
            span_id,
            parent_span_id,
            attributes,
            service_name,
            trace_id
        FROM records
        WHERE trace_id = '{trace_id}'
        ORDER BY start_timestamp ASC
        LIMIT 1000
    """

    # The Query API requires min_timestamp and applies its own row limit
    # (default 100), independent of the SQL LIMIT.
    min_timestamp = (
        datetime.now(timezone.utc) - timedelta(days=LOGFIRE_QUERY_WINDOW_DAYS)
    ).isoformat()
    body = {
        "sql": query,
        "min_timestamp": min_timestamp,
        "limit": 1000,
    }

    headers = {
        "Authorization": f"Bearer {settings.logfire_read_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.logfire_api_base}/v2/query",
                json=body,
                headers=headers
            )

            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid Logfire read token")
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="Insufficient permissions for Logfire API")
            elif response.status_code != 200:
                logfire.error(f"Logfire API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Logfire API error: {response.text}"
                )

            data = response.json()

            # v2 JSON returns row objects under "data" (with a "schema" sibling).
            # Fall back to "rows", then to the legacy columnar "columns" shape so
            # this keeps working across API/format variations.
            rows = data.get("data")
            if rows is None:
                rows = data.get("rows")
            if rows is None:
                columns = data.get("columns", [])
                rows = []
                if columns:
                    num_rows = len(columns[0].get("values", []))
                    for i in range(num_rows):
                        row = {
                            col.get("name"): (
                                col.get("values", [])[i]
                                if i < len(col.get("values", []))
                                else None
                            )
                            for col in columns
                        }
                        rows.append(row)

            logfire.info(f"Fetched {len(rows)} log records for trace {trace_id}")

            return {
                "trace_id": trace_id,
                "logs": rows,
                "record_count": len(rows)
            }

    except httpx.TimeoutException:
        logfire.error(f"Timeout fetching logs for trace {trace_id}")
        raise HTTPException(status_code=504, detail="Logfire API timeout")
    except httpx.RequestError as e:
        logfire.error(f"Error fetching logs for trace {trace_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Logfire API: {str(e)}")
