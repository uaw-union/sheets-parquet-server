# sheets-parquet-server

This is a simple Python service that serves Google Sheets and [Grist Documents](https://www.getgrist.com/) as Parquet or CSV files.

It is designed to be deployed:
- with your Google Service account credentials and Grist API keys included as environment variables
- and without accessibility to the public internet

So that from a data warehouse in the same private network, you can query Google Sheets and Grist Documents as if they were tables in a traditional SQL database.

In general, the CSV option is rarely used and Parquet is preferred. This is because Parquet is typed, and 
this service carefully preserves Grist and Google Sheets types in a way that your warehouse
may not.

This obviously is less fast that Parquet on S3 or any other traditional columnar storage, but
response times are generally good enough. Grist response times are much faster than Google Sheets.

## Usage

If we have this deployed at `http://sheets-server.internal.svc.cluster.local` (which is what
this might look like if you're using Kubernetes), you could perform:

```bash
$ curl http://sheets-server.internal.svc.cluster.local/google/<document id>/<sanitized sheet name>.(csv|parquet)

$ curl http://sheets-server.internal.svc.cluster.local/grist/<document id>/<table name>.(csv|parquet)
```
And receive a CSV or Parquet file in response.

From Clickhouse, DuckDB, Polars, or other data engines which suppose Parquet over HTTP, you can then
run something like this (in Clickhouse):
```sql
select * 
from url('http://sheets-server.internal.svc.cluster.local/google/<document id>/<sanitized sheet name>.parquet')
```

In my database, I have two functions defined:
```sql
create or replace function google_sheet_url as (sheetId, sheetName) -> 
  'http://sheets-server.warehouse.svc.cluster.local/google/' || sheetId || '/' || sheetName || '.parquet';

create or replace function grist_table_url as (docId, tableName) -> 
  'http://sheets-server.warehouse.svc.cluster.local/grist/' || docId || '/' || tableName || '.parquet';
```

Such that I can then query the data like this:
```sql
select * from url(google_sheet_url('<document id>', 'sheet1'));
```

## Deployment

3 environment variables are required:
- `GRIST_SERVER_URL`: The URL of the Grist server
- `GRIST_API_KEY`: The API key for the Grist server
- `GOOGLE_CREDENTIALS_JSON_BASE64`: The base64 encoded Google service account credentials JSON

I find it easier to encode the JSON as base64 and then decode it in the container than to
mount the service account JSON file as a configmap or volume.

